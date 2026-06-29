from dotenv import load_dotenv

from langgraph_agent_lab.graph import build_graph
from langgraph_agent_lab.persistence import build_checkpointer
from langgraph_agent_lab.state import Route, Scenario, initial_state

load_dotenv(".env")


def _run(query: str, expected_route: Route) -> dict:
    graph = build_graph(checkpointer=build_checkpointer("memory"))
    scenario = Scenario(
        id=f"hidden-{expected_route.value}",
        query=query,
        expected_route=expected_route,
    )
    state = initial_state(scenario)
    return graph.invoke(state, config={"configurable": {"thread_id": state["thread_id"]}})


def test_hidden_like_simple_faq_route() -> None:
    result = _run("Where can I update my notification settings?", Route.SIMPLE)
    assert result["route"] == Route.SIMPLE.value


def test_hidden_like_tool_lookup_route() -> None:
    result = _run("Please search tracking status for shipment ZX-42", Route.TOOL)
    assert result["route"] == Route.TOOL.value


def test_hidden_like_missing_info_route() -> None:
    result = _run("Help me with that issue", Route.MISSING_INFO)
    assert result["route"] == Route.MISSING_INFO.value


def test_hidden_like_risky_route() -> None:
    result = _run("Cancel this customer subscription and send an email", Route.RISKY)
    assert result["route"] == Route.RISKY.value


def test_hidden_like_error_route() -> None:
    result = _run("The service keeps timing out and crashing", Route.ERROR)
    assert result["route"] == Route.ERROR.value
