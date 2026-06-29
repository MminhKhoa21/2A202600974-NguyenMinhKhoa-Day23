"""Node functions for the LangGraph workflow.

Each function receives AgentState and returns a partial state update dict.
Do NOT mutate input state — return new values only.

LLM REQUIREMENT:
- classify_node MUST use a real LLM call (structured output for intent classification)
- answer_node MUST use a real LLM call (grounded response generation)
- evaluate_node SHOULD use LLM-as-judge (bonus points; heuristic acceptable for base score)
"""

from __future__ import annotations

import os

from pydantic import BaseModel, Field

from .llm import get_llm
from .state import AgentState, make_event


class ClassificationResult(BaseModel):
    route: str = Field(pattern="^(simple|tool|missing_info|risky|error)$")
    risk_level: str = Field(pattern="^(low|high)$")
    reason: str = ""


class EvaluationResult(BaseModel):
    evaluation_result: str = Field(pattern="^(success|needs_retry)$")
    rationale: str = ""


def _heuristic_route(query: str) -> ClassificationResult:
    text = query.lower()
    if any(keyword in text for keyword in ("refund", "delete", "cancel", "send email", "email")):
        return ClassificationResult(route="risky", risk_level="high")
    if any(
        keyword in text for keyword in ("lookup", "look up", "status", "tracking", "search", "find")
    ):
        return ClassificationResult(route="tool", risk_level="low")
    if any(keyword in text for keyword in ("timeout", "failure", "crash", "error", "unavailable")):
        return ClassificationResult(
            route="error",
            risk_level="low",
            reason="explicit outage/error language",
        )
    if len(text.split()) <= 4 or any(
        phrase in text for phrase in ("fix it", "help me", "can you fix")
    ):
        return ClassificationResult(
            route="missing_info",
            risk_level="low",
            reason="request is too vague",
        )
    if text.startswith("how do i") or text.startswith("how to") or text.startswith("where can i"):
        return ClassificationResult(route="simple", risk_level="low", reason="faq-style question")
    return ClassificationResult(route="simple", risk_level="low", reason="general support question")


def _has_strong_policy_pattern(query: str, route: str) -> bool:
    text = query.lower()
    route_patterns = {
        "risky": ("refund", "delete", "cancel", "send email", "email"),
        "tool": ("lookup", "look up", "tracking", "order status", "search", "find"),
        "missing_info": ("fix it", "help me", "can you fix"),
        "error": ("timeout", "failure", "crash", "service unavailable", "cannot recover"),
        "simple": ("how do i", "how to", "where can i", "reset my password"),
    }
    return any(pattern in text for pattern in route_patterns.get(route, ()))


def _reconcile_route(
    query: str,
    llm_result: ClassificationResult,
    heuristic_result: ClassificationResult,
) -> ClassificationResult:
    # Keep the LLM as the primary classifier and only correct clear policy-critical misses.
    if (
        heuristic_result.route in {"risky", "error", "missing_info"}
        and llm_result.route != heuristic_result.route
        and _has_strong_policy_pattern(query, heuristic_result.route)
    ):
        return heuristic_result
    if (
        heuristic_result.route == "simple"
        and llm_result.route in {"tool", "risky"}
        and _has_strong_policy_pattern(query, "simple")
    ):
        return heuristic_result
    if (
        heuristic_result.route == "tool"
        and llm_result.route == "simple"
        and _has_strong_policy_pattern(query, "tool")
    ):
        return heuristic_result
    return llm_result


# ─── EXAMPLE: working node (provided for reference) ──────────────────
def intake_node(state: AgentState) -> dict:
    """Normalize raw query. This node is provided as a working example."""
    query = state.get("query", "").strip()
    return {
        "query": query,
        "messages": [f"intake:{query[:40]}"],
        "events": [make_event("intake", "completed", "query normalized")],
    }


# ─── TODO(student): implement ALL nodes below ────────────────────────


def classify_node(state: AgentState) -> dict:
    """Classify the query into a route using an LLM.

    *** MUST use a real LLM call — keyword-only heuristics will lose points. ***

    Use .with_structured_output() or equivalent to get reliable enum classification.
    The LLM should classify into one of: simple, tool, missing_info, risky, error.

    Hints:
    - See llm.py for the get_llm() helper
    - Use Pydantic model or TypedDict with .with_structured_output()
    - Set risk_level to "high" for risky routes, "low" otherwise
    - Priority guide: risky > tool > missing_info > error > simple

    Return: {"route": str, "risk_level": str, "events": [make_event(...)]}
    """
    query = state.get("query", "").strip()
    heuristic_result = _heuristic_route(query)
    try:
        llm = get_llm(temperature=0.0)
        structured_llm = llm.with_structured_output(ClassificationResult)
        llm_result = structured_llm.invoke(
            "Classify the support request into exactly one route.\n"
            "Priority order: risky > tool > missing_info > error > simple.\n"
            "Routes:\n"
            "- risky: refunds, deletions, cancellations, emails, or any side-effectful action.\n"
            "- tool: information lookup or retrieval.\n"
            "- missing_info: vague request missing actionable context.\n"
            "- error: system failure, timeout, crash, or outage.\n"
            "- simple: general support question answerable directly.\n"
            "Return risk_level='high' only for risky, otherwise 'low'.\n"
            "Also include a short reason that cites the request pattern you used.\n"
            "Do not guess hidden actions or risks that are not stated in the request.\n\n"
            f"Query: {query}"
        )
    except Exception:
        llm_result = heuristic_result

    result = _reconcile_route(query, llm_result, heuristic_result)

    return {
        "route": result.route,
        "risk_level": result.risk_level,
        "classification_reason": result.reason or f"final route={result.route}",
        "messages": [f"classify:{result.route}"],
        "events": [
            make_event(
                "classify",
                "completed",
                "route classified",
                route=result.route,
                llm_route=llm_result.route,
                heuristic_route=heuristic_result.route,
                reason=result.reason,
            )
        ],
    }


def tool_node(state: AgentState) -> dict:
    """Execute a mock tool call.

    Simulate transient failures for error-route scenarios to test retry loops.

    Requirements:
    - Read current attempt count from state
    - If route is "error" and attempt < 2: return error result (string containing "ERROR")
    - Otherwise: return a mock success result string
    - Append result to tool_results list

    Return: {"tool_results": [result_string], "events": [make_event(...)]}
    """
    route = str(state.get("route", ""))
    attempt = int(state.get("attempt", 0))
    query = state.get("query", "")
    proposed_action = state.get("proposed_action")

    if route == "error" and attempt < 2:
        result = f"ERROR: transient backend failure while handling request '{query}'"
        event_type = "failed"
    elif route == "risky":
        result = f"SUCCESS: approved action executed. {proposed_action or query}"
        event_type = "completed"
    else:
        result = f"SUCCESS: tool result for '{query}'"
        event_type = "completed"

    return {
        "tool_results": [result],
        "events": [make_event("tool", event_type, "tool call finished", result=result)],
    }


def evaluate_node(state: AgentState) -> dict:
    """Evaluate tool results — the retry-loop gate.

    Check whether the latest tool result is satisfactory or needs retry.

    SHOULD use LLM-as-judge for bonus points. Heuristic (e.g., check for "ERROR" substring)
    is acceptable for base score.

    Requirements:
    - Read the latest entry from tool_results
    - Set evaluation_result to "needs_retry" or "success"
    - This field drives route_after_evaluate conditional edge

    Note: You may need to add 'evaluation_result' to AgentState if not present.

    Return: {"evaluation_result": str, "events": [make_event(...)]}
    """
    latest = (state.get("tool_results") or [""])[-1]
    normalized = latest.upper()
    if normalized.startswith("SUCCESS:"):
        evaluation_result = "success"
        rationale = "deterministic success prefix"
    elif "ERROR" in normalized:
        evaluation_result = "needs_retry"
        rationale = "deterministic error marker"
    else:
        try:
            llm = get_llm(temperature=0.0)
            judge = llm.with_structured_output(EvaluationResult)
            result = judge.invoke(
                "You are evaluating whether a support tool result is usable.\n"
                "Return `needs_retry` only when the result clearly indicates a transient failure, "
                "timeout, backend error, or unusable output. Otherwise return `success`.\n\n"
                f"Tool result: {latest}"
            )
            evaluation_result = result.evaluation_result
            rationale = result.rationale
        except Exception:
            evaluation_result = "needs_retry" if "ERROR" in latest.upper() else "success"
            rationale = "heuristic fallback"
    return {
        "evaluation_result": evaluation_result,
        "events": [
            make_event(
                "evaluate",
                "completed",
                "tool result evaluated",
                evaluation_result=evaluation_result,
                rationale=rationale,
            )
        ],
    }


def answer_node(state: AgentState) -> dict:
    """Generate a final response using an LLM.

    *** MUST use a real LLM call — hardcoded strings will lose points. ***

    The LLM should generate a helpful response grounded in available context:
    - tool_results (if any)
    - approval decision (if risky route)
    - original query

    Return: {"final_answer": str, "events": [make_event(...)]}
    """
    query = state.get("query", "")
    tool_results = state.get("tool_results") or []
    approval = state.get("approval")
    route = state.get("route", "")
    latest_tool_result = tool_results[-1] if tool_results else "No tool result available."

    prompt = (
        "You are a helpful support agent. Answer the user using only the provided context.\n"
        "Be concise, accurate, and mention uncertainty instead of inventing details.\n"
        "Do not add facts that are not supported by the context below.\n\n"
        f"Route: {route}\n"
        f"Original query: {query}\n"
        f"Latest tool result: {latest_tool_result}\n"
        f"Approval context: {approval}\n"
        f"Errors: {state.get('errors') or []}\n"
    )
    try:
        llm = get_llm(temperature=0.2)
        response = llm.invoke(prompt)
        final_answer = getattr(response, "content", str(response)).strip()
    except Exception:
        if route == "simple":
            final_answer = (
                "I can help with that. Based on your request, "
                f"please follow the standard support steps for: {query}"
            )
        elif route in {"tool", "risky", "error"}:
            final_answer = f"Here is the current result for your request: {latest_tool_result}"
        else:
            final_answer = f"I need a bit more context before I can answer your request: {query}"

    return {
        "final_answer": final_answer,
        "events": [make_event("answer", "completed", "final answer generated")],
    }


def ask_clarification_node(state: AgentState) -> dict:
    """Ask for missing information instead of hallucinating.

    Generate a specific clarification question based on the vague/incomplete query.

    Note: You may need to add 'pending_question' to AgentState if not present.

    Return: {"pending_question": str, "final_answer": str, "events": [make_event(...)]}
    """
    query = state.get("query", "")
    pending_question = (
        f"Could you share a bit more detail about '{query}'? "
        "For example, include the account, order, or specific issue you want me to act on."
    )
    return {
        "pending_question": pending_question,
        "final_answer": pending_question,
        "events": [make_event("clarify", "completed", "clarification requested")],
    }


def risky_action_node(state: AgentState) -> dict:
    """Prepare a risky action for human approval.

    Describe the proposed action and why it requires approval.

    Note: You may need to add 'proposed_action' to AgentState if not present.

    Return: {"proposed_action": str, "events": [make_event(...)]}
    """
    query = state.get("query", "")
    proposed_action = (
        f"Proposed high-risk action for review: {query}. "
        "This request may change customer data or trigger an external side effect."
    )
    return {
        "proposed_action": proposed_action,
        "events": [make_event("risky_action", "completed", "risky action prepared")],
    }


def approval_node(state: AgentState) -> dict:
    """Human-in-the-loop approval step.

    Default behavior: mock approval (approved=True) so tests and CI run offline.
    Extension: if env LANGGRAPH_INTERRUPT=true, use langgraph.types.interrupt() for real HITL.

    Return: approval payload plus an audit event.
    """
    if os.getenv("LANGGRAPH_INTERRUPT", "").lower() == "true":
        from langgraph.types import interrupt

        payload = interrupt(
            {
                "query": state.get("query"),
                "proposed_action": state.get("proposed_action"),
                "thread_id": state.get("thread_id"),
            }
        )
        approval = {
            "approved": bool(payload.get("approved", False)),
            "reviewer": payload.get("reviewer", "human-reviewer"),
            "comment": payload.get("comment", ""),
        }
    else:
        approval = {
            "approved": True,
            "reviewer": "mock-reviewer",
            "comment": "Auto-approved for offline lab execution.",
        }

    return {
        "approval": approval,
        "events": [
            make_event(
                "approval",
                "completed",
                "approval decision recorded",
                approved=approval["approved"],
            )
        ],
    }


def retry_or_fallback_node(state: AgentState) -> dict:
    """Record a retry attempt.

    Increment the attempt counter and log the transient failure.

    Requirements:
    - Read current attempt from state, increment by 1
    - Add an error message to errors list
    - Return updated attempt count

    Return: {"attempt": int, "errors": [str], "events": [make_event(...)]}
    """
    next_attempt = int(state.get("attempt", 0)) + 1
    error_message = f"Retry requested after unsuccessful tool evaluation. attempt={next_attempt}"
    return {
        "attempt": next_attempt,
        "errors": [error_message],
        "events": [
            make_event(
                "retry",
                "completed",
                "retry attempt recorded",
                attempt=next_attempt,
            )
        ],
    }


def dead_letter_node(state: AgentState) -> dict:
    """Handle unresolvable failures after max retries exceeded.

    This is the third layer: retry → fallback → dead letter.
    Log the failure and set a final_answer explaining that the request could not be completed.

    Return: {"final_answer": str, "events": [make_event(...)]}
    """
    final_answer = (
        "I could not complete this request after the allowed retry attempts. "
        "Please escalate to a human operator or try again later."
    )
    return {
        "final_answer": final_answer,
        "events": [make_event("dead_letter", "completed", "request moved to dead letter queue")],
    }


def finalize_node(state: AgentState) -> dict:
    """Emit a final audit event. All routes must pass through here before END.

    Return: {"events": [make_event("finalize", "completed", "workflow finished")]}
    """
    return {"events": [make_event("finalize", "completed", "workflow finished")]}
