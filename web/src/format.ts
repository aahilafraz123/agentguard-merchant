import type { DecisionStatus, GuardMode, Outcome } from "./api";

const usd = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });

/** "48.00", "48.00 USD", 48 -> "$48.00". Anything unparseable is returned as-is. */
export function money(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") return "";
  const n = typeof value === "number" ? value : Number.parseFloat(String(value));
  return Number.isFinite(n) ? usd.format(n) : String(value);
}

export function toNumber(value: string | number | null | undefined): number {
  const n = typeof value === "number" ? value : Number.parseFloat(String(value ?? ""));
  return Number.isFinite(n) ? n : 0;
}

export function percent(value: number | undefined, digits = 0): string {
  return value === undefined || !Number.isFinite(value) ? "n/a" : `${(value * 100).toFixed(digits)}%`;
}

export function timeAgo(iso: string | null | undefined, now = Date.now()): string {
  if (!iso) return "";
  const seconds = Math.max(0, Math.round((now - new Date(iso).getTime()) / 1000));
  if (seconds < 10) return "just now";
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

export function dateTime(iso: string | null | undefined): string {
  if (!iso) return "";
  return new Date(iso).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

/** "not_received" -> "Not received" */
export function humanize(value: string | null | undefined): string {
  if (!value) return "";
  const text = value.replace(/_/g, " ").trim();
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export type Tone = "allow" | "review" | "block" | "neutral";

export const OUTCOME_LABEL: Record<Outcome, string> = {
  allow: "Allowed",
  escalate: "Needs review",
  block: "Blocked",
};

export const OUTCOME_TONE: Record<Outcome, Tone> = {
  allow: "allow",
  escalate: "review",
  block: "block",
};

export const STATUS_LABEL: Record<DecisionStatus, string> = {
  executed: "Refunded",
  pending: "Awaiting review",
  blocked: "Blocked",
  approved: "Approved",
  denied: "Denied",
  failed: "Failed",
};

export const STATUS_TONE: Record<DecisionStatus, Tone> = {
  executed: "allow",
  approved: "allow",
  pending: "review",
  blocked: "block",
  denied: "block",
  failed: "block",
};

export const MODE_LABEL: Record<GuardMode, string> = {
  unguarded: "Unguarded",
  prompt_only: "Prompt only",
  agentguard: "AgentGuard",
};
