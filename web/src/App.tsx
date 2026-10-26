import { lazy, Suspense } from "react";
import { api } from "./api";
import { TopNav } from "./components/TopNav";
import { usePath, usePoll } from "./hooks";
import { LiveDemoPage } from "./pages/LiveDemoPage";

// The console (and AG Grid with it) loads only when someone opens it.
const ConsolePage = lazy(() => import("./pages/ConsolePage").then((m) => ({ default: m.ConsolePage })));

export function App() {
  const path = usePath();
  const health = usePoll(api.health, 15_000);
  const onConsole = path.startsWith("/console");

  return (
    <div className="app">
      <TopNav path={path} health={health.data} offline={!!health.error} />
      {onConsole ? (
        <Suspense fallback={null}>
          <ConsolePage path={path} />
        </Suspense>
      ) : (
        <LiveDemoPage health={health.data} />
      )}
    </div>
  );
}
