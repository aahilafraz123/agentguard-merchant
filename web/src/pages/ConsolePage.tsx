import { useCallback, useMemo, useState } from "react";
import { api } from "../api";
import { DecisionDetail } from "../components/DecisionDetail";
import { Link } from "../components/Link";
import { Sheet } from "../components/Sheet";
import { usePoll } from "../hooks";
import { DecisionsTab } from "./console/DecisionsTab";
import { EvalsTab } from "./console/EvalsTab";
import { OrdersTab } from "./console/OrdersTab";
import { OverviewTab } from "./console/OverviewTab";
import { PolicyTab } from "./console/PolicyTab";
import { QueueTab } from "./console/QueueTab";

const TABS = [
  { slug: "", label: "Overview" },
  { slug: "queue", label: "Review queue" },
  { slug: "decisions", label: "All decisions" },
  { slug: "orders", label: "Orders" },
  { slug: "policy", label: "Policy" },
  { slug: "evals", label: "Evals" },
] as const;

export function ConsolePage({ path }: { path: string }) {
  const slug = path.replace(/^\/console\/?/, "").split("/")[0];
  const tab = TABS.find((t) => t.slug === slug) ?? TABS[0];

  const customers = usePoll(api.customers, 0);
  const decisions = usePoll(api.decisions, 2_500);
  const stats = usePoll(api.stats, 2_500);
  const [openId, setOpenId] = useState<number>();

  const names = useMemo(
    () => Object.fromEntries((customers.data ?? []).map((c) => [c.customer_id, c.name])),
    [customers.data],
  );
  const { refresh: refreshDecisions } = decisions;
  const { refresh: refreshStats } = stats;
  const refresh = useCallback(() => {
    void refreshDecisions();
    void refreshStats();
  }, [refreshDecisions, refreshStats]);
  const close = useCallback(() => setOpenId(undefined), []);

  const pending = decisions.data?.filter((d) => d.status === "pending") ?? [];
  const open = decisions.data?.find((d) => d.id === openId);
  const shared = { decisions: decisions.data, names, onOpen: setOpenId };

  return (
    <main className="console">
      <header className="console-head">
        <div className="console-titles">
          <h1 className="console-title">Merchant console</h1>
          <p className="console-sub">Kettle &amp; Crow Coffee Roasters</p>
        </div>
        <nav className="tabs" aria-label="Console sections">
          {TABS.map((t) => (
            <Link
              key={t.slug}
              href={t.slug ? `/console/${t.slug}` : "/console"}
              className="tab"
              aria-current={t === tab ? "page" : undefined}
            >
              {t.label}
              {t.slug === "queue" && pending.length > 0 && <span className="tab-count num">{pending.length}</span>}
            </Link>
          ))}
        </nav>
      </header>

      <div className="console-body">
        {tab.slug === "" && <OverviewTab {...shared} stats={stats.data} />}
        {tab.slug === "queue" && <QueueTab {...shared} />}
        {tab.slug === "decisions" && <DecisionsTab {...shared} />}
        {tab.slug === "orders" && <OrdersTab names={names} />}
        {tab.slug === "policy" && <PolicyTab />}
        {tab.slug === "evals" && <EvalsTab />}
      </div>

      {open && (
        <Sheet title={`Refund request #${open.id}`} onClose={close}>
          <DecisionDetail key={open.id} decision={open} names={names} onResolved={refresh} />
        </Sheet>
      )}
    </main>
  );
}
