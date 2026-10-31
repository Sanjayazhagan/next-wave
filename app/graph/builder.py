"""Wires the flow steps into a LangGraph graph with checkpoints."""
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from app.graph.nodes import Deps, Nodes
from app.graph.state import AgentState


def build_graph(deps: Deps, checkpointer: BaseCheckpointSaver) -> Any:
    nodes = Nodes(deps)
    plugins = deps.plugins
    graph = StateGraph(AgentState)

    for name in (
        "choose_language", "consent", "intake_think", "intake_listen", "ask_question",
        "confirm_details", "fix_details",
        "collect_documents", "extract_profile", "match_schemes", "choose_scheme", "doctor", "prepare_portal",
        "portal_login", "browser_step", "challenge", "ask_field", "handover",
        "save_skill", "prepare_review", "review", "edit", "submit", "receipt",
        "finish",
    ):
        graph.add_node(name, getattr(nodes, name))

    def after_language(state: AgentState) -> str:
        return "consent" if state.get("language") else "choose_language"

    def after_consent(state: AgentState) -> str:
        if state.get("final"):
            return "finish"
        return "intake_think" if state.get("consent") else "consent"

    def next_after_questions() -> str:
        return "match_schemes" if plugins.rules else "collect_documents"

    def after_think(state: AgentState) -> str:
        return {
            "listen": "intake_listen",
            "fallback": "ask_question",
        }.get(state["intake_route"], "confirm_details")

    def after_questions(state: AgentState) -> str:
        return "confirm_details" if state.get("questions_done") else "ask_question"

    def after_confirm(state: AgentState) -> str:
        choice = state.get("details_choice")
        if choice == "yes":
            return next_after_questions()
        return "fix_details" if choice == "change" else "confirm_details"

    def after_fix(state: AgentState) -> str:
        return "fix_details" if state.get("fix_error") else "confirm_details"

    def after_match(state: AgentState) -> str:
        if state.get("rules_failed"):
            return "collect_documents"  # Carries on with the default portal.
        return "finish" if state.get("final") else "choose_scheme"

    def after_choice(state: AgentState) -> str:
        return "collect_documents" if state.get("scheme") else "choose_scheme"

    def after_documents(state: AgentState) -> str:
        return "extract_profile" if state.get("documents_done") else "collect_documents"

    def after_extraction(state: AgentState) -> str:
        return "doctor" if plugins.doctor else "prepare_portal"

    def by_route(state: AgentState) -> str:
        return {
            "again": "browser_step",
            "login": "portal_login",
            "reopen": "prepare_portal",
            "challenge": "challenge",
            "ask_field": "ask_field",
            "handover": "handover",
            "reached_review": "save_skill",
            "receipt": "receipt",
            "stop": "finish",
        }[state["route"]]

    def after_review(state: AgentState) -> str:
        return {"approve": "submit", "edit": "edit"}.get(state.get("review_choice"), "review")

    def after_edit(state: AgentState) -> str:
        return "edit" if state.get("edit_error") else "prepare_portal"

    def after_field(state: AgentState) -> str:
        return "ask_field" if state.get("missing_field") else "browser_step"

    route_targets = [
        "browser_step", "portal_login", "prepare_portal", "challenge", "ask_field",
        "handover", "save_skill", "receipt", "finish",
    ]

    graph.add_edge(START, "choose_language" if deps.settings.choose_language else "consent")
    graph.add_conditional_edges("choose_language", after_language, ["choose_language", "consent"])
    graph.add_conditional_edges("consent", after_consent, ["consent", "intake_think", "finish"])
    graph.add_conditional_edges(
        "intake_think", after_think,
        ["intake_listen", "ask_question", "confirm_details"],
    )
    graph.add_edge("intake_listen", "intake_think")
    graph.add_conditional_edges("ask_question", after_questions, ["ask_question", "confirm_details"])
    graph.add_conditional_edges(
        "confirm_details", after_confirm,
        ["confirm_details", "fix_details", "match_schemes", "collect_documents"],
    )
    graph.add_conditional_edges("fix_details", after_fix, ["fix_details", "confirm_details"])
    graph.add_conditional_edges(
        "match_schemes", after_match, ["choose_scheme", "collect_documents", "finish"]
    )
    graph.add_conditional_edges(
        "choose_scheme", after_choice, ["choose_scheme", "collect_documents"]
    )
    graph.add_conditional_edges(
        "collect_documents", after_documents, ["collect_documents", "extract_profile"]
    )
    graph.add_conditional_edges("extract_profile", after_extraction, ["doctor", "prepare_portal"])
    graph.add_edge("doctor", "prepare_portal")
    for name in ("prepare_portal", "portal_login", "browser_step", "challenge", "handover", "submit"):
        graph.add_conditional_edges(name, by_route, route_targets)
    graph.add_conditional_edges("ask_field", after_field, ["ask_field", "browser_step"])
    graph.add_edge("save_skill", "prepare_review")
    graph.add_edge("prepare_review", "review")
    graph.add_conditional_edges("review", after_review, ["review", "submit", "edit"])
    graph.add_conditional_edges("edit", after_edit, ["edit", "prepare_portal"])
    graph.add_edge("receipt", "finish")
    graph.add_edge("finish", END)

    return graph.compile(checkpointer=checkpointer)
