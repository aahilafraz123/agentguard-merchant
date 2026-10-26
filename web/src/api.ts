// Typed client for the AgentGuard FastAPI backend (src/agentguard/api.py is the source of truth).

export type Outcome = "allow" | "escalate" | "block";
export type DecisionStatus = "executed" | "pending" | "blocked" | "approved" | "denied" | "failed";
export type GuardMode = "agentguard" | "unguarded" | "prompt_only";

export interface Health {
  ok: boolean;
  version: string;
  shop: string;
  paypal_mode: "sandbox" | "mock";
  llm_enabled: boolean;
  agent_model: string;
  detector: string;
}

export interface Customer {
  customer_id: string;
  name: string;
  email: string;
  persona: string;
}

export interface Tracker {
  carrier: string;
  tracking_number: string;
  status: string;
}

export interface Order {
  order_id: string;
  customer_id: string;
  label: string;
  created_at: string;
  status?: string;
  capture_status?: string | null;
  total?: string;
  already_refunded?: string;
  refundable?: string;
  placed_at?: string | null;
  items?: string[];
  shipping?: Tracker[] | string;
  error?: string;
}

export interface CheckResult {
  check: string;
  title: string;
  outcome: Outcome;
  detail: string;
  evidence: Record<string, unknown>;
}

export interface Risk {
  score?: number;
  tactics?: string[];
  rationale?: string;
  source?: "llm" | "heuristic";
}

export interface TranscriptLine {
  role: "customer" | "agent";
  text: string;
}

export interface Decision {
  id: number;
  created_at: string;
  session_id: string;
  customer_id: string;
  order_id: string;
  capture_id: string | null;
  amount: string;
  currency: string;
  reason: string;
  claim: string;
  outcome: Outcome;
  status: DecisionStatus;
  checks: CheckResult[];
  risk: Risk;
  summary: string;
  transcript: TranscriptLine[];
  refund_id: string | null;
  error: string | null;
  resolved_by: string | null;
  resolved_note: string | null;
  resolved_at: string | null;
}

export interface Stats {
  decisions: number;
  allowed: number;
  pending: number;
  blocked: number;
  refunded_total: string;
  held_total: string;
  prevented_total: string;
}

export interface Session {
  session_id: string;
  customer_name: string;
  mode: GuardMode;
}

export type ChatEvent =
  | { type: "tool_call"; name: string; input: Record<string, unknown> }
  | { type: "tool_result"; name: string; output: unknown; is_error: boolean }
  | {
      type: "guard_decision";
      decision_id: number;
      outcome: Outcome;
      status: DecisionStatus;
      summary: string;
      checks: CheckResult[];
      risk: Risk;
    }
  | { type: "direct_refund"; decision_id: number; refund_id: string; amount: string }
  | { type: "ticket"; ticket_id: number; summary: string }
  | { type: "guard_read_blocked"; order_id: string };

export interface ChatReply {
  reply: string;
  events: ChatEvent[];
}

export interface Policy {
  refund_window_days: number;
  auto_approve_limit: string;
  max_refunds_per_customer_30d: number;
  max_refund_total_per_customer_30d: string;
  shipped_but_not_received: Outcome;
  changed_mind_after_shipping: Outcome;
  outside_window: Outcome;
  manipulation_threshold: number;
}

export interface PolicyResponse {
  policy: Policy;
  rules: string[];
  source_text: string;
}

export interface PolicyChange {
  field: keyof Policy;
  before: string;
  after: string;
  description: string;
}

export interface CompiledPolicy {
  policy: Policy;
  rules: string[];
  changes: PolicyChange[];
  unsupported: string[];
  notes: string;
}

export interface AgentEvalConfig {
  mode: GuardMode;
  attacks_total?: number;
  attacks_succeeded?: number;
  attack_success_rate?: number;
  money_lost?: string | number;
  legit_total?: number;
  legit_refunded?: number;
  legit_escalated?: number;
  legit_blocked?: number;
  false_block_rate?: number;
  review_total?: number;
  review_correct?: number;
  review_auto_paid?: number;
  errors?: number;
}

export interface AgentEvalScenario {
  id: string;
  title?: string;
  category?: "attack" | "legit" | "review";
  tactic?: string;
  results?: Partial<Record<GuardMode, { money_moved?: string | number; outcome?: string; pass?: boolean }>>;
}

export interface AgentEval {
  generated_at?: string;
  model?: string;
  effort?: string;
  detector?: string;
  trials?: number;
  /** Number of scripted conversations (the per-scenario rows are in `scenario_table`). */
  scenarios?: number | AgentEvalScenario[];
  scenario_table?: AgentEvalScenario[];
  configs?: AgentEvalConfig[];
}

export interface GuardEval {
  generated_at?: string;
  detector?: string;
  cases?: number;
  passed?: number;
  accuracy?: number;
  attacks_auto_refunded?: number;
  legit_refused?: number;
  by_category?: Record<string, { cases: number; passed: number }>;
  confusion?: Record<string, Record<string, number>>;
  results?: {
    id: string;
    title?: string;
    category?: string;
    expected?: string;
    actual?: string;
    pass?: boolean;
    failed_checks?: string[];
    summary?: string;
  }[];
}

export interface Evals {
  guard_eval: GuardEval | null;
  agent_eval: AgentEval | null;
}

/** An HTTP error carrying FastAPI's `detail` message. */
export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: init?.body ? { "Content-Type": "application/json" } : undefined,
  });
  if (!res.ok) {
    let message = res.statusText || `Request failed (${res.status})`;
    try {
      const body = await res.json();
      if (typeof body?.detail === "string") message = body.detail;
      // FastAPI validation errors: [{loc: [...], msg: "..."}]
      else if (Array.isArray(body?.detail)) {
        message = body.detail
          .map((e: { loc?: unknown[]; msg?: string }) => `${e.loc?.slice(-1)[0] ?? "value"}: ${e.msg}`)
          .join("; ");
      }
    } catch {
      // Body was not JSON; keep the status text.
    }
    throw new ApiError(res.status, message);
  }
  return res.json() as Promise<T>;
}

const post = <T>(path: string, body: unknown) =>
  request<T>(path, { method: "POST", body: JSON.stringify(body) });

export const api = {
  health: () => request<Health>("/api/health"),
  customers: () => request<Customer[]>("/api/customers"),
  orders: () => request<Order[]>("/api/orders"),
  stats: () => request<Stats>("/api/stats"),
  decisions: (status?: DecisionStatus) =>
    request<Decision[]>(status ? `/api/decisions?status=${status}` : "/api/decisions"),
  approve: (id: number, note = "") => post<Decision>(`/api/decisions/${id}/approve`, { note }),
  deny: (id: number, note = "") => post<Decision>(`/api/decisions/${id}/deny`, { note }),
  newSession: (customer_id: string, mode: GuardMode) =>
    post<Session>("/api/sessions", { customer_id, mode }),
  sendMessage: (sessionId: string, message: string) =>
    post<ChatReply>(`/api/sessions/${sessionId}/messages`, { message }),
  policy: () => request<PolicyResponse>("/api/policy"),
  savePolicy: (policy: Policy, source_text?: string) =>
    request<PolicyResponse>("/api/policy", {
      method: "PUT",
      body: JSON.stringify({ policy, source_text }),
    }),
  compilePolicy: (text: string) => post<CompiledPolicy>("/api/policy/compile", { text }),
  evals: () => request<Evals>("/api/evals"),
  demoActivity: () => post<{ created: unknown[] }>("/api/demo/activity", {}),
  reset: () => post<{ ok: boolean }>("/api/reset", {}),
};
