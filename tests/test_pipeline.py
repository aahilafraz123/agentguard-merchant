"""LangGraph-specific behaviour: interrupts, durable resume and operator sessions."""

from decimal import Decimal

from agentguard.demo_world import seed
from agentguard.guard import AgentGuard, HeuristicDetector, Outcome, RefundRequest, SessionContext
from agentguard.paypal import PayPalSimulator
from agentguard.store import Store


def _request(order_id, amount, reason="damaged"):
    return RefundRequest(order_id=order_id, amount=Decimal(amount), reason=reason, customer_claim="broken")


def test_escalation_pauses_graph_and_survives_restart(tmp_path):
    """A paused review is checkpointed; a new guard process can resume it."""
    paypal, store = PayPalSimulator(), Store(tmp_path / "ag.db")
    world = seed(paypal, store)
    first = AgentGuard(paypal, store, HeuristicDetector())
    oid = world.order_id("priya_grinder")
    context = SessionContext(session_id="s", customer_id="c_priya", customer_messages=["dead"])
    decision = first.submit(_request(oid, "149"), context)
    assert decision.outcome == Outcome.ESCALATE and decision.status == "pending"
    row = store.get_decision(decision.id)
    snapshot = first.graph.get_state({"configurable": {"thread_id": row["thread_id"]}})
    assert snapshot.next == ("human_review",)

    restarted = AgentGuard(paypal, Store(tmp_path / "ag.db"), HeuristicDetector())
    approved = restarted.approve(decision.id, reviewer="owner", note="photo checked")
    assert approved["status"] == "approved" and approved["resolved_by"] == "owner"
    assert paypal.get_order(oid).refundable == 0


def test_denied_review_moves_no_money():
    paypal, store = PayPalSimulator(), Store(":memory:")
    world = seed(paypal, store)
    guard = AgentGuard(paypal, store, HeuristicDetector())
    oid = world.order_id("marcus_sampler")
    d = guard.submit(
        _request(oid, "48", "not_received"),
        SessionContext(session_id="s", customer_id="c_marcus", customer_messages=["never came"]),
    )
    row = guard.deny(d.id, note="tracking shows delivered")
    assert row["status"] == "denied" and row["resolved_note"] == "tracking shows delivered"
    assert paypal.get_order(oid).refunded == 0


def test_operator_session_skips_ownership_but_keeps_limits():
    """MCP operator sessions have no signed-in customer; every other check still applies."""
    paypal, store = PayPalSimulator(), Store(":memory:")
    world = seed(paypal, store)
    guard = AgentGuard(paypal, store, HeuristicDetector())
    operator = SessionContext(session_id="mcp", customer_id=None, channel="mcp")
    small = guard.submit(_request(world.order_id("sarah_beans"), "34", "changed_mind"), operator)
    big = guard.submit(_request(world.order_id("priya_grinder"), "149"), operator)
    too_much = guard.submit(_request(world.order_id("alex_mug"), "50"), operator)
    assert small.status == "executed"
    assert big.outcome == Outcome.ESCALATE
    assert too_much.outcome == Outcome.BLOCK
    assert store.get_decision(small.id)["mode"] == "mcp"
    assert store.get_decision(small.id)["customer_id"] == "c_sarah"  # from PayPal custom_id


def test_graph_has_the_documented_nodes():
    guard = AgentGuard(PayPalSimulator(), Store(":memory:"), HeuristicDetector())
    diagram = guard.mermaid()
    nodes = ("load_evidence", "assess_risk", "check_policy", "record", "human_review", "recheck", "execute")
    assert all(node in diagram for node in nodes)
