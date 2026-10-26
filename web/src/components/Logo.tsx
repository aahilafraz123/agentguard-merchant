/** The AgentGuard mark: a checkpoint square with the accent block it lets through. */
export function Logo() {
  return (
    <span className="logo">
      <svg viewBox="0 0 32 32" aria-hidden="true" className="logo-mark">
        <rect x="3" y="3" width="26" height="26" rx="7" className="logo-tile" />
        <rect x="10" y="10" width="12" height="12" rx="2.5" className="logo-ring" />
        <rect x="18" y="6" width="8" height="8" rx="2" className="logo-accent" />
      </svg>
      <span className="logo-word">AgentGuard</span>
    </span>
  );
}
