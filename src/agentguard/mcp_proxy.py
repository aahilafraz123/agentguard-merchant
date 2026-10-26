"""AgentGuard as an MCP security proxy in front of PayPal's MCP server.

Any MCP client (Claude Desktop, Claude Code, an agent framework) connects to this server
instead of PayPal's. It launches PayPal's official MCP server (`@paypal/mcp`, built on the
PayPal Agent Toolkit) as a subprocess and re-exposes its tools:

* read tools (get_order, list_transactions, ...) pass straight through;
* `create_refund` runs through the AgentGuard LangGraph pipeline first. Allowed refunds are
  executed by the Agent Toolkit's own `create_refund`; escalated ones wait in the console's
  review queue; blocked ones never reach PayPal;
* irreversible actions with no amount to check (accepting dispute claims, cancelling
  subscriptions) are refused and logged for a human.

    uv run agentguard-mcp                      # operator session (merchant's own agent)
    AGENTGUARD_CUSTOMER_ID=c_alex uv run agentguard-mcp   # bound to one storefront customer

Needs PAYPAL_CLIENT_ID / PAYPAL_CLIENT_SECRET (sandbox) and Node 18+ for npx.
"""

from __future__ import annotations

import copy
import json
import logging
import os
import sys
import uuid
from decimal import Decimal, InvalidOperation
from typing import Any

import anyio
import anyio.from_thread
import anyio.to_thread
from mcp import Client, StdioServerParameters
from mcp.server import Server, ServerRequestContext
from mcp.server.stdio import stdio_server
from mcp.types import (
    CallToolRequestParams,
    CallToolResult,
    ListToolsResult,
    PaginatedRequestParams,
    TextContent,
    Tool,
)

from . import __version__
from .config import settings
from .guard import AgentGuard, Outcome, RefundRequest, SessionContext, default_detector
from .guard.models import RefundReason
from .paypal import PayPalError, PayPalRestClient, RefundRecord
from .store import Store

log = logging.getLogger("agentguard.mcp")

PAYPAL_MCP_PACKAGE = "@paypal/mcp@1.8.1"
GUARDED_REFUND = "create_refund"
HUMAN_ONLY = {
    "accept_dispute_claim": "Accepting a dispute claim gives up the money and can't be undone.",
    "cancel_subscription": "Cancelling a subscription ends a customer's recurring payments.",
    "cancel_sent_invoice": "Cancelling a sent invoice voids money the customer owes.",
}
REASONS = list(RefundReason.__args__)


def _text(payload: Any, *, error: bool = False) -> CallToolResult:
    body = payload if isinstance(payload, str) else json.dumps(payload, default=str)
    return CallToolResult(content=[TextContent(type="text", text=body)], is_error=error)


def _result_text(result: CallToolResult) -> str:
    return "".join(c.text for c in result.content if getattr(c, "type", "") == "text")


class ToolkitRefunds:
    """PayPal gateway for the guard: reads go to the REST API, refunds go through the Agent Toolkit.

    The guard runs in a worker thread; refunds hop back to the event loop to call the
    upstream MCP server.
    """

    mode = "sandbox"

    def __init__(self, rest: PayPalRestClient, upstream: Client):
        self.rest = rest
        self.upstream = upstream

    def get_order(self, order_id: str):
        return self.rest.get_order(order_id)

    def refund_capture(
        self, capture_id: str, amount: Decimal, currency: str, note: str, request_id: str
    ) -> RefundRecord:
        args = {
            "capture_id": capture_id,
            "amount": {"currency_code": currency, "value": f"{amount:.2f}"},
            "note_to_payer": note,
        }
        result = anyio.from_thread.run(self.upstream.call_tool, GUARDED_REFUND, args)
        text = _result_text(result)
        if result.is_error:
            raise PayPalError(f"Agent Toolkit create_refund failed: {text[:300]}")
        try:
            body = json.loads(text)
        except ValueError as exc:
            raise PayPalError(f"Unexpected create_refund response: {text[:300]}") from exc
        return RefundRecord(
            refund_id=body["id"],
            amount=Decimal(body.get("amount", {}).get("value", f"{amount:.2f}")),
            status=body.get("status", "COMPLETED"),
        )

    # The proxy never seeds orders or adds tracking.
    def create_paid_order(self, *args, **kwargs):
        raise NotImplementedError

    def add_tracking(self, *args, **kwargs):
        raise NotImplementedError


class GuardedPayPalServer:
    def __init__(self, upstream: Client, rest: PayPalRestClient, store: Store, customer_id: str | None):
        self.upstream = upstream
        self.rest = rest
        self.store = store
        self.customer_id = customer_id
        self.session_id = f"mcp-{uuid.uuid4().hex[:8]}"
        self.guard = AgentGuard(ToolkitRefunds(rest, upstream), store, default_detector())
        self.tools: dict[str, Tool] = {}

    async def load_tools(self) -> None:
        upstream_tools = (await self.upstream.list_tools()).tools
        self.tools = {t.name: self._wrap(t) for t in upstream_tools}

    @staticmethod
    def _wrap(tool: Tool) -> Tool:
        if tool.name == GUARDED_REFUND:
            schema = copy.deepcopy(tool.input_schema)
            schema.setdefault("properties", {}).update(
                {
                    "reason": {"type": "string", "enum": REASONS, "description": "Why the refund is due"},
                    "customer_claim": {
                        "type": "string",
                        "description": "What the customer said happened, in one sentence",
                    },
                }
            )
            description = (
                "[Guarded by AgentGuard] Every refund is checked against PayPal order, capture and "
                "tracking data and the merchant's refund policy. It is executed, sent to the owner "
                f"for approval, or declined.\n\n{tool.description or ''}"
            )
            return tool.model_copy(update={"description": description, "input_schema": schema})
        if tool.name in HUMAN_ONLY:
            description = f"[AgentGuard: requires a human in PayPal] {tool.description or ''}"
            return tool.model_copy(update={"description": description})
        return tool

    # -- MCP handlers ----------------------------------------------------------
    async def list_tools(self, ctx: ServerRequestContext, params: PaginatedRequestParams | None):
        return ListToolsResult(tools=list(self.tools.values()))

    async def call_tool(self, ctx: ServerRequestContext, params: CallToolRequestParams) -> CallToolResult:
        args = dict(params.arguments or {})
        if params.name == GUARDED_REFUND:
            return await self._refund(args)
        if params.name in HUMAN_ONLY:
            why = HUMAN_ONLY[params.name]
            summary = f"Agent tried {params.name} via MCP ({json.dumps(args)[:200]}). {why}"
            self.store.add_ticket(self.session_id, self.customer_id or "operator", summary)
            message = f"AgentGuard: {why} A ticket was opened for the owner."
            return _text({"status": "DECLINED", "message": message}, error=True)
        if params.name not in self.tools:
            return _text(f"Unknown tool {params.name}", error=True)
        return await self.upstream.call_tool(params.name, args)

    async def _refund(self, args: dict[str, Any]) -> CallToolResult:
        capture_id = str(args.get("capture_id", ""))
        order_id = await anyio.to_thread.run_sync(self.rest.order_for_capture, capture_id)
        if not order_id:
            return _text({"status": "DECLINED", "message": f"No PayPal capture {capture_id}."}, error=True)
        amount = await self._amount(args, order_id)
        if amount is None:
            return _text({"status": "DECLINED", "message": "amount.value must be a number"}, error=True)
        claim = str(args.get("customer_claim") or args.get("note_to_payer") or "")
        reason = args.get("reason") if args.get("reason") in REASONS else "other"
        request = RefundRequest(order_id=order_id, amount=amount, reason=reason, customer_claim=claim)
        context = SessionContext(
            session_id=self.session_id,
            customer_id=self.customer_id,
            customer_messages=[claim] if claim else [],
            channel="mcp",
        )
        decision = await anyio.to_thread.run_sync(self.guard.submit, request, context)
        body = {
            "decision_id": decision.id,
            "outcome": decision.outcome.value,
            "summary": decision.summary,
            "flagged_checks": [c.check for c in decision.failed_checks],
        }
        if decision.status == "executed":
            return _text({"status": "COMPLETED", "refund_id": decision.refund_id, **body})
        if decision.outcome == Outcome.ESCALATE and decision.status == "pending":
            return _text({"status": "PENDING_REVIEW", "message": decision.customer_message, **body})
        message = decision.error or decision.summary
        return _text({"status": "DECLINED", "message": message, **body}, error=True)

    async def _amount(self, args: dict[str, Any], order_id: str) -> Decimal | None:
        value = (args.get("amount") or {}).get("value")
        if value is None:  # PayPal refunds the full remaining amount when none is given
            facts = await anyio.to_thread.run_sync(self.rest.get_order, order_id)
            return facts.refundable
        try:
            return Decimal(str(value)).quantize(Decimal("0.01"))
        except InvalidOperation:
            return None


def upstream_params(access_token: str) -> StdioServerParameters:
    env = {k: os.environ[k] for k in ("PATH", "HOME", "npm_config_cache") if k in os.environ}
    env |= {"PAYPAL_ACCESS_TOKEN": access_token, "PAYPAL_ENVIRONMENT": "SANDBOX"}
    return StdioServerParameters(command="npx", args=["-y", PAYPAL_MCP_PACKAGE, "--tools=all"], env=env)


async def serve() -> None:
    if not (settings.paypal_client_id and settings.paypal_client_secret):
        raise SystemExit("Set PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET (sandbox) to run the MCP proxy.")
    rest = PayPalRestClient(
        settings.paypal_client_id, settings.paypal_client_secret, settings.paypal_base_url
    )
    token = await anyio.to_thread.run_sync(rest.access_token)
    store = Store(settings.db_path)  # shared with the console, so reviews show up there
    customer = os.getenv("AGENTGUARD_CUSTOMER_ID") or None
    async with Client(upstream_params(token)) as upstream:
        proxy = GuardedPayPalServer(upstream, rest, store, customer)
        await proxy.load_tools()
        log.info("Proxying %d PayPal tools (customer=%s)", len(proxy.tools), customer or "operator")
        server = Server(
            "agentguard-paypal",
            version=__version__,
            instructions="PayPal tools behind AgentGuard. Refunds are policy-checked; some need a human.",
            on_list_tools=proxy.list_tools,
            on_call_tool=proxy.call_tool,
        )
        async with stdio_server() as (read, write):
            await server.run(read, write, server.create_initialization_options())


def main() -> None:
    # stdout carries the MCP protocol, so logs go to stderr.
    logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    anyio.run(serve)


if __name__ == "__main__":
    main()
