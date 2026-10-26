"""Types that flow through the guard: requests, context, check results and decisions."""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

RefundReason = Literal[
    "not_received",
    "damaged",
    "wrong_item",
    "not_as_described",
    "changed_mind",
    "duplicate_charge",
    "other",
]


class Outcome(StrEnum):
    ALLOW = "allow"
    ESCALATE = "escalate"
    BLOCK = "block"

    @property
    def severity(self) -> int:
        return {"allow": 0, "escalate": 1, "block": 2}[self.value]


class RefundRequest(BaseModel):
    """What the agent asked for. Everything here came from an LLM and is untrusted."""

    order_id: str
    amount: Decimal
    reason: RefundReason
    customer_claim: str = ""


class SessionContext(BaseModel):
    """Who is actually signed in. This comes from the storefront session, never from the chat."""

    session_id: str
    # None for an operator session (e.g. a merchant's own agent over MCP): no customer to match.
    customer_id: str | None
    customer_name: str = ""
    customer_messages: list[str] = Field(default_factory=list)
    channel: str = "agentguard"  # agentguard (storefront chat) or mcp (MCP proxy)


class CheckResult(BaseModel):
    check: str
    title: str
    outcome: Outcome
    detail: str
    evidence: dict = Field(default_factory=dict)


class RiskAssessment(BaseModel):
    score: float = Field(ge=0, le=1)
    tactics: list[str] = Field(default_factory=list)
    rationale: str = ""
    source: Literal["llm", "heuristic"] = "heuristic"


class Decision(BaseModel):
    id: int | None = None
    outcome: Outcome
    status: Literal["executed", "pending", "blocked", "approved", "denied", "failed"]
    request: RefundRequest
    context: SessionContext
    checks: list[CheckResult]
    risk: RiskAssessment
    summary: str
    customer_message: str
    capture_id: str | None = None
    refund_id: str | None = None
    error: str | None = None

    @property
    def failed_checks(self) -> list[CheckResult]:
        return [c for c in self.checks if c.outcome != Outcome.ALLOW]
