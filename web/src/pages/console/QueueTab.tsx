import type { ColDef, ICellRendererParams } from "ag-grid-community";
import { useMemo } from "react";
import type { Decision } from "../../api";
import { Grid } from "../../components/Grid";
import { money, toNumber } from "../../format";
import { decisionColumns } from "./columns";

interface Props {
  decisions: Decision[] | undefined;
  names: Record<string, string>;
  onOpen: (id: number) => void;
}

export function QueueTab({ decisions, names, onOpen }: Props) {
  const pending = decisions?.filter((d) => d.status === "pending");
  const held = (pending ?? []).reduce((sum, d) => sum + toNumber(d.amount), 0);

  const columns = useMemo<ColDef<Decision>[]>(() => {
    const c = decisionColumns(names);
    return [
      c.time,
      c.customer,
      c.order,
      c.amount,
      c.reason,
      c.flags,
      c.risk,
      {
        headerName: "",
        colId: "review",
        width: 110,
        sortable: false,
        filter: false,
        resizable: false,
        cellRenderer: (p: ICellRendererParams<Decision>) =>
          p.data && (
            <button type="button" className="btn btn-small" onClick={() => onOpen(p.data!.id)}>
              Review
            </button>
          ),
      },
    ];
  }, [names, onOpen]);

  return (
    <section className="panel-stack">
      <div className="section-head">
        <h2 className="section-title">Review queue</h2>
        <p className="section-sub">
          {pending?.length
            ? `${pending.length} refund${pending.length === 1 ? "" : "s"} worth ${money(held)} held for you. Approving re-checks the order on PayPal before any money moves.`
            : "Refunds AgentGuard is unsure about wait here for you."}
        </p>
      </div>
      <Grid
        rows={pending}
        columns={columns}
        rowId={(d) => String(d.id)}
        onRowClick={(d) => onOpen(d.id)}
        emptyMessage="Queue is clear. Nothing is waiting on you."
      />
    </section>
  );
}
