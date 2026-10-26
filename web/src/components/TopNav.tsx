import type { Health } from "../api";
import { Link } from "./Link";
import { Logo } from "./Logo";

interface Props {
  path: string;
  health: Health | undefined;
  offline: boolean;
}

export function TopNav({ path, health, offline }: Props) {
  const onConsole = path.startsWith("/console");
  return (
    <header className="topnav">
      <Link href="/" className="topnav-brand" aria-label="AgentGuard live demo">
        <Logo />
      </Link>
      <nav className="topnav-links" aria-label="Primary">
        <Link href="/" className="topnav-link" aria-current={!onConsole ? "page" : undefined}>
          Live demo
        </Link>
        <Link href="/console" className="topnav-link" aria-current={onConsole ? "page" : undefined}>
          Console
        </Link>
      </nav>
      <StatusPill health={health} offline={offline} />
    </header>
  );
}

function StatusPill({ health, offline }: { health: Health | undefined; offline: boolean }) {
  if (offline) {
    return (
      <div className="status-pill is-down" role="status">
        <span className="status-dot" />
        API unreachable
      </div>
    );
  }
  if (!health) return <div className="status-pill is-loading" aria-hidden="true" />;
  const sandbox = health.paypal_mode === "sandbox";
  return (
    <div
      className="status-pill"
      role="status"
      title={`Agent model: ${health.agent_model}. Manipulation detector: ${health.detector}.`}
    >
      <span className={`status-seg ${sandbox ? "is-live" : ""}`}>
        <span className="status-dot" />
        {sandbox ? "PayPal Sandbox" : "PayPal Simulator"}
      </span>
      <span className="status-divider" />
      <span className={`status-seg ${health.llm_enabled ? "is-live" : "is-off"}`}>
        <span className="status-dot" />
        {health.llm_enabled ? "Claude on" : "Claude off"}
      </span>
    </div>
  );
}
