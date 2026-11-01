"""One method per flow step.

LangGraph reruns a node from the top when it resumes, so anything with a side
effect goes after the node's interrupt, or in a separate node.
"""
import base64
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from langgraph.types import interrupt
from pydantic import ValidationError

from app.assistant import Assistant, clean_answer, parse_correction
from app.browser import BrowserError, BrowserSessionLost, BrowserWorker
from app.config import Settings
from app.documents import DocumentError, combine, file_name, fit_document
from app.events import EventLog
from app.graph import messages
from app.graph.state import AgentState
from app.llm import LlmError
from app.planner import Planner, PlanError
from app.plugins import PluginError, Plugins, call
from app.redact import mask_for_display, redact
from app.sessions import SessionStore
from app.skills import SkillStep, SkillStore
from app.states import indian_state, states_in_message
from app.vault import FileStore, Vault
from common.corrections import normalize as normalize_value
from common.corrections import parse_draft_edit
from common.textnorm import one_amount
from contracts.browser import Action, Snapshot
from contracts.doctor import DoctorRequest, DoctorResponse
from contracts.documents import DocumentImage, ExtractedDocument, ExtractionResult
from contracts.eligibility import EligibilityRequest, EligibilityResponse
from contracts.profile import Profile, ProfileField
from contracts.vault import Receipt

log = logging.getLogger(__name__)
LOGIN_BOX = re.compile(
    r"user.?id|login.?id|registration.?id|application.?id|username|mobile number", re.I
)

MAX_STRIKES = 3
MAX_BUTTONS = 3
MAX_CHAT_TURNS = 12  # Then the fixed questions finish the job.
YES_WORDS = {"yes", "y", "ok", "okay", "agree", "i agree", "ஆம்", "சரி", "हाँ", "हां", "ठीक है"}
NO_WORDS = {"no", "n", "disagree", "இல்லை", "नहीं"}


@dataclass
class Deps:
    settings: Settings
    browser: BrowserWorker
    vault: Vault
    files: FileStore
    skills: SkillStore
    planner: Planner
    assistant: Assistant
    plugins: Plugins
    events: EventLog
    sessions: SessionStore


def ask(
    kind: str,
    text: str,
    buttons: dict[str, str] | None = None,
    image_ref: str | None = None,
    localized: bool = False,
) -> dict[str, Any]:
    """Pause the graph until the user replies. Button ids carry the prompt kind.

    `localized` marks text already in the user's language, so it is not translated.
    """
    prompt: dict[str, Any] = {
        "kind": kind,
        "text": text,
        "image_ref": image_ref,
        "localized": localized,
    }
    if buttons:
        prompt["buttons"] = {f"{kind}:{id_}": title for id_, title in buttons.items()}
    return interrupt(prompt)


def chosen(reply: dict[str, Any]) -> str | None:
    button = reply.get("button")
    return button.split(":", 1)[1] if button else None


def typed(reply: dict[str, Any]) -> str:
    return str(reply.get("text", "")).strip()


def profile_of(state: AgentState) -> Profile:
    return Profile.model_validate(state.get("profile") or {})


def known_values(state: AgentState) -> dict[str, str]:
    return {name: f.value for name, f in profile_of(state).fields.items()}


def indian_rupees(digits: str) -> str:
    """Group as India writes it, so 120000 reads ₹1,20,000 and a slip is easy to see."""
    head, tail = digits[:-3], digits[-3:]
    groups = []
    while head:
        groups.insert(0, head[-2:])
        head = head[:-2]
    return "₹" + ",".join([*groups, tail])


def display_answer(question: messages.Question, fields: dict[str, ProfileField]) -> str:
    field = fields.get(question.field)
    if field is None:
        return "-"
    if question.digits_only and field.value.isdigit():
        return indian_rupees(field.value)
    return field.value


def with_answer(state: AgentState, field: str, value: str, source: str) -> dict[str, Any]:
    profile = profile_of(state)
    profile.fields[field] = ProfileField(value=value, source_document=source, confidence=1.0)
    return profile.model_dump()


class Nodes:
    def __init__(self, deps: Deps) -> None:
        self.d = deps

    def _emit(self, state: AgentState, step: str, message: str, reasoning: str | None = None) -> None:
        self.d.events.emit(
            state["session_id"], "step_started", step=step, message=message, reasoning=reasoning
        )

    def _module_failed(self, state: AgentState, step: str, exc: Exception) -> None:
        """A teammate's module must never end a user's session."""
        log.warning("Module for %s failed: %s", step, type(exc).__name__)
        self._emit(state, step, "Module failed, so this step was skipped", type(exc).__name__)

    # --- User loop ---

    async def choose_language(self, state: AgentState) -> dict[str, Any]:
        choices = messages.LANGUAGE_CHOICES
        reply = ask("language", messages.CHOOSE_LANGUAGE, choices, localized=True)
        choice = chosen(reply) or messages.LANGUAGE_WORDS.get(typed(reply).lower())
        if choice not in choices:
            return {}
        self.d.sessions.set_language(state["session_id"], choice)
        return {"language": choice}

    async def consent(self, state: AgentState) -> dict[str, Any]:
        reply = ask("consent", messages.CONSENT, {"yes": "I agree", "no": "No thanks"})
        answer = chosen(reply) or typed(reply).lower()
        if answer == "yes" or answer in YES_WORDS:
            return {
                "consent": {
                    "given_at": datetime.now(UTC).isoformat(),
                    "version": messages.CONSENT_VERSION,
                }
            }
        if answer == "no" or answer in NO_WORDS:
            return {
                "outcome": "declined",
                "final": {"text": messages.DECLINED},
            }
        return {}

    async def confirm_details(self, state: AgentState) -> dict[str, Any]:
        """The AI can misread an answer, so the user checks them before they are used."""
        fields = profile_of(state).fields
        lines = [
            f"{number}. {question.label} {display_answer(question, fields)}"
            for number, question in enumerate(messages.QUESTIONS, start=1)
        ]
        text = "\n\n".join(
            [messages.CONFIRM_INTRO, "\n".join(lines), messages.CONFIRM_QUESTION]
        )
        reply = ask("confirm", text, {"yes": "Yes, correct", "change": "Change"})
        answer = chosen(reply) or typed(reply).lower()
        if answer == "yes" or answer in YES_WORDS:
            return {"details_choice": "yes"}
        if answer == "change" or answer in NO_WORDS:
            return {"details_choice": "change"}
        return self._apply_correction(state, typed(reply))

    @staticmethod
    def _apply_correction(state: AgentState, text: str) -> dict[str, Any]:
        """Save a fix and show the details again, or ask for it in the numbered form."""
        correction = parse_correction(text)
        if correction is None:
            return {"details_choice": "change", "fix_error": True}
        question, value = correction
        return {
            "fix_error": False,
            "details_choice": None,
            "profile": with_answer(state, question.field, value, "user_edit"),
        }

    async def fix_details(self, state: AgentState) -> dict[str, Any]:
        text = messages.EDIT
        if state.get("fix_error"):
            text = f"{messages.EDIT_INVALID} {text}"
        return self._apply_correction(state, typed(ask("fix", text)))

    async def collect_documents(self, state: AgentState) -> dict[str, Any]:
        file_refs = state.get("file_refs", [])
        intro = None
        if state.get("documents_needed"):
            text = messages.DOCUMENTS_NEEDED
        elif file_refs:
            text = messages.DOCUMENT_RECEIVED
        else:
            intro = state.get("documents_intro")
            text = intro or messages.DOCUMENTS
        reply = ask("documents", text, {"done": "Done"}, localized=bool(intro))
        if reply.get("file_ref"):
            entry = {"file_ref": reply["file_ref"], "mime_type": reply.get("mime_type", "image/jpeg")}
            return {"file_refs": [*file_refs, entry], "documents_needed": False}
        if chosen(reply) == "done" or typed(reply).lower() == "done":
            if file_refs:
                return {"documents_done": True}
            return {"documents_needed": True}
        return {}

    async def extract_profile(self, state: AgentState) -> dict[str, Any]:
        extract = self.d.plugins.extraction
        if extract is None:
            return {"documents": []}
        self._emit(state, "extract_profile", "Reading your documents")
        images = []
        for entry in state["file_refs"]:
            data, mime_type = self.d.files.get(entry["file_ref"])
            images.append(DocumentImage(file_ref=entry["file_ref"], mime_type=mime_type, data=data))
        try:
            result = ExtractionResult.model_validate(await call(extract, images))
        except (PluginError, ValidationError) as exc:
            self._module_failed(state, "extract_profile", exc)
            return {"documents": []}
        # What the user told us stays. The doctor flags any clash with the documents.
        profile = profile_of(state)
        for name, field in result.profile.fields.items():
            profile.fields.setdefault(name, field)
        return {
            "profile": profile.model_dump(),
            "documents": [document.model_dump() for document in result.documents],
        }

    async def intake_think(self, state: AgentState) -> dict[str, Any]:
        """Ask the model what to say next. Separate from the wait for the user,
        because a node reruns on resume and this must not call the model twice."""
        answered = state.get("answered", [])
        missing = [q for q in messages.QUESTIONS if q.field not in answered]
        if not self.d.assistant.available or state.get("chat_turns", 0) >= MAX_CHAT_TURNS:
            return {"intake_route": "fallback"}
        language = messages.LANGUAGE_NAMES.get(state.get("language", ""), "English")
        try:
            have = {
                field: profile_of(state).fields[field].value
                for field in answered
                if field in profile_of(state).fields
            }
            turn = await self.d.assistant.next_turn(
                state.get("chat", []), have, missing, language
            )
        except LlmError as exc:
            log.warning("AI chat fell back to fixed questions: %s", exc)
            return {"intake_route": "fallback"}

        profile = profile_of(state)
        for field, value in turn.fields.items():
            profile.fields[field] = ProfileField(
                value=value, source_document="user_answer", confidence=1.0
            )
        answered = list(dict.fromkeys([*answered, *turn.fields]))
        update: dict[str, Any] = {
            "profile": profile.model_dump(),
            "answered": answered,
            "chat": [*state.get("chat", []), {"role": "assistant", "text": turn.reply}],
        }
        if all(q.field in answered for q in messages.QUESTIONS):
            return {
                **update,
                "intake_route": "done",
                "questions_done": True,
                "documents_intro": turn.reply,
            }
        return {**update, "intake_route": "listen", "chat_reply": turn.reply}

    async def intake_listen(self, state: AgentState) -> dict[str, Any]:
        reply = ask("chat", state["chat_reply"], localized=True)
        text = typed(reply)
        if not text:
            return {}
        return {
            "chat": [*state.get("chat", []), {"role": "user", "text": redact(text)}],
            "chat_turns": state.get("chat_turns", 0) + 1,
        }

    async def ask_question(self, state: AgentState) -> dict[str, Any]:
        answered = state.get("answered", [])
        for question in messages.QUESTIONS:
            if question.field in answered:
                continue
            reply = ask(f"question_{question.field}", question.text, dict(question.choices) or None)
            value = dict(question.choices).get(chosen(reply) or "") or typed(reply)
            if not value:
                return {}
            if question.field == "state":
                # A spoken answer arrives as a sentence ("I am in Tamil Nadu"): take it only when
                # it names exactly one state.
                named = states_in_message(value)
                value = indian_state(value) or (named[0] if len(named) == 1 else None)
                if value is None:
                    return {}  # Not a place we know, so the question comes round again.
            elif question.digits_only:
                # Store digits, not the sentence: "Our income is ₹2,00,000." -> 200000.
                value = clean_answer(question, value, strict=True) or one_amount(value)
                if value is None:
                    return {}
            return {
                "profile": with_answer(state, question.field, value, "user_answer"),
                "answered": [*answered, question.field],
            }
        return {"questions_done": True}

    async def match_schemes(self, state: AgentState) -> dict[str, Any]:
        self._emit(state, "match_schemes", "Checking which schemes you qualify for")
        request = EligibilityRequest(profile=profile_of(state))
        try:
            response = EligibilityResponse.model_validate(
                await call(self.d.plugins.rules, request)
            )
        except (PluginError, ValidationError) as exc:
            self._module_failed(state, "match_schemes", exc)
            return {"schemes": [], "rules_failed": True}
        asked = state.get("asked_for_schemes", [])
        unasked = [q for q in response.questions if q.field not in asked]
        if unasked:
            return {"scheme_question": unasked[0].model_dump()}
        schemes = sorted(response.schemes, key=lambda scheme: scheme.rank)
        if not schemes:
            return {"schemes": [], "outcome": "no_scheme", "final": {"text": messages.NO_SCHEME}}
        return {"schemes": [scheme.model_dump() for scheme in schemes]}

    async def ask_scheme_question(self, state: AgentState) -> dict[str, Any]:
        """Ask what decides a scheme, so nobody is told they qualify on a guess."""
        question = state["scheme_question"]
        reply = ask("scheme_detail", question["text"], question["choices"] or None)
        value = chosen(reply) or typed(reply)
        if not value:
            return {}
        return {
            "scheme_question": None,
            "asked_for_schemes": [*state.get("asked_for_schemes", []), question["field"]],
            "profile": with_answer(state, question["field"], value, "user_answer"),
        }

    async def choose_scheme(self, state: AgentState) -> dict[str, Any]:
        schemes = state["schemes"][:MAX_BUTTONS]
        lines = [f"{s['rank']}. {s['name']}\n   {s['cited_clause']}" for s in schemes]
        text = "\n\n".join([messages.SCHEMES_INTRO, "\n".join(lines), messages.SCHEMES_QUESTION])
        reply = ask("scheme", text, {s["scheme_id"]: s["name"] for s in schemes})
        choice = chosen(reply) or typed(reply)
        for index, scheme in enumerate(schemes, start=1):
            if choice in (scheme["scheme_id"], str(index)):
                return {"scheme": scheme, "portal_id": scheme["portal_id"]}
        return {}

    async def doctor(self, state: AgentState) -> dict[str, Any]:
        self._emit(state, "doctor", "Checking your documents for mismatches")
        scheme = state.get("scheme") or {}
        documents = [ExtractedDocument.model_validate(d) for d in state.get("documents", [])]
        request = DoctorRequest(
            profile=profile_of(state), documents=documents, scheme_id=scheme.get("scheme_id")
        )
        try:
            report = DoctorResponse.model_validate(await call(self.d.plugins.doctor, request))
        except (PluginError, ValidationError) as exc:
            self._module_failed(state, "doctor", exc)
            return {"doctor_report": None}
        return {"doctor_report": report.model_dump()}

    # --- Portal run ---

    async def prepare_portal(self, state: AgentState) -> dict[str, Any]:
        portal_id = state.get("portal_id") or self.d.settings.default_portal_id
        if not portal_id:
            return {"route": "stop", "outcome": "no_portal", "final": {"text": messages.NO_PORTAL}}
        if state.get("browser_session"):
            try:
                await self.d.browser.close(state["browser_session"])
            except BrowserError:
                pass
        try:
            browser_session = await self.d.browser.open(portal_id, known_values(state))
        except BrowserError as exc:
            return self._strike(state, f"Could not open the portal: {exc}", retry_route="reopen")

        skill = self.d.skills.latest(portal_id)
        mode = "replay" if skill else "explore"
        self._emit(
            state,
            "prepare_portal",
            f"Opening {portal_id}",
            f"Replaying saved skill v{skill.version}" if skill else "No saved skill, so exploring",
        )
        return {
            "route": "login",
            "portal_id": portal_id,
            "browser_session": browser_session,
            "mode": mode,
            "steps": [step.model_dump() for step in skill.steps] if skill else [],
            "skill_version": skill.version if skill else None,
            "skill_repaired": False,
            "trace": [],
            "step_index": 0,
            "challenge": None,
        }

    async def _has_no_login_box(self, state: AgentState) -> bool:
        """Live pages often open on information or a form, so ask for a login only
        when one is on the page. The agent can still reach a login page later."""
        try:
            snapshot = await self.d.browser.snapshot(state["browser_session"])
        except BrowserError:
            return False
        return bool(snapshot.observation_id) and not any(
            LOGIN_BOX.search(node.name) for node in snapshot.nodes
        )

    async def portal_login(self, state: AgentState) -> dict[str, Any]:
        if await self._has_no_login_box(state):
            return {"route": "again"}
        owner, portal_id = state["owner"], state["portal_id"]
        portal_user_id = self.d.vault.get_portal_id(owner, portal_id)
        if portal_user_id is None:
            portal_user_id = typed(ask("portal_id", messages.PORTAL_ID))
            if not portal_user_id:
                return {"route": "login"}
            self.d.vault.put_portal_id(owner, portal_id, portal_user_id)
        self._emit(state, "portal_login", "Logging in to the portal")
        try:
            await self.d.browser.login(state["browser_session"], portal_user_id)
        except BrowserSessionLost:
            return self._strike(state, "Browser session lost during login", retry_route="reopen")
        except BrowserError as exc:
            return self._strike(state, f"Login failed: {exc}", retry_route="login")
        return {"route": "again"}

    async def browser_step(self, state: AgentState) -> dict[str, Any]:
        """Do one thing on the portal, so every action gets its own checkpoint."""
        try:
            snapshot = await self.d.browser.snapshot(state["browser_session"])
        except BrowserSessionLost:
            return self._strike(state, "Browser session lost", retry_route="reopen")
        except BrowserError as exc:
            return self._strike(state, str(exc))

        if snapshot.session_expired:
            return {"route": "login"}
        if snapshot.challenge:
            return self._raise_challenge(state, snapshot)

        if state["mode"] == "replay":
            update = await self._replay_step(state, snapshot)
        else:
            update = await self._explore_step(state, snapshot)
        return {"challenge_tries": 0, **update}

    def _raise_challenge(self, state: AgentState, snapshot: Snapshot) -> dict[str, Any]:
        challenge = snapshot.challenge
        tries = state.get("challenge_tries", 0) + 1
        if tries > MAX_STRIKES:
            return self._handover(f"{challenge.kind} failed {MAX_STRIKES} times")
        image_ref = None
        if challenge.image_base64:
            image_ref = self.d.files.put(base64.b64decode(challenge.image_base64), "image/png")
        return {
            "route": "challenge",
            "challenge_tries": tries,
            "challenge": {
                "kind": challenge.kind,
                "input": challenge.input.model_dump(),
                "submit": challenge.submit.model_dump() if challenge.submit else None,
                "image_ref": image_ref,
            },
        }

    async def _explore_step(self, state: AgentState, snapshot: Snapshot) -> dict[str, Any]:
        if len(state.get("trace", [])) >= self.d.settings.max_explore_steps:
            return self._handover("Exploring took too many steps")
        history = [step["intent"] for step in state.get("trace", [])]
        try:
            planned = await self.d.planner.next_step(
                self._goal(state),
                snapshot,
                known_values(state),
                self._document_names(state),
                history,
                [step for step in state.get("trace", []) if step["action"] == "upload"],
            )
        except (LlmError, PlanError) as exc:
            return self._strike(state, f"Planning failed: {exc}")

        self._emit(state, "browser_step", planned.intent or planned.action, planned.reasoning)
        if planned.action == "review":
            return {"route": "reached_review"}
        if planned.action == "ask":
            return {"route": "ask_field", "missing_field": planned.field}
        node = next((n for n in snapshot.nodes if n.ref == planned.ref), None)
        target = {"role": node.role, "name": node.name} if node else None
        step = SkillStep(
            intent=planned.intent or planned.action,
            action=planned.action,
            target=target,
            field=planned.field,
            document=planned.document,
            file_rules=planned.file_rules,
        )
        update = await self._perform(state, step, snapshot)
        if update.get("route") == "again" and update.get("strikes") == 0:
            update["trace"] = [*state.get("trace", []), step.model_dump()]
        return update

    async def _replay_step(self, state: AgentState, snapshot: Snapshot) -> dict[str, Any]:
        steps, index = state["steps"], state["step_index"]
        if index >= len(steps):
            return {"route": "reached_review"}
        step = SkillStep.model_validate(steps[index])
        repaired: dict[str, Any] = {}
        if step.target and snapshot.find(step.target) is None:
            try:
                target, reasoning = await self.d.planner.repair(step, snapshot, known_values(state))
            except (LlmError, PlanError) as exc:
                return self._strike(state, f"Self-repair failed: {exc}")
            self._emit(
                state,
                "self_repair",
                f"Page changed: '{step.target.name}' is now '{target.name}'",
                reasoning,
            )
            step = step.model_copy(update={"target": target})
            new_steps = [*steps]
            new_steps[index] = step.model_dump()
            repaired = {"steps": new_steps, "skill_repaired": True}
        else:
            self._emit(state, "browser_step", step.intent, "Replaying saved skill")
        return {**repaired, **await self._perform(state, step, snapshot)}

    async def _perform(
        self, state: AgentState, step: SkillStep, snapshot: Snapshot
    ) -> dict[str, Any]:
        action = Action(type=step.action, target=step.target, wait_ms=step.wait_ms)
        filled: dict[str, Any] = {}
        if step.action == "type":
            field = profile_of(state).fields.get(step.field or "")
            if field is None:
                return {"route": "ask_field", "missing_field": step.field}
            action.value = field.value
            filled = {
                step.field: {
                    "label": step.target.name if step.target else step.field,
                    "source_document": field.source_document,
                    "confidence": field.confidence,
                }
            }
        elif step.action == "upload":
            try:
                await self._attach_document(state, step, action, snapshot)
            except (LookupError, DocumentError) as exc:
                return self._strike(state, str(exc))
        try:
            result = await self.d.browser.act(state["browser_session"], action)
        except BrowserSessionLost:
            return self._strike(state, "Browser session lost", retry_route="reopen")
        except BrowserError as exc:
            return self._strike(state, str(exc))
        if not result.ok:
            return self._strike(state, result.error or "The action failed")
        update: dict[str, Any] = {
            "route": "again",
            "strikes": 0,
            "step_index": state.get("step_index", 0) + 1,
        }
        if filled:
            update["filled"] = {**state.get("filled", {}), **filled}
        return update

    async def _attach_document(
        self, state: AgentState, step: SkillStep, action: Action, snapshot: Snapshot
    ) -> None:
        file_ref = self._file_for(state, step.document)
        if file_ref is None:
            raise LookupError(f"No document for {step.document}")
        data, mime_type = self.d.files.get(file_ref)
        compress = self.d.plugins.compressor
        if compress is not None:
            try:
                data = await call(
                    compress, data, mime_type, state["portal_id"], step.document or ""
                )
            except PluginError as exc:
                self._module_failed(state, "compressor", exc)  # Try the original.
        # Read fresh on every run, because a form can change its rules at any time.
        control = snapshot.find(step.target) if step.target else None
        rules = combine(
            control.file_rules if control else None, step.file_rules, snapshot.upload_limits
        )
        data, mime_type = await fit_document(data, mime_type, rules)
        action.file_base64 = base64.b64encode(data).decode()
        action.file_mime = mime_type
        action.file_name = file_name(step.document or "document", mime_type)

    @staticmethod
    def _file_for(state: AgentState, document_type: str | None) -> str | None:
        for document in state.get("documents", []):
            if document["document_type"] == document_type:
                return document["file_ref"]
        # Without extraction, documents are only known as document_1, document_2...
        file_refs = state.get("file_refs", [])
        match = re.fullmatch(r"document_(\d+)", document_type or "")
        index = int(match[1]) - 1 if match else 0
        return file_refs[index]["file_ref"] if index < len(file_refs) else None

    @staticmethod
    def _document_names(state: AgentState) -> list[str]:
        names = [document["document_type"] for document in state.get("documents", [])]
        return names or [f"document_{i}" for i in range(1, len(state.get("file_refs", [])) + 1)]

    @staticmethod
    def _goal(state: AgentState) -> str:
        scheme = state.get("scheme") or {}
        target = scheme.get("name") or state.get("portal_id")
        return (
            f"Fill in the application for {target} up to its final review page. "
            "Do not submit it."
        )

    def _strike(
        self, state: AgentState, reason: str, retry_route: str = "again"
    ) -> dict[str, Any]:
        strikes = state.get("strikes", 0) + 1
        self.d.events.emit(
            state["session_id"], "step_started", step="retry",
            message=f"Try {strikes} of {MAX_STRIKES} failed", reasoning=reason,
        )
        if strikes >= MAX_STRIKES:
            return {"strikes": strikes, **self._handover(reason)}
        return {"strikes": strikes, "route": retry_route}

    @staticmethod
    def _handover(reason: str) -> dict[str, Any]:
        return {"route": "handover", "handover_reason": reason}

    async def challenge(self, state: AgentState) -> dict[str, Any]:
        challenge = state["challenge"]
        text = messages.CAPTCHA if challenge["kind"] == "captcha" else messages.OTP
        answer = typed(ask(challenge["kind"], text, image_ref=challenge["image_ref"]))
        browser_session = state["browser_session"]
        try:
            await self.d.browser.act(
                browser_session, Action(type="type", target=challenge["input"], value=answer)
            )
            if challenge["submit"]:
                await self.d.browser.act(
                    browser_session, Action(type="click", target=challenge["submit"])
                )
        except BrowserError as exc:
            return {**self._strike(state, str(exc)), "challenge": None}
        return {"challenge": None, "route": "again"}

    async def ask_field(self, state: AgentState) -> dict[str, Any]:
        # A fixed sentence, so a hostile page cannot word the question via the model.
        field = state["missing_field"]
        label = field.replace("_", " ")
        value = typed(ask(f"field_{field}", messages.FIELD_NEEDED.format(label=label)))
        if not value:
            return {}
        return {
            "profile": with_answer(state, field, value, "user_answer"),
            "missing_field": None,
        }

    async def handover(self, state: AgentState) -> dict[str, Any]:
        """Wait for a human. Only the session API can resume this, not the user."""
        reply = ask("handover", messages.HANDOVER)
        action = reply.get("action")
        if reply.get("receipt_number"):
            return {"receipt_number": reply["receipt_number"], "route": "receipt"}
        if action == "abort":
            return {"route": "stop", "outcome": "aborted", "final": {"text": messages.ABORTED}}
        route = "again" if state.get("browser_session") else "reopen"
        return {"route": route, "strikes": 0, "challenge_tries": 0, "handover_reason": None}

    # --- Review and submit ---

    async def save_skill(self, state: AgentState) -> dict[str, Any]:
        portal_id = state["portal_id"]
        if state["mode"] == "explore":
            steps = [SkillStep.model_validate(step) for step in state.get("trace", [])]
            version = self.d.skills.save(portal_id, steps, repaired=False)
        elif state.get("skill_repaired"):
            steps = [SkillStep.model_validate(step) for step in state["steps"]]
            version = self.d.skills.save(portal_id, steps, repaired=True)
        else:
            version = state["skill_version"]
            self.d.skills.record_run(portal_id, version)
        self._emit(state, "save_skill", f"Saved skill v{version} for {portal_id}")
        return {"skill_version": version}

    async def prepare_review(self, state: AgentState) -> dict[str, Any]:
        snapshot = await self.d.browser.snapshot(state["browser_session"])
        image_ref = None
        if snapshot.screenshot_masked and snapshot.screenshot_base64:
            image_ref = self.d.files.put(base64.b64decode(snapshot.screenshot_base64), "image/png")

        known = known_values(state)
        filled = self._filled_fields(state, snapshot)
        lines = [
            f"{number}. {details['label']}: {mask_for_display(field, known.get(field, ''))}"
            for number, (field, details) in enumerate(filled.items(), start=1)
        ]
        report = state.get("doctor_report")
        if report and report["mismatches"]:
            lines.append(f"\n{messages.REVIEW_FLAGS}")
            lines += [f"- {m['field']}: {m['detail']}" for m in report["mismatches"]]
        text = f"{messages.REVIEW_INTRO}\n\n" + "\n".join(lines)
        return {"review": {"text": text, "image_ref": image_ref}, "filled": filled}

    @staticmethod
    def _filled_fields(state: AgentState, snapshot: Snapshot) -> dict[str, dict[str, Any]]:
        """A managed portal fills the form itself, so it reports what it filled."""
        if not snapshot.managed_fields:
            return state.get("filled", {})
        fields = profile_of(state).fields
        return {
            name: {
                "label": label,
                "source_document": fields[name].source_document,
                "confidence": fields[name].confidence,
            }
            for name, label in snapshot.managed_fields.items()
            if name in fields
        }

    async def review(self, state: AgentState) -> dict[str, Any]:
        review = state["review"]
        reply = ask(
            "approval",
            review["text"],
            {"approve": "Approve", "edit": "Edit"},
            image_ref=review["image_ref"],
        )
        choice = chosen(reply) or typed(reply).lower()
        if choice in ("approve", "edit"):
            return {"review_choice": choice}
        return {"review_choice": None}

    async def edit(self, state: AgentState) -> dict[str, Any]:
        text = messages.EDIT
        if state.get("edit_error"):
            text = f"{messages.EDIT_INVALID} {text}"
        # Read in code, never by the AI: "2 120000", "income 2 lakh", "change dob to 15/08/2005".
        parsed = parse_draft_edit(typed(ask("edit", text)), state.get("filled", {}))
        if parsed is None:
            return {"edit_error": "invalid"}
        field, raw = parsed
        question = next((q for q in messages.QUESTIONS if q.field == field), None)
        value = clean_answer(question, raw, strict=True) if question else normalize_value(field, raw)
        if not value:
            return {"edit_error": "invalid"}
        return {
            "edit_error": None,
            "review_choice": None,
            "strikes": 0,
            "profile": with_answer(state, field, value, "user_edit"),
        }

    async def submit(self, state: AgentState) -> dict[str, Any]:
        owner = state["owner"]
        if not self.d.settings.allow_real_submit:
            lines = [messages.STOPPED_AT_REVIEW]
            lines += [
                messages.EARLIER_RECEIPT.format(number=receipt.receipt_number)
                for receipt in self.d.vault.list_receipts(owner)
            ]
            return {
                "route": "stop",
                "outcome": "stopped_at_review",
                "final": {"text": "\n\n".join(lines)},
            }

        if not self.d.sessions.claim_submit(state["session_id"]):
            return self._handover(messages.SUBMIT_UNCERTAIN)
        self._emit(state, "submit", "Submitting the approved application")
        browser_session = state["browser_session"]
        snapshot = await self.d.browser.snapshot(browser_session)
        button = self.d.planner.find_final_submit(snapshot)
        if button is None:
            return self._handover("Could not find the final submit button")
        try:
            if snapshot.observation_id:
                await self.d.browser.authorize_submit(
                    browser_session, state["session_id"], snapshot.observation_id
                )
            result = await self.d.browser.act(
                browser_session,
                Action(type="click", target={"role": button.role, "name": button.name}),
            )
        except BrowserError:
            return self._handover(messages.SUBMIT_UNCERTAIN)
        if not result.ok:
            return self._handover(messages.SUBMIT_UNCERTAIN)
        snapshot = await self.d.browser.snapshot(browser_session)
        if not snapshot.receipt_number:
            return self._handover(messages.SUBMIT_UNCERTAIN)
        return {"route": "receipt", "receipt_number": snapshot.receipt_number}

    async def receipt(self, state: AgentState) -> dict[str, Any]:
        scheme = state.get("scheme") or {}
        number = state["receipt_number"]
        self.d.vault.put_receipt(
            state["owner"],
            Receipt(
                portal_id=state["portal_id"],
                scheme_id=scheme.get("scheme_id"),
                receipt_number=number,
                submitted_at=datetime.now(UTC),
            ),
        )
        text = messages.SUBMITTED.format(number=number)
        return {"outcome": "submitted", "final": {"text": text, "voice_text": text}}

    async def finish(self, state: AgentState) -> dict[str, Any]:
        if state.get("browser_session"):
            try:
                await self.d.browser.close(state["browser_session"])
            except BrowserError:
                pass
        return {"browser_session": None}
