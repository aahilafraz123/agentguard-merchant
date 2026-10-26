import { MagnifyingGlass } from "@phosphor-icons/react";
import type { ColDef } from "ag-grid-community";
import { useMemo, useState } from "react";
import type { Decision, DecisionStatus } from "../../api";
import { Grid } from "../../components/Grid";
import { decisionColumns } from "./columns";

interface Props {
  decisions: Decision[] | undefined;
  names: Record<string, string>;
  onOpen: (id: number) => void;
}

const FILTERS: { key: string; label: string; statuses?: DecisionStatus[] }[] = [
  { key: "all", label: "All" },
  { key: "refunded", label: "Refunded", statuses: ["executed", "approved"] },
  { key: "pending", label: "Awaiting review", statuses: ["pending"] },
  { key: "blocked", label: "Blocked", statuses: ["blocked"] },
  { key: "denied", label: "Denied", statuses: ["denied"] },
  { key: "failed", label: "Failed", statuses: ["failed"] },
];

export function DecisionsTab({ decisions, names, onOpen }: Props) {
  const [filter, setFilter] = useState("all");
  const [search, setSearch] = useState("");
  const active = FILTERS.find((f) => f.key === filter) ?? FILTERS[0];
  const rows = decisions?.filter((d) => !active.statuses || active.statuses.includes(d.status));
  const count = (f: (typeof FILTERS)[number]) =>
    decisions?.filter((d) => !f.statuses || f.statuses.includes(d.status)).length ?? 0;

  const columns = useMemo<ColDef<Decision>[]>(() => {
    const c = decisionColumns(names);
    return [c.id, c.time, c.customer, c.order, c.amount, c.reason, c.outcome, c.status, c.why];
  }, [names]);

  return (
    <section className="panel-stack">
      <div className="section-head">
        <h2 className="section-title">All decisions</h2>
        <p className="section-sub">Every refund the support bot attempted, with the verdict and what happened next.</p>
      </div>
      <div className="toolbar">
        <div className="segmented" role="group" aria-label="Filter by status">
          {FILTERS.map((f) => (
            <button key={f.key} type="button" aria-pressed={f.key === filter} onClick={() => setFilter(f.key)}>
              {f.label}
              <span className="num seg-count">{count(f)}</span>
            </button>
          ))}
        </div>
        <label className="search">
          <MagnifyingGlass weight="bold" aria-hidden="true" />
          <span className="sr-only">Search decisions</span>
          <input
            className="input"
            type="search"
            placeholder="Search customer, order, reason"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </label>
      </div>
      <Grid
        rows={rows}
        columns={columns}
        rowId={(d) => String(d.id)}
        onRowClick={(d) => onOpen(d.id)}
        quickFilter={search}
        emptyMessage="No decisions match this filter."
      />
    </section>
  );
}
