"""AgentGuard: decide, record and (when allowed) execute a refund the agent asked for."""

from __future__ import annotations

import logging

from ..paypal.client import PayPalGateway
from ..paypal.models import OrderFacts, PayPalError
from ..store import Store, utcnow
from .checks import HARD_CHECKS, CheckInput, run_checks, worst
from .detector import Detector, HeuristicDetector
from .models import Decision, Outcome, RefundRequest, RiskAssessment, SessionContext
from .policy import Policy

log = logging.getLogger(__name__)

CUSTOMER_MESSAGES = {
    Outcome.ALLOW: "Refund issued.",
    Outcome.ESCALATE: (
        "This refund needs a quick review by the shop owner. It has been queued and the "
        "customer will hear back within one business day."
    ),
    Outcome.BLOCK: "This refund can't be issued for this order.",
}


class AgentGuard:
    def __init__(self, paypal: PayPalGateway, store: Store, detector: Detector | None = None):
        self.paypal = paypal
        self.store = store
        self.detector = detector or HeuristicDetector()

    # -- policy -------------------------------------------------------------
    @property
    def policy(self) -> Policy:
        raw = self.store.get_setting("policy")
        return Policy.model_validate(raw) if raw else Policy()

    def set_policy(self, policy: Policy, source_text: str | None = None) -> None:
        self.store.set_setting("policy", policy.model_dump(mode="json"))
        if source_text is not None:
            self.store.set_setting("policy_source", source_text)

    # -- evaluation ---------------------------------------------------------
    def _facts(self, order_id: str) -> OrderFacts | None:
        try:
            return self.paypal.get_order(order_id)
        except PayPalError as exc:
            if exc.status in (400, 404, 422):
                return None
            raise

    def evaluate(self, request: RefundRequest, context: SessionContext) -> Decision:
        """Pure decision: reads PayPal and history, moves no money, writes nothing."""
        facts = self._facts(request.order_id)
        risk = self.detector.assess(context.customer_messages)
        checks = run_checks(
            CheckInput(request, context, facts, self.policy, risk, self.store)
        )
        outcome = worst(checks)
        status = {Outcome.ALLOW: "executed", Outcome.ESCALATE: "pending", Outcome.BLOCK: "blocked"}
        return Decision(
            outcome=outcome,
            status=status[outcome],
            request=request,
            context=context,
            checks=checks,
            risk=risk,
            summary=_summary(outcome, request, checks),
            customer_message=CUSTOMER_MESSAGES[outcome],
            capture_id=facts.capture_id if facts else None,
        )

    def submit(
        self, request: RefundRequest, context: SessionContext, transcript: list[dict] | None = None
    ) -> Decision:
        """Evaluate, record, and execute the refund on PayPal if every check allows it."""
        decision = self.evaluate(request, context)
        decision.id = self.store.insert_decision(
            {
                "session_id": context.session_id,
                "customer_id": context.customer_id,
                "order_id": request.order_id,
                "capture_id": decision.capture_id,
                "amount": f"{request.amount:.2f}",
                "reason": request.reason,
                "claim": request.customer_claim,
                "outcome": decision.outcome.value,
                # Recorded as pending until PayPal confirms, so concurrent requests see it.
                "status": "pending" if decision.outcome == Outcome.ALLOW else decision.status,
                "checks": [c.model_dump(mode="json") for c in decision.checks],
                "risk": decision.risk.model_dump(mode="json"),
                "summary": decision.summary,
                "transcript": transcript or [],
            }
        )
        if decision.outcome == Outcome.ALLOW:
            self._execute(decision.id, decision)
        return decision

    def _execute(self, decision_id: int, decision: Decision, final_status: str = "executed") -> None:
        try:
            refund = self.paypal.refund_capture(
                capture_id=decision.capture_id or "",
                amount=decision.request.amount,
                currency="USD",
                note=f"Refund for order {decision.request.order_id}",
                request_id=f"agentguard-decision-{decision_id}",
            )
        except PayPalError as exc:
            log.error("PayPal refund failed for decision %s: %s", decision_id, exc)
            decision.status, decision.error = "failed", str(exc)
            decision.customer_message = "The refund could not be processed; a person will follow up."
            self.store.update_decision(decision_id, status="failed", error=str(exc))
            return
        decision.status, decision.refund_id = final_status, refund.refund_id
        self.store.update_decision(decision_id, status=final_status, refund_id=refund.refund_id)

    # -- merchant review ----------------------------------------------------
    def approve(self, decision_id: int, reviewer: str = "merchant", note: str = "") -> dict:
        row = self._pending(decision_id)
        request = RefundRequest(
            order_id=row["order_id"], amount=row["amount"], reason=row["reason"],
            customer_claim=row["claim"],
        )
        context = SessionContext(session_id=row["session_id"], customer_id=row["customer_id"])
        facts = self._facts(row["order_id"])
        # The order may have changed while the request sat in the queue.
        recheck = run_checks(
            CheckInput(request, context, facts, self.policy, RiskAssessment(score=0), self.store),
            HARD_CHECKS,
        )
        resolved = {"resolved_by": reviewer, "resolved_note": note, "resolved_at": utcnow().isoformat()}
        if worst(recheck) == Outcome.BLOCK:
            reason = "; ".join(c.detail for c in recheck if c.outcome == Outcome.BLOCK)
            self.store.update_decision(decision_id, status="denied", error=f"Re-check failed: {reason}", **resolved)
            return self.store.get_decision(decision_id)
        self.store.update_decision(decision_id, **resolved)
        decision = Decision(
            id=decision_id, outcome=Outcome.ESCALATE, status="pending", request=request,
            context=context, checks=recheck, risk=RiskAssessment(score=0), summary=row["summary"],
            customer_message="", capture_id=facts.capture_id if facts else None,
        )
        self._execute(decision_id, decision, final_status="approved")
        return self.store.get_decision(decision_id)

    def deny(self, decision_id: int, reviewer: str = "merchant", note: str = "") -> dict:
        self._pending(decision_id)
        self.store.update_decision(
            decision_id, status="denied", resolved_by=reviewer, resolved_note=note,
            resolved_at=utcnow().isoformat(),
        )
        return self.store.get_decision(decision_id)

    def _pending(self, decision_id: int) -> dict:
        row = self.store.get_decision(decision_id)
        if row is None:
            raise KeyError(f"decision {decision_id} not found")
        if row["status"] != "pending" or row["outcome"] != Outcome.ESCALATE.value:
            raise ValueError(f"decision {decision_id} is {row['status']}, not awaiting review")
        return row


def _summary(outcome: Outcome, request: RefundRequest, checks) -> str:
    head = f"${request.amount:.2f} refund on {request.order_id} ({request.reason.replace('_', ' ')})"
    flagged = [c for c in checks if c.outcome != Outcome.ALLOW]
    if not flagged:
        return f"Allowed: {head}. All {len(checks)} checks passed."
    verb = "Blocked" if outcome == Outcome.BLOCK else "Needs review"
    reasons = " ".join(c.detail for c in flagged if c.outcome == outcome) or flagged[0].detail
    return f"{verb}: {head}. {reasons}"
