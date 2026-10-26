"""Wires the PayPal gateway, store, guard and agent together for the app and the CLI."""

from __future__ import annotations

from dataclasses import dataclass

from .agent import GuardMode, SupportAgent
from .config import settings
from .guard import AgentGuard, default_detector
from .paypal import PayPalGateway, PayPalRestClient, PayPalSimulator
from .store import Store


@dataclass
class Runtime:
    paypal: PayPalGateway
    store: Store
    guard: AgentGuard
    agent: SupportAgent


def make_paypal() -> PayPalGateway:
    if settings.paypal_mode == "sandbox":
        return PayPalRestClient(
            settings.paypal_client_id or "", settings.paypal_client_secret or "",
            settings.paypal_base_url,
        )
    return PayPalSimulator()


def build_runtime(store: Store | None = None, paypal: PayPalGateway | None = None) -> Runtime:
    paypal = paypal or make_paypal()
    # The simulator lives in memory, so its store must too or the two drift apart on restart.
    store = store or Store(":memory:" if isinstance(paypal, PayPalSimulator) else settings.db_path)
    guard = AgentGuard(paypal, store, default_detector())
    agent = SupportAgent(paypal, store, guard, GuardMode.AGENTGUARD)
    return Runtime(paypal, store, guard, agent)
