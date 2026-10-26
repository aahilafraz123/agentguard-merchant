import type { ColDef, ICellRendererParams } from "ag-grid-community";
import { useMemo } from "react";
import { api, type Order } from "../../api";
import { Badge } from "../../components/Badge";
import { Grid } from "../../components/Grid";
import { dateTime, humanize, money, toNumber } from "../../format";
import { usePoll } from "../../hooks";
import { NUMERIC } from "./columns";

function shippingText(order: Order): string {
  if (!order.shipping || typeof order.shipping === "string") return "Not shipped";
  return order.shipping.map((t) => `${t.carrier} ${t.tracking_number}`).join(", ");
}

export function OrdersTab({ names }: { names: Record<string, string> }) {
  const orders = usePoll(api.orders, 5_000);

  const columns = useMemo<ColDef<Order>[]>(
    () => [
      { headerName: "PayPal order", field: "order_id", width: 150, cellClass: "mono", pinned: "left" },
      {
        headerName: "Customer",
        colId: "customer",
        valueGetter: (p) => (p.data ? (names[p.data.customer_id] ?? p.data.customer_id) : ""),
        width: 125,
      },
      {
        headerName: "Items",
        colId: "items",
        valueGetter: (p) => p.data?.items?.join(", ") ?? p.data?.label ?? "",
        flex: 1,
        minWidth: 200,
        tooltip: (p) => p.value,
      },
      { headerName: "Paid", field: "placed_at", width: 125, valueFormatter: (p) => dateTime(p.value), filter: false },
      ...(["total", "already_refunded", "refundable"] as const).map(
        (field): ColDef<Order> => ({
          headerName: { total: "Captured", already_refunded: "Refunded", refundable: "Refundable" }[field],
          colId: field,
          width: 105,
          type: "rightAligned",
          valueGetter: (p) => toNumber(p.data?.[field]?.split(" ")[0]),
          valueFormatter: (p) => money(p.value),
          filter: "agNumberColumnFilter",
          cellClass: field === "refundable" ? [...NUMERIC, "strong"] : NUMERIC,
        }),
      ),
      {
        headerName: "Capture",
        field: "capture_status",
        width: 125,
        cellRenderer: (p: ICellRendererParams<Order>) => {
          if (!p.data) return null;
          if (p.data.error) return <Badge tone="block">Lookup failed</Badge>;
          const status = p.data.capture_status ?? "";
          const tone = status === "COMPLETED" ? "allow" : status.includes("REFUNDED") ? "neutral" : "review";
          return <Badge tone={tone}>{humanize(status.toLowerCase()) || "Unknown"}</Badge>;
        },
      },
      {
        headerName: "Shipping",
        colId: "shipping",
        valueGetter: (p) => (p.data ? shippingText(p.data) : ""),
        width: 240,
        cellRenderer: (p: ICellRendererParams<Order>) =>
          p.data && typeof p.data.shipping !== "string" && p.data.shipping?.length ? (
            <span className="mono">{p.value}</span>
          ) : (
            <span className="muted">Not shipped</span>
          ),
      },
    ],
    [names],
  );

  return (
    <section className="panel-stack">
      <div className="section-head">
        <h2 className="section-title">Orders</h2>
        <p className="section-sub">
          Read live from PayPal. These are the facts AgentGuard checks every refund against, not what the chat says.
        </p>
      </div>
      {orders.error ? (
        <p className="form-error">Could not load orders: {orders.error.message}</p>
      ) : (
        <Grid rows={orders.data} columns={columns} rowId={(o) => o.order_id} emptyMessage="No orders yet." />
      )}
    </section>
  );
}
