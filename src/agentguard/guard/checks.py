"""Individual guard checks.

Each check compares the agent's request with ground truth (PayPal order data, the
signed-in session, the merchant's own refund history) and returns allow, escalate or
block. None of them read the conversation except `manipulation`, which only ever
escalates.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..paypal.models import OrderFacts
from ..store import Store, utcnow
from .models import CheckResult, Outcome, RefundRequest, RiskAssessment, SessionContext
from .policy import Policy


@dataclass
class CheckInput:
    request: RefundRequest
    context: SessionContext
    facts: OrderFacts | None
    policy: Policy
    risk: RiskAssessment
    store: Store


def _ok(check: str, title: str, detail: str, **evidence) -> CheckResult:
    return CheckResult(check=check, title=title, outcome=Outcome.ALLOW, detail=detail, evidence=evidence)


def _flag(check: str, title: str, outcome: Outcome, detail: str, **evidence) -> CheckResult:
    return CheckResult(check=check, title=title, outcome=outcome, detail=detail, evidence=evidence)


def order_paid(i: CheckInput) -> CheckResult:
    title = "Order exists and was paid"
    if i.facts is None:
        return _flag("order_paid", title, Outcome.BLOCK, f"PayPal has no order {i.request.order_id}.")
    if i.facts.status != "COMPLETED" or not i.facts.capture_id:
        return _flag(
            "order_paid", title, Outcome.BLOCK,
            f"PayPal order status is {i.facts.status}; there is no completed capture to refund.",
            paypal_status=i.facts.status,
        )
    return _ok("order_paid", title, f"Capture {i.facts.capture_id} is {i.facts.capture_status}.",
               capture_id=i.facts.capture_id)


def ownership(i: CheckInput) -> CheckResult:
    title = "Order belongs to the signed-in customer"
    if i.facts is None:
        return _flag("ownership", title, Outcome.BLOCK, "No PayPal order to check ownership against.")
    if i.facts.customer_id != i.context.customer_id:
        return _flag(
            "ownership", title, Outcome.BLOCK,
            "PayPal records this order under a different customer than the one signed in.",
            order_customer=i.facts.customer_id, session_customer=i.context.customer_id,
        )
    return _ok("ownership", title, "PayPal custom_id matches the signed-in customer.",
               customer_id=i.context.customer_id)


def refundable_amount(i: CheckInput) -> CheckResult:
    title = "Amount is still refundable"
    amount = i.request.amount
    if amount <= 0:
        return _flag("refundable_amount", title, Outcome.BLOCK, "Refund amount must be positive.")
    if i.facts is None:
        return _flag("refundable_amount", title, Outcome.BLOCK, "No PayPal capture to refund.")
    evidence = {
        "requested": f"{amount:.2f}",
        "captured": f"{i.facts.captured:.2f}",
        "already_refunded": f"{i.facts.refunded:.2f}",
        "refundable": f"{i.facts.refundable:.2f}",
    }
    if amount > i.facts.refundable:
        return _flag(
            "refundable_amount", title, Outcome.BLOCK,
            f"Requested ${amount:.2f} but only ${i.facts.refundable:.2f} of this payment is "
            "still refundable.",
            **evidence,
        )
    return _ok("refundable_amount", title,
               f"${amount:.2f} of ${i.facts.refundable:.2f} refundable.", **evidence)


def no_pending_duplicate(i: CheckInput) -> CheckResult:
    title = "No refund already waiting for this payment"
    if i.facts is None or not i.facts.capture_id:
        return _ok("no_pending_duplicate", title, "Nothing to compare.")
    pending = i.store.pending_for_capture(i.facts.capture_id)
    if pending:
        return _flag(
            "no_pending_duplicate", title, Outcome.BLOCK,
            f"A refund for this payment is already awaiting review (decision #{pending[0]['id']}).",
            pending_decision=pending[0]["id"],
        )
    return _ok("no_pending_duplicate", title, "No pending refund for this capture.")


def refund_window(i: CheckInput) -> CheckResult:
    title = "Within the refund window"
    if i.facts is None or i.facts.captured_at is None:
        return _ok("refund_window", title, "No payment date available.")
    age = (utcnow() - i.facts.captured_at).days
    evidence = {"paid_days_ago": age, "window_days": i.policy.refund_window_days}
    if age > i.policy.refund_window_days:
        return _flag("refund_window", title, i.policy.outside_window,
                     f"Paid {age} days ago; the window is {i.policy.refund_window_days} days.",
                     **evidence)
    return _ok("refund_window", title, f"Paid {age} days ago.", **evidence)


def shipping_evidence(i: CheckInput) -> CheckResult:
    title = "Claim is consistent with shipping records"
    if i.facts is None:
        return _ok("shipping_evidence", title, "No order data.")
    trackers = [t.model_dump() for t in i.facts.trackers]
    if i.request.reason == "not_received" and i.facts.shipped:
        t = i.facts.trackers[0]
        return _flag(
            "shipping_evidence", title, i.policy.shipped_but_not_received,
            f"Customer says it never arrived, but PayPal shows it shipped "
            f"({t.carrier} {t.tracking_number}).",
            trackers=trackers,
        )
    if i.request.reason == "changed_mind" and i.facts.shipped:
        return _flag("shipping_evidence", title, i.policy.changed_mind_after_shipping,
                     "Change-of-mind refund on an order that has already shipped.",
                     trackers=trackers)
    detail = "Order has not shipped." if not i.facts.shipped else "Reason does not conflict with tracking."
    return _ok("shipping_evidence", title, detail, trackers=trackers)


def auto_approve_limit(i: CheckInput) -> CheckResult:
    title = "Under the auto-approve limit"
    limit = i.policy.auto_approve_limit
    if i.request.amount > limit:
        return _flag("auto_approve_limit", title, Outcome.ESCALATE,
                     f"${i.request.amount:.2f} is above the ${limit:.2f} auto-approve limit.",
                     limit=f"{limit:.2f}")
    return _ok("auto_approve_limit", title, f"Under ${limit:.2f}.", limit=f"{limit:.2f}")


def velocity(i: CheckInput) -> CheckResult:
    title = "Customer refund history is normal"
    count, total = i.store.refund_activity(i.context.customer_id)
    new_count, new_total = count + 1, total + i.request.amount
    evidence = {"refunds_30d": count, "refunded_30d": f"{total:.2f}"}
    if new_count > i.policy.max_refunds_per_customer_30d:
        return _flag("velocity", title, Outcome.ESCALATE,
                     f"This would be refund #{new_count} for this customer in 30 days "
                     f"(limit {i.policy.max_refunds_per_customer_30d}).", **evidence)
    if new_total > i.policy.max_refund_total_per_customer_30d:
        return _flag("velocity", title, Outcome.ESCALATE,
                     f"This would bring the customer to ${new_total:.2f} refunded in 30 days "
                     f"(limit ${i.policy.max_refund_total_per_customer_30d:.2f}).", **evidence)
    return _ok("velocity", title, f"{count} refund(s), ${total:.2f} in the last 30 days.", **evidence)


def manipulation(i: CheckInput) -> CheckResult:
    title = "No signs of manipulation in the conversation"
    risk = i.risk
    evidence = {"score": round(risk.score, 2), "tactics": risk.tactics, "source": risk.source}
    if risk.score >= i.policy.manipulation_threshold:
        tactics = ", ".join(risk.tactics) or "unspecified"
        return _flag("manipulation", title, Outcome.ESCALATE,
                     f"Risk {risk.score:.2f} ({tactics}). {risk.rationale}".strip(), **evidence)
    return _ok("manipulation", title, f"Risk {risk.score:.2f}.", **evidence)


ALL_CHECKS = (
    order_paid,
    ownership,
    refundable_amount,
    no_pending_duplicate,
    refund_window,
    shipping_evidence,
    auto_approve_limit,
    velocity,
    manipulation,
)

# Re-run before a merchant-approved refund executes, in case the facts changed meanwhile.
HARD_CHECKS = (order_paid, ownership, refundable_amount)


def run_checks(i: CheckInput, checks=ALL_CHECKS) -> list[CheckResult]:
    return [check(i) for check in checks]


def worst(results: list[CheckResult]) -> Outcome:
    return max((r.outcome for r in results), key=lambda o: o.severity, default=Outcome.ALLOW)
