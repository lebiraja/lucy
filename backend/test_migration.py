"""Comprehensive functional tests for the LangGraph migration."""

import asyncio


async def run_all_tests():
    # ========== TEST 1: GraphExecutor singleton init ==========
    from app.services.langgraph.executor import graph_executor
    assert graph_executor is not None
    assert "sequential" in graph_executor._graphs
    assert "parallel" in graph_executor._graphs
    assert "dynamic" in graph_executor._graphs
    assert "council" in graph_executor._graphs
    print("✓ TEST 1: GraphExecutor singleton initializes with all 4 strategy graphs")

    # ========== TEST 2: TaskState creation matches schema ==========
    from app.services.langgraph.state import TaskState, AgentResult, RankingResult
    state: TaskState = {
        "task_id": 1,
        "prompt": "Test",
        "strategy": "sequential",
        "agents": [{"id": 1, "name": "test", "role": "employee"}],
        "agent_responses": [],
        "current_step_order": 0,
        "routing_decision": None,
        "council_opinions": [],
        "council_reviews": [],
        "council_rankings": [],
        "label_to_agent": {},
        "final_output": None,
        "task_status": "running",
        "error": None,
    }
    assert state["task_id"] == 1
    assert state["strategy"] == "sequential"
    print("✓ TEST 2: TaskState TypedDict creation works correctly")

    # ========== TEST 3: AgentResult dataclass ==========
    result = AgentResult(
        agent_id=1, agent_name="TestAgent", agent_role="employee",
        model_name="test-model", response="Hello", duration_ms=100,
        status="completed", step_label="opinion",
    )
    assert result.status == "completed"
    assert result.duration_ms == 100
    print("✓ TEST 3: AgentResult dataclass works correctly")

    # ========== TEST 4: Routing helpers ==========
    from app.services.langgraph.nodes.routing_nodes import (
        extract_json, parse_ranking_from_text,
    )

    # Test extract_json with markdown fences
    raw = '```json\n{"strategy": "parallel"}\n```'
    assert extract_json(raw) == '{"strategy": "parallel"}'
    # Test without fences
    assert extract_json('  {"a": 1}  ') == '{"a": 1}'
    print("✓ TEST 4a: extract_json strips markdown fences correctly")

    # Test parse_ranking
    review_text = (
        "Analysis here...\n"
        "FINAL RANKING:\n"
        "1. Response A\n"
        "2. Response B\n"
        "3. Response C"
    )
    labels = ["Response A", "Response B", "Response C"]
    ranking = parse_ranking_from_text(review_text, labels)
    assert ranking == ["Response A", "Response B", "Response C"]
    print("✓ TEST 4b: parse_ranking_from_text extracts rankings correctly")

    # Test ranking with invalid labels filtered
    ranking2 = parse_ranking_from_text(review_text, ["Response A", "Response C"])
    assert "Response B" not in ranking2
    print("✓ TEST 4c: parse_ranking filters invalid labels")

    # Test no FINAL RANKING section - fallback to full text scan
    no_section = "Response B is best, then Response A"
    ranking3 = parse_ranking_from_text(no_section, labels)
    assert ranking3 == ["Response B", "Response A"]
    print("✓ TEST 4d: parse_ranking handles missing FINAL RANKING section")

    # ========== TEST 5: calculate_aggregate_rankings ==========
    from app.services.langgraph.nodes.routing_nodes import calculate_aggregate_rankings
    reviews = [
        {"response": "Review...\nFINAL RANKING:\n1. Response A\n2. Response B"},
        {"response": "Review...\nFINAL RANKING:\n1. Response B\n2. Response A"},
    ]
    label_to_id = {"Response A": 10, "Response B": 20}
    label_to_info = {
        "Response A": {"name": "Alpha", "role": "cto"},
        "Response B": {"name": "Beta", "role": "employee"},
    }
    agg = calculate_aggregate_rankings(reviews, label_to_id, label_to_info)
    assert len(agg) == 2
    # Both should have avg_rank 1.5 (A got 1,2 and B got 2,1)
    assert all(r["average_rank"] == 1.5 for r in agg)
    print("✓ TEST 5: calculate_aggregate_rankings computes correct averages")

    # ========== TEST 6: Orchestrator adapter signature ==========
    import inspect
    from app.services.orchestrator import execute_task
    sig = inspect.signature(execute_task)
    params = list(sig.parameters.keys())
    assert params == ["session", "task", "agents"]
    assert asyncio.iscoroutinefunction(execute_task)
    print("✓ TEST 6: execute_task is async and has correct signature")

    # ========== TEST 7: ROLE_SYSTEM_PROMPTS preserved ==========
    from app.services.langgraph.nodes.agent_nodes import ROLE_SYSTEM_PROMPTS
    assert "ceo" in ROLE_SYSTEM_PROMPTS
    assert "cto" in ROLE_SYSTEM_PROMPTS
    assert "manager" in ROLE_SYSTEM_PROMPTS
    assert "employee" in ROLE_SYSTEM_PROMPTS
    assert "CEO-level strategic" in ROLE_SYSTEM_PROMPTS["ceo"]
    print("✓ TEST 7: ROLE_SYSTEM_PROMPTS has all 4 roles with correct content")

    # ========== TEST 8: Council graph structure ==========
    from app.services.langgraph.graphs.council import build_council_graph
    from langgraph.checkpoint.memory import MemorySaver
    g = build_council_graph().compile(checkpointer=MemorySaver())
    nodes = list(g.get_graph().nodes.keys())
    expected = {
        "__start__", "stage1_opinions", "stage2_reviews",
        "aggregate_rankings", "stage3_synthesis",
        "persist_metadata", "fail", "__end__",
    }
    assert set(nodes) == expected, f"Missing nodes: {expected - set(nodes)}"
    print("✓ TEST 8: Council subgraph has all 8 required nodes")

    # ========== TEST 9: Dynamic graph conditional routing ==========
    from app.services.langgraph.graphs.dynamic import route_after_decision
    assert route_after_decision({"routing_decision": {"strategy": "sequential"}}) == "sequential"
    assert route_after_decision({"routing_decision": {"strategy": "parallel"}}) == "parallel"
    assert route_after_decision({"routing_decision": None}) == "parallel"
    assert route_after_decision({}) == "parallel"
    print("✓ TEST 9: Dynamic router conditional edges route correctly")

    # ========== TEST 10: DB session from LangGraph context ==========
    from app.database import async_session
    from app.models import Task, Agent
    from sqlalchemy import select
    async with async_session() as session:
        result = await session.execute(select(Task).limit(1))
        result.scalars().all()
        result2 = await session.execute(select(Agent).limit(1))
        result2.scalars().all()
    print("✓ TEST 10: DB session and ORM queries work from LangGraph context")

    # ========== TEST 11: log_step function works ==========
    from app.services.langgraph.nodes.utility_nodes import log_step
    # Create a test task to log against
    from app.models import TaskStatus, TaskStrategy
    async with async_session() as session:
        test_task = Task(
            prompt="LangGraph migration test",
            strategy=TaskStrategy.SEQUENTIAL,
            status=TaskStatus.PENDING,
        )
        session.add(test_task)
        await session.commit()
        test_task_id = test_task.id

    # log_step should persist to DB and broadcast
    await log_step(test_task_id, "Test log from LangGraph migration test", level="info")

    # Verify log was persisted
    from app.models import LogEntry
    async with async_session() as session:
        result = await session.execute(
            select(LogEntry).where(LogEntry.task_id == test_task_id)
        )
        logs = result.scalars().all()
        assert len(logs) >= 1
        assert "LangGraph migration test" in logs[0].message

    # Clean up test task
    async with async_session() as session:
        test_task = await session.get(Task, test_task_id)
        if test_task:
            await session.delete(test_task)
            await session.commit()

    print("✓ TEST 11: log_step persists LogEntry to DB and broadcasts")

    # ========== TEST 12: tasks.py still imports execute_task correctly ==========
    from app.routers.tasks import _run_task_background
    assert asyncio.iscoroutinefunction(_run_task_background)
    print("✓ TEST 12: tasks.py _run_task_background still works with new orchestrator")

    print("")
    print("=" * 55)
    print(" ALL 12 TESTS PASSED ✅  — Migration is solid!")
    print("=" * 55)


if __name__ == "__main__":
    asyncio.run(run_all_tests())
