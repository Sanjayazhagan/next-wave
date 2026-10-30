"""Fake portal and extraction, used until the real modules are merged.

Everything here is made up, so a run can be tried end to end with USE_STANDINS.
"""
import base64
import uuid

from app.browser import BrowserSessionLost
from contracts.browser import Action, ActionResult, Challenge, PageNode, Snapshot, Target
from contracts.documents import DocumentImage, ExtractedDocument, ExtractionResult
from contracts.profile import Profile, ProfileField

OTP = "123456"
CAPTCHA = "ABCD"
RECEIPT = "DEMO-0001"
# A 1x1 PNG, standing in for a cropped CAPTCHA image.
PIXEL_PNG = base64.b64encode(
    bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
        "0000000d49444154789c6360000002000001e221bc330000000049454e44ae426082"
    )
).decode()


class StubExtractor:
    async def __call__(self, images: list[DocumentImage]) -> ExtractionResult:
        fields = {
            "full_name": ProfileField(
                value="Demo Student", source_document="marksheet", confidence=0.97
            ),
            "date_of_birth": ProfileField(
                value="01-06-2006", source_document="marksheet", confidence=0.95
            ),
        }
        documents = [
            ExtractedDocument(document_type="marksheet", fields=fields, file_ref=image.file_ref)
            for image in images[:1]
        ]
        return ExtractionResult(profile=Profile(fields=fields), documents=documents)


class _Page:
    def __init__(self) -> None:
        self.step = "login"
        self.values: dict[str, str] = {}
        self.uploaded = False


class StubBrowser:
    """A small fake portal: login OTP, a form, a CAPTCHA, review, then a receipt."""

    def __init__(self) -> None:
        self.sessions: dict[str, _Page] = {}
        self.renames: dict[str, str] = {}
        self.final_submits = 0

    def _name(self, name: str) -> str:
        return self.renames.get(name, name)

    def _page(self, session_id: str) -> _Page:
        if session_id not in self.sessions:
            raise BrowserSessionLost(session_id)
        return self.sessions[session_id]

    async def open(self, portal_id: str) -> str:
        session_id = uuid.uuid4().hex
        self.sessions[session_id] = _Page()
        return session_id

    async def login(self, session_id: str, portal_user_id: str) -> Snapshot:
        self._page(session_id).step = "otp"
        return await self.snapshot(session_id)

    async def snapshot(self, session_id: str) -> Snapshot:
        page = self._page(session_id)
        url = f"https://portal.example/{page.step}"
        if page.step == "otp":
            challenge = Challenge(
                kind="otp",
                input=Target(role="textbox", name="OTP"),
                submit=Target(role="button", name="Verify"),
            )
            return Snapshot(url=url, title="Login", challenge=challenge)
        if page.step == "captcha":
            challenge = Challenge(
                kind="captcha",
                input=Target(role="textbox", name="Captcha"),
                submit=Target(role="button", name="Check"),
                image_base64=PIXEL_PNG,
            )
            return Snapshot(url=url, title="Security check", challenge=challenge)
        if page.step == "form":
            nodes = [
                PageNode(
                    ref=f"n{index}",
                    role="textbox",
                    name=self._name(label),
                    value=page.values.get(label, ""),
                )
                for index, label in enumerate(
                    ["Full name", "Date of birth", "Annual income"]
                )
            ]
            nodes.append(PageNode(ref="n3", role="button", name=self._name("Upload marksheet")))
            nodes.append(PageNode(ref="n4", role="button", name=self._name("Continue")))
            return Snapshot(url=url, title="Application form", nodes=nodes)
        if page.step == "review":
            summary = [
                PageNode(ref=f"r{i}", role="text", name=label, value=value)
                for i, (label, value) in enumerate(page.values.items())
            ]
            final = PageNode(ref="r9", role="button", name="Final submit")
            return Snapshot(url=url, title="Review", nodes=[*summary, final])
        return Snapshot(url=url, title="Done", receipt_number=RECEIPT)

    async def act(self, session_id: str, action: Action) -> ActionResult:
        page = self._page(session_id)
        if action.type == "wait":
            return ActionResult(ok=True)
        name = action.target.name if action.target else ""
        labels = {self._name(label): label for label in self._labels(page)}
        if name not in labels:
            return ActionResult(ok=False, error=f"No element named {name}")
        label = labels[name]

        if page.step == "otp":
            return self._answer_challenge(page, label, action, OTP, "form")
        if page.step == "captcha":
            return self._answer_challenge(page, label, action, CAPTCHA, "review")
        if page.step == "form":
            return self._use_form(page, label, action)
        if page.step == "review" and label == "Final submit":
            self.final_submits += 1
            page.step = "receipt"
            return ActionResult(ok=True)
        return ActionResult(ok=False, error="Nothing to do here")

    @staticmethod
    def _labels(page: _Page) -> list[str]:
        return {
            "otp": ["OTP", "Verify"],
            "captcha": ["Captcha", "Check"],
            "form": [
                "Full name", "Date of birth", "Annual income",
                "Upload marksheet", "Continue",
            ],
            "review": ["Final submit"],
        }.get(page.step, [])

    @staticmethod
    def _answer_challenge(
        page: _Page, label: str, action: Action, answer: str, next_step: str
    ) -> ActionResult:
        if action.type == "type":
            page.values["_answer"] = action.value or ""
            return ActionResult(ok=True)
        if page.values.pop("_answer", "") == answer:
            page.step = next_step
        return ActionResult(ok=True)

    @staticmethod
    def _use_form(page: _Page, label: str, action: Action) -> ActionResult:
        if action.type == "type":
            page.values[label] = action.value or ""
            return ActionResult(ok=True)
        if action.type == "upload":
            page.uploaded = True
            return ActionResult(ok=True)
        if label == "Continue":
            page.step = "captcha"
        return ActionResult(ok=True)

    async def close(self, session_id: str) -> None:
        self.sessions.pop(session_id, None)
