import type { Stats } from "../api";
import { money } from "../format";

interface Props {
  stats: Stats | undefined;
  /** Adds the total decision count as a fourth figure. */
  showCount?: boolean;
}

export function Kpis({ stats, showCount = false }: Props) {
  const items = [
    {
      key: "refunded",
      label: "Refunded",
      value: money(stats?.refunded_total ?? 0),
      note: "Paid back to customers on PayPal",
      tone: "allow",
    },
    {
      key: "held",
      label: "Held for review",
      value: money(stats?.held_total ?? 0),
      note: stats ? `${stats.pending} waiting on you` : "",
      tone: "review",
    },
    {
      key: "prevented",
      label: "Prevented",
      value: money(stats?.prevented_total ?? 0),
      note: "Blocked or denied, never paid out",
      tone: "block",
    },
  ];
  if (showCount) {
    items.push({
      key: "count",
      label: "Refund requests",
      value: String(stats?.decisions ?? 0),
      note: "checked by AgentGuard",
      tone: "neutral",
    });
  }
  return (
    <dl className={`kpis ${stats ? "" : "is-loading"}`}>
      {items.map((item) => (
        <div key={item.key} className={`kpi tone-${item.tone}`}>
          <dt className="kpi-label">{item.label}</dt>
          <dd className="kpi-value num" key={item.value}>
            {item.value}
          </dd>
          <dd className="kpi-note">{item.note}</dd>
        </div>
      ))}
    </dl>
  );
}
