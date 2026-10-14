"""Bounded LangGraph investigation workflow.

Graph shape::

    interpret ──> plan ──(call_tool)──> act ──> plan ... (bounded loop)
                    └──(finish / limits reached)──> analyze ──> END

Bounds enforced structurally:
- ``max_steps`` tool-call ceiling (conditional edge, not model goodwill);
- per-tool timeout + retry budget (ToolExecutor);
- failed-call budget: repeated tool failures short-circuit to analysis;
- LangGraph recursion_limit as a final backstop.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

from langgraph.graph import END, StateGraph

from .planner import Planner, PlannerDecision
from .state import AgentState
from .tools import ToolExecutor

logger = logging.getLogger("cloudops.agent.graph")

MAX_FAILED_CALLS = 3

PersistHook = Callable[[AgentState], None]


def build_graph(
    planner: Planner,
    executor: ToolExecutor,
    simulated: bool,
    persist: PersistHook | None = None,
):
    """Compile the investigation graph for one run."""

    def _persist(state: AgentState) -> None:
        if persist is not None:
            persist(state)

    def interpret(state: AgentState) -> AgentState:
        # Normalize working fields; resource/time window were resolved upstream
        # (scenario or request). The planner handles a missing resource.
        state.setdefault("steps", [])
        state.setdefault("evidence", [])
        state.setdefault("step_count", 0)
        state.setdefault("failed_tool_calls", 0)
        _persist(state)
        return state

    def plan(state: AgentState) -> AgentState:
        try:
            decision = planner.decide(state)
        except Exception as exc:
            logger.exception("Planner failure")
            state["decision"] = PlannerDecision(
                action="finish",
                reasoning=f"Planner unavailable ({type(exc).__name__}); finishing with collected evidence.",
            ).model_dump()
            return state
        state["decision"] = decision.model_dump()
        return state

    def should_act(state: AgentState) -> str:
        decision = state.get("decision") or {}
        if decision.get("action") != "call_tool":
            return "analyze"
        if state.get("step_count", 0) >= state.get("max_steps", 8):
            logger.info("Step limit reached; moving to analysis")
            return "analyze"
        if state.get("failed_tool_calls", 0) >= MAX_FAILED_CALLS:
            logger.info("Failed-call budget exhausted; moving to analysis")
            return "analyze"
        return "act"

    def act(state: AgentState) -> AgentState:
        decision = state["decision"] or {}
        tool = decision.get("tool", "")
        args = decision.get("args", {}) or {}
        step, evidence = executor.execute(tool, args, step_index=len(state["steps"]))
        state["steps"].append(json.loads(step.model_dump_json()))
        state["evidence"].extend(json.loads(e.model_dump_json()) for e in evidence)
        state["step_count"] = state.get("step_count", 0) + 1
        if step.status == "failed":
            state["failed_tool_calls"] = state.get("failed_tool_calls", 0) + 1
        _persist(state)
        return state

    def analyze(state: AgentState) -> AgentState:
        try:
            report = planner.write_report(state, simulated)
        except Exception as exc:
            logger.exception("Report generation failed; falling back to deterministic analyzer")
            from .analysis import build_report

            report = build_report(
                state["question"], state.get("evidence", []), state.get("steps", []), simulated
            )
            report.limitations.append(
                f"The configured LLM report writer failed ({type(exc).__name__}); "
                "this report uses the deterministic analyzer."
            )
        state["report"] = json.loads(report.model_dump_json())
        _persist(state)
        return state

    graph = StateGraph(AgentState)
    graph.add_node("interpret", interpret)
    graph.add_node("plan", plan)
    graph.add_node("act", act)
    graph.add_node("analyze", analyze)
    graph.set_entry_point("interpret")
    graph.add_edge("interpret", "plan")
    graph.add_conditional_edges("plan", should_act, {"act": "act", "analyze": "analyze"})
    graph.add_edge("act", "plan")
    graph.add_edge("analyze", END)
    return graph.compile()


def run_investigation_graph(
    planner: Planner,
    executor: ToolExecutor,
    initial_state: AgentState,
    simulated: bool,
    persist: PersistHook | None = None,
) -> AgentState:
    compiled = build_graph(planner, executor, simulated, persist)
    # Recursion backstop: interpret + N*(plan+act) + plan + analyze.
    limit = 4 + 2 * int(initial_state.get("max_steps", 8)) + 4
    result: dict[str, Any] = compiled.invoke(initial_state, config={"recursion_limit": limit})
    return result  # type: ignore[return-value]
