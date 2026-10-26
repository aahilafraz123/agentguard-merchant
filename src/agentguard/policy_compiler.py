"""Turn a refund policy written in plain English into the structured `Policy` the guard enforces.

The model only proposes values; the merchant reviews the diff and saves it. Rules that
cannot be expressed in the schema are returned as `unsupported` instead of being dropped.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from . import llm
from .config import settings
from .guard.policy import Policy

OutcomeName = Literal["allow", "escalate", "block"]


class PolicyDraft(BaseModel):
    """`Policy` with JSON-native types, which structured outputs handle cleanly."""

    refund_window_days: int
    auto_approve_limit: float
    max_refunds_per_customer_30d: int
    max_refund_total_per_customer_30d: float
    shipped_but_not_received: OutcomeName
    changed_mind_after_shipping: OutcomeName
    outside_window: OutcomeName
    manipulation_threshold: float


class CompiledPolicy(BaseModel):
    policy: PolicyDraft
    unsupported: list[str] = Field(
        default_factory=list,
        description="Sentences from the merchant's text that the schema cannot express",
    )
    notes: str = Field("", description="One or two sentences on any assumption you made")


SYSTEM = """You convert a small business owner's refund policy, written in plain English, into a
structured configuration for a refund checkpoint. Keep the default for any field the text does
not mention. Outcomes are "allow", "escalate" (owner reviews it) or "block". If the text contains
rules the schema cannot represent, list them in `unsupported` rather than approximating them."""


def compile_policy(text: str, current: Policy) -> tuple[Policy, CompiledPolicy]:
    if not settings.llm_enabled:
        raise RuntimeError("Set ANTHROPIC_API_KEY to compile policies from plain English.")
    response = llm.parse(
        model=settings.agent_model,
        max_tokens=4000,
        system=SYSTEM,
        output_config={"effort": "low"},
        output_format=CompiledPolicy,
        messages=[
            {
                "role": "user",
                "content": (
                    f"Current configuration (defaults):\n{current.model_dump_json(indent=2)}\n\n"
                    f"<merchant_policy>\n{text}\n</merchant_policy>"
                ),
            }
        ],
    )
    compiled = response.parsed_output
    if compiled is None:
        raise RuntimeError(f"Could not compile policy (stop_reason={response.stop_reason}).")
    # Validate through the real model so bounds (ge/le) are enforced on what the LLM proposed.
    return Policy.model_validate(compiled.policy.model_dump()), compiled


def diff(old: Policy, new: Policy) -> list[dict[str, str]]:
    before, after = old.model_dump(mode="json"), new.model_dump(mode="json")
    return [
        {"field": key, "before": str(before[key]), "after": str(after[key]),
         "description": Policy.model_fields[key].description or key}
        for key in before
        if before[key] != after[key]
    ]
