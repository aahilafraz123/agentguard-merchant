import type { ColDef, ICellRendererParams } from "ag-grid-community";
import type { Decision } from "../../api";
import { OutcomeBadge, StatusBadge } from "../../components/Badge";
import { reasonText } from "../../components/DecisionFeed";
import { STATUS_LABEL, dateTime, humanize, money, toNumber } from "../../format";

type Col = ColDef<Decision>;

/** Right-aligned tabular numbers. Setting cellClass replaces the class `type: "rightAligned"` adds. */
export const NUMERIC = ["num", "ag-right-aligned-cell"];

export function decisionColumns(names: Record<string, string>) {
  const id: Col = { headerName: "#", field: "id", width: 76, minWidth: 70, filter: "agNumberColumnFilter", sort: "desc" };
  const time: Col = {
    headerName: "Received",
    field: "created_at",
    width: 140,
    valueFormatter: (p) => dateTime(p.value),
    filter: false,
  };
  const customer: Col = {
    headerName: "Customer",
    colId: "customer",
    valueGetter: (p) => (p.data ? (names[p.data.customer_id] ?? p.data.customer_id) : ""),
    width: 135,
  };
  const order: Col = { headerName: "Order", field: "order_id", width: 140, cellClass: "mono" };
  const amount: Col = {
    headerName: "Amount",
    field: "amount",
    width: 110,
    type: "rightAligned",
    valueGetter: (p) => toNumber(p.data?.amount),
    valueFormatter: (p) => money(p.value),
    filter: "agNumberColumnFilter",
    cellClass: NUMERIC,
  };
  const reason: Col = { headerName: "Reason", field: "reason", width: 125, valueFormatter: (p) => humanize(p.value) };
  const outcome: Col = {
    headerName: "Guard verdict",
    field: "outcome",
    width: 140,
    cellRenderer: (p: ICellRendererParams<Decision>) =>
      p.data && (p.data.checks.length ? <OutcomeBadge outcome={p.data.outcome} /> : <span className="muted">No checks</span>),
  };
  const status: Col = {
    headerName: "Status",
    field: "status",
    width: 150,
    filterValueGetter: (p) => (p.data ? STATUS_LABEL[p.data.status] : ""),
    cellRenderer: (p: ICellRendererParams<Decision>) => p.data && <StatusBadge status={p.data.status} />,
  };
  const why: Col = {
    headerName: "Why",
    colId: "why",
    valueGetter: (p) => (p.data ? reasonText(p.data) : ""),
    flex: 1,
    minWidth: 260,
    tooltip: (p) => p.value,
  };
  const flags: Col = {
    headerName: "Flagged checks",
    colId: "flags",
    valueGetter: (p) =>
      p.data?.checks
        .filter((c) => c.outcome !== "allow")
        .map((c) => c.title)
        .join(", ") ?? "",
    flex: 1,
    minWidth: 260,
    tooltip: (p) => p.value,
  };
  const risk: Col = {
    headerName: "Risk",
    colId: "risk",
    width: 90,
    type: "rightAligned",
    valueGetter: (p) => (typeof p.data?.risk?.score === "number" ? p.data.risk.score : null),
    valueFormatter: (p) => (p.value === null ? "" : Number(p.value).toFixed(2)),
    filter: "agNumberColumnFilter",
    cellClass: NUMERIC,
  };
  return { id, time, customer, order, amount, reason, outcome, status, why, flags, risk };
}
