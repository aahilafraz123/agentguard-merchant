"""Normalized view of a PayPal order: the facts AgentGuard trusts instead of the chat."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class Tracker(BaseModel):
    tracking_number: str
    carrier: str
    status: str  # PayPal tracker status, e.g. SHIPPED / CANCELLED


class LineItem(BaseModel):
    name: str
    quantity: int
    unit_amount: Decimal


class RefundRecord(BaseModel):
    refund_id: str
    amount: Decimal
    status: str


class OrderFacts(BaseModel):
    order_id: str
    status: str
    customer_id: str | None = Field(
        default=None, description="purchase_units[0].custom_id, set by the storefront at checkout"
    )
    capture_id: str | None = None
    capture_status: str | None = None
    currency: str = "USD"
    captured: Decimal = Decimal("0")
    captured_at: datetime | None = None
    refunds: list[RefundRecord] = Field(default_factory=list)
    items: list[LineItem] = Field(default_factory=list)
    trackers: list[Tracker] = Field(default_factory=list)

    @property
    def refunded(self) -> Decimal:
        return sum((r.amount for r in self.refunds if r.status != "CANCELLED"), Decimal("0"))

    @property
    def refundable(self) -> Decimal:
        return max(self.captured - self.refunded, Decimal("0"))

    @property
    def shipped(self) -> bool:
        return any(t.status == "SHIPPED" for t in self.trackers)

    def summary(self) -> dict:
        """Compact, JSON-safe view used in agent tool results and the console."""
        return {
            "order_id": self.order_id,
            "status": self.status,
            "capture_status": self.capture_status,
            "total": f"{self.captured:.2f} {self.currency}",
            "already_refunded": f"{self.refunded:.2f}",
            "placed_at": self.captured_at.isoformat() if self.captured_at else None,
            "items": [f"{i.quantity} x {i.name} @ {i.unit_amount:.2f}" for i in self.items],
            "shipping": [
                {"carrier": t.carrier, "tracking_number": t.tracking_number, "status": t.status}
                for t in self.trackers
            ]
            or "not shipped yet",
        }


class PayPalError(RuntimeError):
    def __init__(self, message: str, status: int | None = None, debug_id: str | None = None):
        super().__init__(message)
        self.status = status
        self.debug_id = debug_id
