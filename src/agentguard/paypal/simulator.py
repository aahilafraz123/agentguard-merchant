"""In-memory stand-in for the PayPal sandbox.

Used by tests, CI and the eval harness so every run starts from identical state and
no sandbox data is mutated. It enforces the same invariants PayPal does that matter
here: you cannot refund more than was captured, and request ids are idempotent.
"""

from __future__ import annotations

import itertools
import threading
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from .models import LineItem, OrderFacts, PayPalError, RefundRecord, Tracker


class PayPalSimulator:
    mode = "mock"

    def __init__(self) -> None:
        self._orders: dict[str, OrderFacts] = {}
        self._by_capture: dict[str, str] = {}
        self._request_ids: dict[str, tuple[str, RefundRecord]] = {}
        self._seq = itertools.count(1)
        self._lock = threading.Lock()

    def _id(self, prefix: str) -> str:
        return f"{prefix}{next(self._seq):06d}SIM"

    def get_order(self, order_id: str) -> OrderFacts:
        order = self._orders.get(order_id)
        if order is None:
            raise PayPalError(f"PayPal 404: RESOURCE_NOT_FOUND order {order_id}", status=404)
        return order.model_copy(deep=True)

    def refund_capture(
        self, capture_id: str, amount: Decimal, currency: str, note: str, request_id: str
    ) -> RefundRecord:
        with self._lock:
            if request_id in self._request_ids:
                previous_capture, refund = self._request_ids[request_id]
                if previous_capture != capture_id:  # PayPal rejects a reused id on another request
                    raise PayPalError(
                        "PayPal 400: DUPLICATE_REQUEST_ID The value of PayPal-Request-Id header "
                        "has already been used.",
                        status=400,
                    )
                return refund
            order_id = self._by_capture.get(capture_id)
            if order_id is None:
                raise PayPalError("PayPal 404: RESOURCE_NOT_FOUND capture", status=404)
            order = self._orders[order_id]
            if amount <= 0 or amount > order.refundable:
                raise PayPalError(
                    "PayPal 422: REFUND_AMOUNT_EXCEEDED The refund amount must be less than "
                    "or equal to the capture amount that has not yet been refunded.",
                    status=422,
                )
            refund = RefundRecord(refund_id=self._id("RF"), amount=amount, status="COMPLETED")
            order.refunds.append(refund)
            order.capture_status = "REFUNDED" if order.refundable == 0 else "PARTIALLY_REFUNDED"
            self._request_ids[request_id] = (capture_id, refund)
            return refund

    def create_paid_order(
        self,
        customer_id: str,
        customer_name: str,
        items: list[LineItem],
        currency: str = "USD",
        placed_days_ago: int = 0,
    ) -> OrderFacts:
        total = sum((i.unit_amount * i.quantity for i in items), Decimal("0"))
        order = OrderFacts(
            order_id=self._id("ORD"),
            status="COMPLETED",
            customer_id=customer_id,
            capture_id=self._id("CAP"),
            capture_status="COMPLETED",
            currency=currency,
            captured=total,
            captured_at=datetime.now(UTC) - timedelta(days=placed_days_ago),
            items=items,
        )
        with self._lock:
            self._orders[order.order_id] = order
            self._by_capture[order.capture_id] = order.order_id
        return order.model_copy(deep=True)

    def add_tracking(self, order_id: str, capture_id: str, tracking_number: str, carrier: str) -> None:
        self._orders[order_id].trackers.append(
            Tracker(tracking_number=tracking_number, carrier=carrier, status="SHIPPED")
        )
