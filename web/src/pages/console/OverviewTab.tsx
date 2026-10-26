import { ArrowRight } from "@phosphor-icons/react";
import type { Decision, Stats } from "../../api";
import { StatusBadge } from "../../components/Badge";
import { reasonText } from "../../components/DecisionFeed";
import { EmptyState } from "../../components/EmptyState";
import { Kpis } from "../../components/Kpis";
import { Link } from "../../components/Link";
import { money, timeAgo } from "../../format";
import { useNow } from "../../hooks";

interface Props {
  decisions: Decision[] | undefined;
  stats: Stats | undefined;
  names: Record<string, string>;
  onOpen: (id: number) => void;
}

export function OverviewTab({ decisions, stats, names, onOpen }: Props) {
  const all = decisions ?? [];
  const pending = all.filter((d) => d.status === "pending");
  const incidents = all.filter((d) => d.status === "blocked" || d.status === "denied");

  return (
    <div className="overview">
      <Kpis stats={stats} showCount />

      <div className="overview-grid">
        <section className="card">
          <div className="card-head">
            <h2 className="card-title">Waiting on you</h2>
            <Link href="/console/queue" className="card-link">
              Review queue <ArrowRight weight="bold" aria-hidden="true" />
            </Link>
          </div>
          <DecisionList
            rows={pending.slice(0, 4)}
            names={names}
            onOpen={onOpen}
            empty={["Nothing is waiting on you", "Refunds AgentGuard is unsure about will appear here."]}
          />
        </section>

        <section className="card">
          <div className="card-head">
            <h2 className="card-title">Verdicts so far</h2>
          </div>
          <VerdictMix decisions={all} />
          <h3 className="card-subtitle">What the checks caught</h3>
          <CaughtBy decisions={all} />
        </section>

        <section className="card overview-wide">
          <div className="card-head">
            <h2 className="card-title">Recent incidents</h2>
            <Link href="/console/decisions" className="card-link">
              All decisions <ArrowRight weight="bold" aria-hidden="true" />
            </Link>
          </div>
          <DecisionList
            rows={incidents.slice(0, 5)}
            names={names}
            onOpen={onOpen}
            empty={["No incidents yet", "Blocked and denied refunds will appear here with their evidence."]}
          />
        </section>
      </div>
    </div>
  );
}

function DecisionList({
  rows,
  names,
  onOpen,
  empty,
}: {
  rows: Decision[];
  names: Record<string, string>;
  onOpen: (id: number) => void;
  empty: [title: string, body: string];
}) {
  const now = useNow();
  if (!rows.length) return <EmptyState title={empty[0]}>{empty[1]}</EmptyState>;
  return (
    <ul className="dlist">
      {rows.map((d) => (
        <li key={d.id}>
          <button type="button" className="dlist-item" onClick={() => onOpen(d.id)}>
            <span className="dlist-amount num">{money(d.amount)}</span>
            <span className="dlist-main">
              <span className="dlist-who">
                {names[d.customer_id] ?? d.customer_id}
                <span className="mono dlist-order">{d.order_id}</span>
              </span>
              <span className="dlist-reason">{reasonText(d)}</span>
            </span>
            <span className="dlist-side">
              <StatusBadge status={d.status} />
              <span className="dlist-time">{timeAgo(d.created_at, now)}</span>
            </span>
          </button>
        </li>
      ))}
    </ul>
  );
}

function VerdictMix({ decisions }: { decisions: Decision[] }) {
  const groups = [
    {
      key: "allow",
      label: "Refunded after checks",
      n: decisions.filter((d) => d.checks.length && (d.status === "executed" || d.status === "approved")).length,
    },
    { key: "review", label: "Awaiting review", n: decisions.filter((d) => d.status === "pending").length },
    {
      key: "block",
      label: "Blocked or denied",
      n: decisions.filter((d) => ["blocked", "denied", "failed"].includes(d.status)).length,
    },
    { key: "neutral", label: "Unguarded, no checks", n: decisions.filter((d) => !d.checks.length).length },
  ].filter((g) => g.n > 0);
  const total = groups.reduce((s, g) => s + g.n, 0);
  if (!total) return <EmptyState title="No refund requests yet" />;
  return (
    <div className="mix">
      <div className="mix-bar" role="img" aria-label={groups.map((g) => `${g.label}: ${g.n}`).join(", ")}>
        {groups.map((g) => (
          <span key={g.key} className={`mix-seg tone-${g.key}`} style={{ flexGrow: g.n }} title={`${g.label}: ${g.n}`} />
        ))}
      </div>
      <ul className="legend">
        {groups.map((g) => (
          <li key={g.key}>
            <span className={`legend-swatch tone-${g.key}`} aria-hidden="true" />
            {g.label}
            <span className="num legend-n">{g.n}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function CaughtBy({ decisions }: { decisions: Decision[] }) {
  const counts = new Map<string, { title: string; block: number; review: number }>();
  for (const d of decisions) {
    for (const c of d.checks) {
      if (c.outcome === "allow") continue;
      const row = counts.get(c.check) ?? { title: c.title, block: 0, review: 0 };
      if (c.outcome === "block") row.block += 1;
      else row.review += 1;
      counts.set(c.check, row);
    }
  }
  const rows = [...counts.values()].sort((a, b) => b.block + b.review - (a.block + a.review));
  if (!rows.length) return <p className="muted small">No checks have flagged anything yet.</p>;
  const max = Math.max(...rows.map((r) => r.block + r.review));
  return (
    <>
      <ul className="caught">
        {rows.map((r) => (
          <li key={r.title} className="caught-row">
            <span className="caught-title">{r.title}</span>
            <span className="caught-bar" style={{ width: `${((r.block + r.review) / max) * 100}%` }}>
              {r.block > 0 && <span className="caught-seg tone-block" style={{ flexGrow: r.block }} title={`Blocked: ${r.block}`} />}
              {r.review > 0 && <span className="caught-seg tone-review" style={{ flexGrow: r.review }} title={`Sent for review: ${r.review}`} />}
            </span>
            <span className="caught-n num">{r.block + r.review}</span>
          </li>
        ))}
      </ul>
      <ul className="legend">
        <li>
          <span className="legend-swatch tone-block" aria-hidden="true" />
          Blocked
        </li>
        <li>
          <span className="legend-swatch tone-review" aria-hidden="true" />
          Sent for review
        </li>
      </ul>
    </>
  );
}
