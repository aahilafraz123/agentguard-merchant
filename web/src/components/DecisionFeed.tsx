import { useEffect, useRef, type ReactNode } from "react";
import type { Decision } from "../api";
import { STATUS_TONE, money, timeAgo } from "../format";
import { useNow } from "../hooks";
import { StatusBadge } from "./Badge";
import { EmptyState } from "./EmptyState";

interface Props {
  decisions: Decision[] | undefined;
  names: Record<string, string>;
  selectedId: number | undefined;
  onSelect: (id: number) => void;
  empty?: ReactNode;
}

const HEAD = /^(Allowed|Blocked|Needs review): \$[\d,.]+ refund on \S+ \([^)]*\)\.\s*/;

/** The part of a decision summary that explains it, without the amount and order repeated. */
export function reasonText(decision: Decision): string {
  if (!decision.checks.length) return "Issued straight to PayPal. No checks ran.";
  return decision.summary.replace(HEAD, "") || decision.summary;
}

export function DecisionFeed({ decisions, names, selectedId, onSelect, empty }: Props) {
  const now = useNow();
  // Remember which rows were already on screen so only new arrivals animate in.
  const seen = useRef<Set<number> | null>(null);
  const firstRender = seen.current === null;
  const known = seen.current ?? new Set<number>();
  useEffect(() => {
    if (decisions) seen.current = new Set(decisions.map((d) => d.id));
  }, [decisions]);

  if (!decisions) {
    return (
      <ul className="feed" aria-busy="true">
        {[0, 1, 2].map((i) => (
          <li key={i} className="feed-skeleton" />
        ))}
      </ul>
    );
  }
  if (!decisions.length) return <>{empty ?? <EmptyState title="No refund requests yet" />}</>;

  return (
    <ul className="feed">
      {decisions.map((d) => (
        <li key={d.id} className={!firstRender && !known.has(d.id) ? "is-new" : undefined}>
          <button
            type="button"
            className={`feed-item tone-${STATUS_TONE[d.status] ?? "neutral"}`}
            aria-pressed={d.id === selectedId}
            onClick={() => onSelect(d.id)}
          >
            <span className="feed-row">
              <span className="feed-amount num">{money(d.amount)}</span>
              <span className="feed-who">{names[d.customer_id] ?? d.customer_id}</span>
              <span className="feed-time">{timeAgo(d.created_at, now)}</span>
            </span>
            <span className="feed-row">
              <StatusBadge status={d.status} />
              <span className="feed-order mono">{d.order_id}</span>
            </span>
            <span className="feed-reason">{reasonText(d)}</span>
          </button>
        </li>
      ))}
    </ul>
  );
}
