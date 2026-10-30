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
        "consent", "collect_documents", "extract_profile", "ask_question",
        "match_schemes", "choose_scheme", "doctor", "prepare_portal",
        "portal_login", "browser_step", "challenge", "ask_field", "handover",
        "save_skill", "prepare_review", "review", "edit", "submit", "receipt",
        "finish",
    ):
        graph.add_node(name, getattr(nodes, name))

    def after_consent(state: AgentState) -> str:
        if state.get("final"):
            return "finish"
        return "collect_documents" if state.get("consent") else "consent"

    def after_documents(state: AgentState) -> str:
        return "extract_profile" if state.get("documents_done") else "collect_documents"

    def next_after_scheme() -> str:
        return "doctor" if plugins.doctor else "prepare_portal"

    def after_questions(state: AgentState) -> str:
        if not state.get("questions_done"):
            return "ask_question"
        return "match_schemes" if plugins.rules else next_after_scheme()

    def after_match(state: AgentState) -> str:
        return "finish" if state.get("final") else "choose_scheme"

    def after_choice(state: AgentState) -> str:
        return next_after_scheme() if state.get("scheme") else "choose_scheme"

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

    graph.add_edge(START, "consent")
    graph.add_conditional_edges("consent", after_consent, ["consent", "collect_documents", "finish"])
    graph.add_conditional_edges(
        "collect_documents", after_documents, ["collect_documents", "extract_profile"]
    )
    graph.add_edge("extract_profile", "ask_question")
    graph.add_conditional_edges(
        "ask_question", after_questions,
        ["ask_question", "match_schemes", "doctor", "prepare_portal"],
    )
    graph.add_conditional_edges("match_schemes", after_match, ["choose_scheme", "finish"])
    graph.add_conditional_edges(
        "choose_scheme", after_choice, ["choose_scheme", "doctor", "prepare_portal"]
    )
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
