"""PayPal REST client (Orders v2, Payments v2, tracking) plus the interface the simulator implements."""

from __future__ import annotations

import threading
import time
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Protocol

import httpx

from .models import LineItem, OrderFacts, PayPalError, RefundRecord, Tracker

# PayPal's published sandbox test Visa. It only works against api-m.sandbox.paypal.com.
SANDBOX_TEST_CARD = {"number": "4111111111111111", "expiry": "2030-12", "security_code": "123"}


class PayPalGateway(Protocol):
    mode: str

    def get_order(self, order_id: str) -> OrderFacts: ...

    def refund_capture(
        self, capture_id: str, amount: Decimal, currency: str, note: str, request_id: str
    ) -> RefundRecord: ...

    def create_paid_order(
        self, customer_id: str, customer_name: str, items: list[LineItem], currency: str = "USD"
    ) -> OrderFacts: ...

    def add_tracking(self, order_id: str, capture_id: str, tracking_number: str, carrier: str) -> None: ...


class PayPalRestClient:
    """Thin synchronous client over the PayPal sandbox REST API."""

    mode = "sandbox"

    def __init__(self, client_id: str, client_secret: str, base_url: str):
        self._auth = (client_id, client_secret)
        self._http = httpx.Client(base_url=base_url, timeout=30.0)
        self._token: str | None = None
        self._token_expiry = 0.0
        self._lock = threading.Lock()
        self._carriers: dict[str, str] = {}  # tracker id -> carrier; never changes once set

    # -- auth ---------------------------------------------------------------
    def _bearer(self) -> str:
        with self._lock:
            if self._token and time.time() < self._token_expiry - 60:
                return self._token
            resp = self._http.post(
                "/v1/oauth2/token",
                auth=self._auth,
                data={"grant_type": "client_credentials"},
                headers={"Accept": "application/json"},
            )
            self._raise_for_status(resp)
            body = resp.json()
            self._token = body["access_token"]
            self._token_expiry = time.time() + int(body.get("expires_in", 3600))
            return self._token

    def _request(self, method: str, path: str, **kwargs) -> dict:
        headers = kwargs.pop("headers", {})
        headers.setdefault("Authorization", f"Bearer {self._bearer()}")
        headers.setdefault("Content-Type", "application/json")
        resp = self._http.request(method, path, headers=headers, **kwargs)
        self._raise_for_status(resp)
        return resp.json() if resp.content else {}

    @staticmethod
    def _raise_for_status(resp: httpx.Response) -> None:
        if resp.status_code < 400:
            return
        try:
            body = resp.json()
        except ValueError:
            body = {}
        details = body.get("details") or []
        issue = details[0].get("issue") if details else None
        message = body.get("message") or body.get("error_description") or resp.text[:200]
        raise PayPalError(
            f"PayPal {resp.status_code}: {issue or body.get('name') or ''} {message}".strip(),
            status=resp.status_code,
            debug_id=body.get("debug_id"),
        )

    # -- reads --------------------------------------------------------------
    def get_order(self, order_id: str) -> OrderFacts:
        order = self._request("GET", f"/v2/checkout/orders/{order_id}")
        facts = _facts_from_order(order)
        # Order details omit the carrier; the tracking API has it (ids are "<capture>-<number>").
        raw = (order.get("purchase_units") or [{}])[0].get("shipping", {}).get("trackers") or []
        for tracker, raw_tracker in zip(facts.trackers, raw, strict=False):
            tracker_id = raw_tracker.get("id")
            if tracker.carrier != "OTHER" or not tracker_id:
                continue
            if tracker_id not in self._carriers:
                try:
                    detail = self._request("GET", f"/v1/shipping/trackers/{tracker_id}")
                    self._carriers[tracker_id] = detail.get("carrier", "OTHER")
                except PayPalError:
                    continue
            tracker.carrier = self._carriers[tracker_id]
        return facts

    def order_for_capture(self, capture_id: str) -> str | None:
        """The order a capture belongs to (create_refund only names the capture)."""
        try:
            capture = self._request("GET", f"/v2/payments/captures/{capture_id}")
        except PayPalError as exc:
            if exc.status in (400, 404):
                return None
            raise
        return (capture.get("supplementary_data") or {}).get("related_ids", {}).get("order_id")

    def access_token(self) -> str:
        return self._bearer()

    # -- writes -------------------------------------------------------------
    def refund_capture(
        self, capture_id: str, amount: Decimal, currency: str, note: str, request_id: str
    ) -> RefundRecord:
        body = self._request(
            "POST",
            f"/v2/payments/captures/{capture_id}/refund",
            headers={"PayPal-Request-Id": request_id, "Prefer": "return=representation"},
            json={
                "amount": {"currency_code": currency, "value": f"{amount:.2f}"},
                "note_to_payer": note[:255],
            },
        )
        return RefundRecord(
            refund_id=body["id"],
            amount=Decimal(body.get("amount", {}).get("value", f"{amount:.2f}")),
            status=body.get("status", "COMPLETED"),
        )

    def create_paid_order(
        self, customer_id: str, customer_name: str, items: list[LineItem], currency: str = "USD"
    ) -> OrderFacts:
        total = sum((i.unit_amount * i.quantity for i in items), Decimal("0"))
        payload = {
            "intent": "CAPTURE",
            "payment_source": {"card": {**SANDBOX_TEST_CARD, "name": customer_name}},
            "purchase_units": [
                {
                    "custom_id": customer_id,
                    "amount": {
                        "currency_code": currency,
                        "value": f"{total:.2f}",
                        "breakdown": {"item_total": {"currency_code": currency, "value": f"{total:.2f}"}},
                    },
                    "items": [
                        {
                            "name": i.name,
                            "quantity": str(i.quantity),
                            "unit_amount": {
                                "currency_code": currency,
                                "value": f"{i.unit_amount:.2f}",
                            },
                            "category": "PHYSICAL_GOODS",
                        }
                        for i in items
                    ],
                }
            ],
        }
        created = self._request(
            "POST",
            "/v2/checkout/orders",
            headers={"PayPal-Request-Id": str(uuid.uuid4()), "Prefer": "return=representation"},
            json=payload,
        )
        if created.get("status") != "COMPLETED":
            # Card orders usually complete on create; capture explicitly if not.
            self._request(
                "POST",
                f"/v2/checkout/orders/{created['id']}/capture",
                headers={"PayPal-Request-Id": str(uuid.uuid4())},
            )
        return self.get_order(created["id"])

    def add_tracking(self, order_id: str, capture_id: str, tracking_number: str, carrier: str) -> None:
        self._request(
            "POST",
            f"/v2/checkout/orders/{order_id}/track",
            json={
                "capture_id": capture_id,
                "tracking_number": tracking_number,
                "carrier": carrier,
                "notify_payer": False,
            },
        )


def _facts_from_order(order: dict) -> OrderFacts:
    unit = (order.get("purchase_units") or [{}])[0]
    payments = unit.get("payments") or {}
    captures = payments.get("captures") or []
    capture = captures[0] if captures else {}
    amount = capture.get("amount") or unit.get("amount") or {}
    created = capture.get("create_time")
    return OrderFacts(
        order_id=order["id"],
        status=order.get("status", "UNKNOWN"),
        customer_id=unit.get("custom_id"),
        capture_id=capture.get("id"),
        capture_status=capture.get("status"),
        currency=amount.get("currency_code", "USD"),
        captured=Decimal(amount.get("value", "0")) if capture else Decimal("0"),
        captured_at=datetime.fromisoformat(created.replace("Z", "+00:00")) if created else None,
        refunds=[
            RefundRecord(
                refund_id=r["id"],
                amount=Decimal(r.get("amount", {}).get("value", "0")),
                status=r.get("status", "COMPLETED"),
            )
            for r in payments.get("refunds") or []
        ],
        items=[
            LineItem(
                name=i.get("name", "item"),
                quantity=int(i.get("quantity", "1")),
                unit_amount=Decimal(i.get("unit_amount", {}).get("value", "0")),
            )
            for i in unit.get("items") or []
        ],
        trackers=[
            Tracker(
                tracking_number=_tracking_number(t),
                carrier=t.get("carrier", "OTHER"),
                status=t.get("status", "SHIPPED"),
            )
            for t in (unit.get("shipping") or {}).get("trackers") or []
        ],
    )


def _tracking_number(tracker: dict) -> str:
    # Tracker ids look like "<capture_id>-<tracking_number>".
    if tracker.get("tracking_number"):
        return tracker["tracking_number"]
    tid = tracker.get("id", "")
    return tid.split("-", 1)[1] if "-" in tid else tid
