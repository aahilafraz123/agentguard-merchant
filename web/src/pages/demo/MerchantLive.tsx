import { ArrowCounterClockwise, Lightning } from "@phosphor-icons/react";
import { useEffect, useRef, useState } from "react";
import { api, type Decision, type Stats } from "../../api";
import { DecisionDetail } from "../../components/DecisionDetail";
import { DecisionFeed } from "../../components/DecisionFeed";
import { EmptyState } from "../../components/EmptyState";
import { Kpis } from "../../components/Kpis";

interface Props {
  decisions: Decision[] | undefined;
  stats: Stats | undefined;
  names: Record<string, string>;
  error: Error | undefined;
  selectedId: number | undefined;
  onSelect: (id: number) => void;
  onChanged: () => void;
}

export function MerchantLive({ decisions, stats, names, error, selectedId, onSelect, onChanged }: Props) {
  const selected = decisions?.find((d) => d.id === selectedId);
  const detailPane = useRef<HTMLDivElement>(null);
  useEffect(() => {
    detailPane.current?.scrollTo({ top: 0 });
  }, [selectedId]);
  return (
    <section className="merchant" aria-label="Merchant live view">
      <header className="merchant-head">
        <div>
          <h1 className="merchant-title">Merchant view</h1>
          <p className="merchant-sub">
            {error ? (
              <span className="text-block">Lost connection to the API. Retrying.</span>
            ) : (
              <>
                <span className="live-dot" aria-hidden="true" />
                Every refund the bot attempts, live
              </>
            )}
          </p>
        </div>
        <DemoControls onDone={onChanged} />
      </header>

      <Kpis stats={stats} />

      <div className="merchant-body">
        <div className="merchant-feed">
          <h2 className="pane-title">Refund requests</h2>
          <DecisionFeed
            decisions={decisions}
            names={names}
            selectedId={selectedId}
            onSelect={onSelect}
            empty={
              <EmptyState title="No refund requests yet">
                Chat as a customer on the left, or load sample activity to fill the feed.
              </EmptyState>
            }
          />
        </div>
        <div className="merchant-detail" ref={detailPane}>
          {selected ? (
            <DecisionDetail key={selected.id} decision={selected} names={names} onResolved={onChanged} />
          ) : (
            <EmptyState title="Select a request to see the evidence">
              Each refund is checked against PayPal's own records: who owns the order, what is still refundable,
              tracking, the refund window and limits.
            </EmptyState>
          )}
        </div>
      </div>
    </section>
  );
}

function DemoControls({ onDone }: { onDone: () => void }) {
  const [busy, setBusy] = useState(false);
  const run = async (action: () => Promise<unknown>) => {
    setBusy(true);
    try {
      await action();
    } finally {
      setBusy(false);
      onDone();
    }
  };
  return (
    <div className="demo-controls">
      <button type="button" className="btn btn-ghost" disabled={busy} onClick={() => run(api.demoActivity)}>
        <Lightning weight="bold" aria-hidden="true" />
        Sample activity
      </button>
      <button
        type="button"
        className="btn btn-ghost"
        disabled={busy}
        onClick={() => {
          if (window.confirm("Reset the demo shop? This clears all decisions and re-creates the orders.")) {
            void run(api.reset);
          }
        }}
      >
        <ArrowCounterClockwise weight="bold" aria-hidden="true" />
        Reset
      </button>
    </div>
  );
}
