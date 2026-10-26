"""Drive the AgentGuard MCP proxy the way an AI agent would, against the PayPal sandbox.

    uv run python scripts/mcp_demo.py

Spawns `agentguard-mcp` (which spawns PayPal's MCP server), then makes the tool calls an
agent might: a read, a small refund, a large refund, an over-refund and a dispute
acceptance. Uses the demo shop's sandbox orders, so run the app once first to seed them.
"""

from __future__ import annotations

import json
import os

import anyio
from mcp import Client, StdioServerParameters

from agentguard.config import settings
from agentguard.demo_world import load_world
from agentguard.paypal import PayPalRestClient
from agentguard.store import Store


def show(title: str, result) -> None:
    text = "".join(c.text for c in result.content if getattr(c, "type", "") == "text")
    try:
        body = json.loads(text)
        text = json.dumps({k: body[k] for k in list(body)[:6]}, indent=2)
    except (ValueError, TypeError):
        text = text[:400]
    print(f"\n--- {title}{'  [error]' if result.is_error else ''}\n{text}")


async def main() -> None:
    world = load_world(Store(settings.db_path))
    if world is None:
        raise SystemExit("No demo shop in the sandbox yet: start the app once (uvicorn agentguard.api:app).")
    rest = PayPalRestClient(
        settings.paypal_client_id, settings.paypal_client_secret, settings.paypal_base_url
    )
    capture = {key: rest.get_order(oid).capture_id for key, oid in world.orders.items()}

    proxy = StdioServerParameters(
        command="uv",
        args=["run", "agentguard-mcp"],
        env={k: v for k, v in os.environ.items() if k in ("PATH", "HOME")},
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    )
    with anyio.fail_after(240):
        async with Client(proxy) as agent:
            tools = (await agent.list_tools()).tools
            guarded = [t.name for t in tools if (t.description or "").startswith("[AgentGuard")]
            print(f"{len(tools)} PayPal tools exposed; {', '.join(guarded)} need a human")
            order = await agent.call_tool("get_order", {"id": world.order_id("alex_mug")})
            show("get_order (passes through)", order)
            show(
                "create_refund $5 on the mug (within policy -> executed by the Agent Toolkit)",
                await agent.call_tool(
                    "create_refund",
                    {
                        "capture_id": capture["alex_mug"],
                        "amount": {"currency_code": "USD", "value": "5.00"},
                        "reason": "damaged",
                        "customer_claim": "Mug arrived with a small chip on the rim",
                    },
                ),
            )
            show(
                "create_refund $149 on the grinder (over the auto-approve limit -> owner review)",
                await agent.call_tool(
                    "create_refund",
                    {
                        "capture_id": capture["priya_grinder"],
                        "amount": {"currency_code": "USD", "value": "149.00"},
                        "reason": "damaged",
                        "customer_claim": "Grinder motor is dead",
                    },
                ),
            )
            show(
                "create_refund $60 on a $12 mug (more than was paid -> blocked)",
                await agent.call_tool(
                    "create_refund",
                    {"capture_id": capture["alex_mug"], "amount": {"currency_code": "USD", "value": "60.00"}},
                ),
            )
            show(
                "accept_dispute_claim (irreversible -> needs a human)",
                await agent.call_tool("accept_dispute_claim", {"dispute_id": "PP-D-12345", "note": "agent"}),
            )


if __name__ == "__main__":
    anyio.run(main)
