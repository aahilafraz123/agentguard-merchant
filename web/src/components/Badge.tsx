import { CheckCircle, Clock, Prohibit, XCircle, WarningCircle } from "@phosphor-icons/react";
import type { ReactNode } from "react";
import type { DecisionStatus, Outcome } from "../api";
import { OUTCOME_LABEL, OUTCOME_TONE, STATUS_LABEL, STATUS_TONE, type Tone } from "../format";

const STATUS_ICON: Record<DecisionStatus, typeof CheckCircle> = {
  executed: CheckCircle,
  approved: CheckCircle,
  pending: Clock,
  blocked: Prohibit,
  denied: XCircle,
  failed: WarningCircle,
};

const OUTCOME_ICON: Record<Outcome, typeof CheckCircle> = {
  allow: CheckCircle,
  escalate: Clock,
  block: Prohibit,
};

export function Badge({ tone, children }: { tone: Tone; children: ReactNode }) {
  return <span className={`badge tone-${tone}`}>{children}</span>;
}

export function StatusBadge({ status }: { status: DecisionStatus }) {
  const Icon = STATUS_ICON[status] ?? Clock;
  return (
    <Badge tone={STATUS_TONE[status] ?? "neutral"}>
      <Icon weight="bold" aria-hidden="true" />
      {STATUS_LABEL[status] ?? status}
    </Badge>
  );
}

export function OutcomeBadge({ outcome }: { outcome: Outcome }) {
  const Icon = OUTCOME_ICON[outcome] ?? Clock;
  return (
    <Badge tone={OUTCOME_TONE[outcome] ?? "neutral"}>
      <Icon weight="bold" aria-hidden="true" />
      {OUTCOME_LABEL[outcome] ?? outcome}
    </Badge>
  );
}
