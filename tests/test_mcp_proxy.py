"""MCP proxy routing with a fake upstream PayPal MCP server backed by the simulator."""

import json
from decimal import Decimal

import pytest
from mcp.types import CallToolRequestParams, CallToolResult, TextContent, Tool

from agentguard.demo_world import seed
from agentguard.guard import HeuristicDetector
from agentguard.mcp_proxy import GuardedPayPalServer
from agentguard.paypal import PayPalSimulator
from agentguard.store import Store

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _tool(name: str) -> Tool:
    return Tool(name=name, description=f"{name} tool", input_schema={"type": "object", "properties": {}})


class FakeUpstream:
    """Stands in for @paypal/mcp: same tool names, executes refunds on the simulator."""

    def __init__(self, paypal: PayPalSimulator):
        self.paypal = paypal
        self.calls: list[str] = []

    async def list_tools(self):
        names = ["get_order", "create_refund", "accept_dispute_claim", "list_transactions"]
        return type("R", (), {"tools": [_tool(n) for n in names]})()

    async def call_tool(self, name: str, args: dict) -> CallToolResult:
        self.calls.append(name)
        if name == "create_refund":
            refund = self.paypal.refund_capture(
                args["capture_id"], Decimal(args["amount"]["value"]), "USD", "", f"fake-{len(self.calls)}"
            )
            body = {"id": refund.refund_id, "status": "COMPLETED", "amount": {"value": str(refund.amount)}}
        else:
            body = {"tool": name, "args": args}
        return CallToolResult(content=[TextContent(type="text", text=json.dumps(body))])


class SimRest:
    """The REST reads the proxy does, served by the simulator."""

    def __init__(self, paypal: PayPalSimulator):
        self.paypal = paypal

    def get_order(self, order_id):
        return self.paypal.get_order(order_id)

    def order_for_capture(self, capture_id):
        return self.paypal._by_capture.get(capture_id)


@pytest.fixture
async def proxy(monkeypatch):
    monkeypatch.setattr("agentguard.mcp_proxy.default_detector", HeuristicDetector)
    paypal = PayPalSimulator()
    store = Store(":memory:")
    world = seed(paypal, store)
    upstream = FakeUpstream(paypal)
    server = GuardedPayPalServer(upstream, SimRest(paypal), store, customer_id=None)
    server.guard.paypal.rest = SimRest(paypal)
    await server.load_tools()
    return server, upstream, paypal, world


async def call(server, name, args):
    result = await server.call_tool(None, CallToolRequestParams(name=name, arguments=args))
    text = "".join(c.text for c in result.content)
    return result.is_error, json.loads(text)


async def test_refund_tool_is_marked_and_extended(proxy):
    server, *_ = proxy
    refund = server.tools["create_refund"]
    assert refund.description.startswith("[Guarded by AgentGuard]")
    assert {"reason", "customer_claim"} <= set(refund.input_schema["properties"])
    assert server.tools["accept_dispute_claim"].description.startswith("[AgentGuard: requires a human")


async def test_reads_pass_through(proxy):
    server, upstream, _, world = proxy
    error, body = await call(server, "get_order", {"id": world.order_id("alex_mug")})
    assert not error and body["tool"] == "get_order" and upstream.calls == ["get_order"]


async def test_allowed_refund_is_executed_by_upstream_toolkit(proxy):
    server, upstream, paypal, world = proxy
    capture = paypal.get_order(world.order_id("sarah_beans")).capture_id
    amount = {"currency_code": "USD", "value": "34.00"}
    error, body = await call(server, "create_refund", {"capture_id": capture, "amount": amount})
    assert not error and body["status"] == "COMPLETED"
    assert upstream.calls == ["create_refund"]
    assert paypal.get_order(world.order_id("sarah_beans")).refundable == 0


async def test_over_refund_never_reaches_upstream(proxy):
    server, upstream, paypal, world = proxy
    capture = paypal.get_order(world.order_id("alex_mug")).capture_id
    amount = {"currency_code": "USD", "value": "60.00"}
    error, body = await call(server, "create_refund", {"capture_id": capture, "amount": amount})
    assert error and body["status"] == "DECLINED" and "refundable_amount" in body["flagged_checks"]
    assert upstream.calls == []


async def test_large_refund_waits_for_owner(proxy):
    server, upstream, paypal, world = proxy
    capture = paypal.get_order(world.order_id("priya_grinder")).capture_id
    amount = {"currency_code": "USD", "value": "149.00"}
    error, body = await call(server, "create_refund", {"capture_id": capture, "amount": amount})
    assert not error and body["status"] == "PENDING_REVIEW"
    assert upstream.calls == []


async def test_dispute_acceptance_needs_a_human(proxy):
    server, upstream, *_ = proxy
    error, body = await call(server, "accept_dispute_claim", {"dispute_id": "PP-D-1", "note": "x"})
    assert error and body["status"] == "DECLINED"
    assert upstream.calls == [] and server.store.tickets()
