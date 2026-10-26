import { useCallback, useMemo, useState } from "react";
import { api, type Health } from "../api";
import { usePoll } from "../hooks";
import { MerchantLive } from "./demo/MerchantLive";
import { StoreChat } from "./demo/StoreChat";

/** The split-screen demo: the shop's support chat on the left, the merchant's live view on the right. */
export function LiveDemoPage({ health }: { health: Health | undefined }) {
  const customers = usePoll(api.customers, 0);
  const orders = usePoll(api.orders, 5_000);
  const decisions = usePoll(api.decisions, 1_500);
  const stats = usePoll(api.stats, 1_500);
  const [selectedId, setSelectedId] = useState<number>();

  const names = useMemo(
    () => Object.fromEntries((customers.data ?? []).map((c) => [c.customer_id, c.name])),
    [customers.data],
  );

  const { refresh: refreshDecisions } = decisions;
  const { refresh: refreshStats } = stats;
  const { refresh: refreshOrders } = orders;
  const refreshAll = useCallback(() => {
    void refreshDecisions();
    void refreshStats();
    void refreshOrders();
  }, [refreshDecisions, refreshStats, refreshOrders]);

  return (
    <main className="live">
      <StoreChat
        health={health}
        customers={customers.data ?? []}
        orders={orders.data ?? []}
        onDecision={(id) => {
          setSelectedId(id);
          refreshAll();
        }}
        onActivity={refreshAll}
      />
      <MerchantLive
        decisions={decisions.data}
        stats={stats.data}
        names={names}
        error={decisions.error}
        selectedId={selectedId}
        onSelect={setSelectedId}
        onChanged={refreshAll}
      />
    </main>
  );
}
