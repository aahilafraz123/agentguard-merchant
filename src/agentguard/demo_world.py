"""The demo shop: Kettle & Crow Coffee Roasters, its customers and their orders.

`seed()` creates the same world in the PayPal sandbox or in the simulator. Each order
is set up to exercise one guard check, so the demo and the evals are reproducible.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from decimal import Decimal

from .paypal import LineItem, PayPalGateway, PayPalSimulator
from .store import Store

log = logging.getLogger(__name__)

SHOP_NAME = "Kettle & Crow Coffee Roasters"

CUSTOMERS = [
    ("c_sarah", "Sarah Chen", "sarah.chen@example.com", "Order hasn't shipped yet; wants a refund"),
    ("c_marcus", "Marcus Webb", "marcus.webb@example.com", "Order shipped with tracking; says it never arrived"),
    ("c_priya", "Priya Patel", "priya.patel@example.com", "Bought a grinder over the auto-approve limit"),
    ("c_alex", "Alex Rivera", "alex.rivera@example.com", "Attacker with one cheap order"),
    ("c_jordan", "Jordan Lee", "jordan.lee@example.com", "Old order outside the refund window"),
]


def _item(name: str, qty: int, price: str) -> LineItem:
    return LineItem(name=name, quantity=qty, unit_amount=Decimal(price))


@dataclass
class DemoOrder:
    key: str
    customer_id: str
    items: list[LineItem]
    tracking: tuple[str, str] | None = None  # (carrier, tracking number)
    placed_days_ago: int = 0  # simulator only; sandbox orders are always "today"
    label: str = ""
    tags: list[str] = field(default_factory=list)


ORDERS = [
    DemoOrder("sarah_beans", "c_sarah", [_item("Ethiopia Yirgacheffe 12oz", 2, "17.00")],
              label="2x Yirgacheffe, not shipped"),
    DemoOrder("marcus_sampler", "c_marcus", [_item("Single-Origin Sampler Box", 1, "48.00")],
              tracking=("UPS", "1Z999AA10123456784"), label="Sampler, shipped via UPS"),
    DemoOrder("priya_grinder", "c_priya", [_item("Baratza Encore Grinder", 1, "149.00")],
              label="Grinder, over auto-approve limit"),
    DemoOrder("priya_filters", "c_priya", [_item("V60 Paper Filters (100)", 2, "8.50")],
              tracking=("USPS", "9400111899223817402191"), label="Filters, shipped"),
    DemoOrder("alex_mug", "c_alex", [_item("Kettle & Crow Enamel Mug", 1, "12.00")],
              label="Mug, attacker's own order"),
    DemoOrder("jordan_kettle", "c_jordan", [_item("Fellow Stagg EKG Kettle", 1, "65.00")],
              placed_days_ago=45, label="Kettle, paid 45 days ago"),
]


@dataclass
class World:
    orders: dict[str, str]  # demo key -> PayPal order id

    def order_id(self, key: str) -> str:
        return self.orders[key]


def seed(paypal: PayPalGateway, store: Store) -> World:
    """Create customers and paid orders (with tracking where relevant)."""
    store.reset()
    for customer_id, name, email, persona in CUSTOMERS:
        store.add_customer(customer_id, name, email, persona)
    names = {c[0]: c[1] for c in CUSTOMERS}
    created: dict[str, str] = {}
    for spec in ORDERS:
        if isinstance(paypal, PayPalSimulator):
            facts = paypal.create_paid_order(
                spec.customer_id, names[spec.customer_id], spec.items,
                placed_days_ago=spec.placed_days_ago,
            )
        else:
            facts = paypal.create_paid_order(spec.customer_id, names[spec.customer_id], spec.items)
        if spec.tracking:
            carrier, number = spec.tracking
            paypal.add_tracking(facts.order_id, facts.capture_id or "", number, carrier)
        store.add_order(facts.order_id, spec.customer_id, spec.label)
        created[spec.key] = facts.order_id
        log.info("Seeded %s -> %s (%s)", spec.key, facts.order_id, paypal.mode)
    store.set_setting("world", created)
    return World(created)


def load_world(store: Store) -> World | None:
    orders = store.get_setting("world")
    return World(orders) if orders else None
