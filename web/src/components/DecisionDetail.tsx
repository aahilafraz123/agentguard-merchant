import { Check, Prohibit, Warning, X } from "@phosphor-icons/react";
import { useState } from "react";
import { ApiError, api, type CheckResult, type Decision, type Outcome } from "../api";
import { MODE_LABEL, dateTime, humanize, money } from "../format";
import { StatusBadge } from "./Badge";

interface Props {
  decision: Decision;
  names: Record<string, string>;
  /** Called after an approve or deny attempt so the caller can refresh its data. */
  onResolved: () => void;
}

const UNGUARDED = /^Unguarded \((\w+)\)/;

export function DecisionDetail({ decision: d, names, onResolved }: Props) {
  const flagged = d.checks.filter((c) => c.outcome !== "allow").length;
  const unguarded = d.checks.length === 0;
  const unguardedMode = d.summary.match(UNGUARDED)?.[1] as keyof typeof MODE_LABEL | undefined;

  return (
    <article className="detail" aria-label={`Decision ${d.id}`}>
      <header className="detail-head">
        <div className="detail-meta">
          <StatusBadge status={d.status} />
          <span className="mono">#{d.id}</span>
          <span>{dateTime(d.created_at)}</span>
        </div>
        <div className="detail-title">
          <span className="detail-amount num">{money(d.amount)}</span>
          <span className="detail-sub">
            {humanize(d.reason)} refund for <strong>{names[d.customer_id] ?? d.customer_id}</strong> on{" "}
            <span className="mono">{d.order_id}</span>
          </span>
        </div>
        {d.claim && <blockquote className="detail-claim">{d.claim}</blockquote>}
      </header>

      {d.status === "pending" && <ReviewActions id={d.id} onResolved={onResolved} />}
      <Resolution decision={d} />

      <section className="detail-section">
        <h3 className="detail-h">
          Checks against PayPal
          {!unguarded && (
            <span className="detail-h-note">
              {flagged ? `${flagged} of ${d.checks.length} flagged` : `All ${d.checks.length} passed`}
            </span>
          )}
        </h3>
        {unguarded ? (
          <p className="detail-unguarded">
            This refund was issued by the {unguardedMode ? MODE_LABEL[unguardedMode].toLowerCase() : "unguarded"} bot
            directly on PayPal. No checks ran.
            {d.refund_id && (
              <>
                {" "}
                Refund <span className="mono">{d.refund_id}</span>.
              </>
            )}
          </p>
        ) : (
          <ol className="checks">
            {d.checks.map((check) => (
              <CheckRow key={check.check} check={check} names={names} />
            ))}
          </ol>
        )}
      </section>

      {!unguarded && <RiskPanel decision={d} />}

      {d.transcript.length > 0 && (
        <section className="detail-section">
          <h3 className="detail-h">Conversation</h3>
          <ol className="transcript">
            {d.transcript.map((line, i) => (
              <li key={i} className={`transcript-line is-${line.role}`}>
                <span className="transcript-role">{line.role === "customer" ? "Customer" : "Support bot"}</span>
                <p>{line.text}</p>
              </li>
            ))}
          </ol>
        </section>
      )}
    </article>
  );
}

const CHECK_ICON: Record<Outcome, typeof Check> = { allow: Check, escalate: Warning, block: X };
const CHECK_WORD: Record<Outcome, string> = { allow: "Pass", escalate: "Review", block: "Block" };

function CheckRow({ check, names }: { check: CheckResult; names: Record<string, string> }) {
  const Icon = CHECK_ICON[check.outcome] ?? Warning;
  const evidence = evidenceRows(check, names);
  return (
    <li className={`check is-${check.outcome}`}>
      <span className="check-icon" aria-label={CHECK_WORD[check.outcome]}>
        <Icon weight="bold" />
      </span>
      <div className="check-body">
        <div className="check-title">
          {check.title}
          <span className="check-word">{CHECK_WORD[check.outcome]}</span>
        </div>
        <p className="check-detail">{check.detail}</p>
        {evidence.length > 0 &&
          (check.outcome === "allow" ? (
            <details className="evidence-more">
              <summary>Evidence</summary>
              <EvidenceList rows={evidence} />
            </details>
          ) : (
            <EvidenceList rows={evidence} />
          ))}
      </div>
    </li>
  );
}

type Row = [label: string, value: string];

function EvidenceList({ rows }: { rows: Row[] }) {
  return (
    <dl className="evidence">
      {rows.map(([label, value]) => (
        <div key={label} className="evidence-row">
          <dt>{label}</dt>
          <dd>{value}</dd>
        </div>
      ))}
    </dl>
  );
}

function evidenceRows(check: CheckResult, names: Record<string, string>): Row[] {
  const who = (id: unknown) => (typeof id === "string" ? `${names[id] ?? "Unknown"} (${id})` : String(id));
  const days = (n: unknown) => `${n} day${n === 1 ? "" : "s"}`;
  const formatters: Record<string, [string, (v: unknown) => string]> = {
    requested: ["Requested", (v) => money(v as string)],
    captured: ["Captured on PayPal", (v) => money(v as string)],
    already_refunded: ["Already refunded", (v) => money(v as string)],
    refundable: ["Still refundable", (v) => money(v as string)],
    order_customer: ["Order owner on PayPal", who],
    session_customer: ["Signed-in customer", who],
    customer_id: ["Customer", who],
    capture_id: ["PayPal capture", String],
    paypal_status: ["PayPal order status", String],
    pending_decision: ["Already waiting", (v) => `Decision #${v}`],
    paid_days_ago: ["Paid", (v) => `${days(v)} ago`],
    window_days: ["Refund window", days],
    limit: ["Auto-approve limit", (v) => money(v as string)],
    refunded_on_order: ["Refunded on this order", (v) => money(v as string)],
    total_after: ["Total after this refund", (v) => money(v as string)],
    refunds_30d: ["Refunds in 30 days", String],
    refunded_30d: ["Refunded in 30 days", (v) => money(v as string)],
    score: ["Risk score", (v) => Number(v).toFixed(2)],
    tactics: ["Tactics", (v) => (Array.isArray(v) && v.length ? v.map(humanize).join(", ") : "None")],
    source: ["Scored by", (v) => (v === "llm" ? "Claude" : "Keyword heuristic")],
    trackers: [
      "PayPal tracking",
      (v) =>
        Array.isArray(v) && v.length
          ? v.map((t) => `${t.carrier} ${t.tracking_number} (${humanize(String(t.status).toLowerCase())})`).join(", ")
          : "No tracking on file",
    ],
  };
  return Object.entries(check.evidence ?? {}).map(([key, value]) => {
    const known = formatters[key];
    if (known) return [known[0], known[1](value)];
    return [humanize(key), typeof value === "string" ? value : JSON.stringify(value)];
  });
}

function RiskPanel({ decision }: { decision: Decision }) {
  const risk = decision.risk ?? {};
  const score = typeof risk.score === "number" ? risk.score : undefined;
  const flagged = decision.checks.some((c) => c.check === "manipulation" && c.outcome !== "allow");
  return (
    <section className="detail-section">
      <h3 className="detail-h">Manipulation risk</h3>
      <div className={`risk ${flagged ? "is-flagged" : ""}`}>
        <div className="risk-score">
          <span className="num">{score === undefined ? "n/a" : score.toFixed(2)}</span>
          <span className="risk-scale">
            {flagged ? "Over the review threshold" : "Under the review threshold"}
          </span>
        </div>
        <div className="risk-body">
          {risk.tactics && risk.tactics.length > 0 ? (
            <ul className="tags">
              {risk.tactics.map((t) => (
                <li key={t} className="tag">
                  {humanize(t)}
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted">No manipulation tactics detected.</p>
          )}
          {risk.rationale && <p className="risk-rationale">{risk.rationale}</p>}
          <p className="risk-source">
            Scored by {risk.source === "llm" ? "Claude" : "keyword heuristic"}. Risk can only send a refund for
            review; it never approves one.
          </p>
        </div>
      </div>
    </section>
  );
}

function ReviewActions({ id, onResolved }: { id: number; onResolved: () => void }) {
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState<"approve" | "deny">();
  const [error, setError] = useState<string>();

  const act = async (kind: "approve" | "deny") => {
    setBusy(kind);
    setError(undefined);
    try {
      await (kind === "approve" ? api.approve(id, note) : api.deny(id, note));
      setNote("");
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 409
          ? "Someone already resolved this request."
          : err instanceof Error
            ? err.message
            : String(err),
      );
    } finally {
      setBusy(undefined);
      onResolved();
    }
  };

  return (
    <div className="review">
      <div className="review-copy">
        <p className="review-title">Waiting on your decision</p>
        <p className="review-text">
          Approving re-checks the order on PayPal, then issues the refund. Denying closes it with no money moved.
        </p>
      </div>
      <label className="field review-note">
        <span className="field-label">Note (optional)</span>
        <input
          className="input"
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="Visible in the audit log"
          maxLength={500}
        />
      </label>
      <div className="review-buttons">
        <button type="button" className="btn btn-approve" disabled={!!busy} onClick={() => act("approve")}>
          <Check weight="bold" aria-hidden="true" />
          {busy === "approve" ? "Approving" : "Approve refund"}
        </button>
        <button type="button" className="btn btn-deny" disabled={!!busy} onClick={() => act("deny")}>
          <Prohibit weight="bold" aria-hidden="true" />
          {busy === "deny" ? "Denying" : "Deny"}
        </button>
      </div>
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}

function Resolution({ decision: d }: { decision: Decision }) {
  if (!d.resolved_at && !d.error && !d.refund_id) return null;
  return (
    <dl className="resolution">
      {d.resolved_at && (
        <div>
          <dt>{d.status === "denied" ? "Denied" : "Approved"} by</dt>
          <dd>
            {humanize(d.resolved_by)} on {dateTime(d.resolved_at)}
            {d.resolved_note && <span className="resolution-note">"{d.resolved_note}"</span>}
          </dd>
        </div>
      )}
      {d.refund_id && (
        <div>
          <dt>PayPal refund</dt>
          <dd className="mono">{d.refund_id}</dd>
        </div>
      )}
      {d.error && (
        <div className="is-error">
          <dt>Problem</dt>
          <dd>{d.error}</dd>
        </div>
      )}
    </dl>
  );
}
