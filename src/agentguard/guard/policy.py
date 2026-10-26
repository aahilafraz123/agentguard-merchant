"""The merchant's refund policy as data: what the guard enforces and what the console edits."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field

from .models import Outcome


class Policy(BaseModel):
    refund_window_days: int = Field(30, ge=0, description="Days after payment a refund is allowed")
    auto_approve_limit: Decimal = Field(
        Decimal("75"), ge=0, description="Refunds above this amount need merchant approval"
    )
    max_refunds_per_customer_30d: int = Field(
        2, ge=0, description="Refunds per customer per 30 days before review"
    )
    max_refund_total_per_customer_30d: Decimal = Field(
        Decimal("150"), ge=0, description="Total refunded per customer per 30 days before review"
    )
    shipped_but_not_received: Outcome = Field(
        Outcome.ESCALATE,
        description="What to do when a customer says 'never arrived' but PayPal shows it shipped",
    )
    changed_mind_after_shipping: Outcome = Field(
        Outcome.ESCALATE, description="What to do for change-of-mind refunds on shipped orders"
    )
    outside_window: Outcome = Field(
        Outcome.ESCALATE, description="What to do for refunds requested after the window"
    )
    manipulation_threshold: float = Field(
        0.6, ge=0, le=1, description="Risk score at which a conversation is sent for review"
    )

    def describe(self) -> list[str]:
        """Plain-English rules, shown in the console and given to the prompt-only baseline."""
        verb = {Outcome.ALLOW: "allowed", Outcome.ESCALATE: "sent for review", Outcome.BLOCK: "refused"}
        return [
            f"Refunds are available within {self.refund_window_days} days of payment; "
            f"later requests are {verb[self.outside_window]}.",
            f"Refunds up to ${self.auto_approve_limit:.2f} can be issued automatically; "
            "larger ones need the owner's approval.",
            f"A customer may receive at most {self.max_refunds_per_customer_30d} refunds and "
            f"${self.max_refund_total_per_customer_30d:.2f} in total per 30 days without review.",
            "If a customer says an order never arrived but it has shipped with tracking, the "
            f"request is {verb[self.shipped_but_not_received]}.",
            "Change-of-mind refunds on orders that have already shipped are "
            f"{verb[self.changed_mind_after_shipping]}.",
            "Refunds can only go to the customer who placed the order, and never for more than "
            "the amount that is still refundable.",
        ]
