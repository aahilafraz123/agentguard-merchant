import {
  ArrowUp,
  CheckCircle,
  Clock,
  MagnifyingGlass,
  Prohibit,
  ShieldWarning,
  Ticket,
  type Icon,
} from "@phosphor-icons/react";
import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { ApiError, api, type ChatEvent, type Customer, type GuardMode, type Health, type Order } from "../../api";
import { OUTCOME_LABEL, money } from "../../format";
import { CustomerPicker } from "./CustomerPicker";
import { suggestionsFor } from "./scripts";

type GuardEvent = Extract<ChatEvent, { type: "guard_decision" }>;
type DirectEvent = Extract<ChatEvent, { type: "direct_refund" }>;

type ChatItem =
  | { kind: "customer"; text: string }
  | { kind: "agent"; text: string }
  | { kind: "tool"; text: string }
  | { kind: "verdict"; event: GuardEvent }
  | { kind: "direct"; event: DirectEvent }
  | { kind: "ticket"; summary: string }
  | { kind: "hidden"; orderId: string }
  | { kind: "error"; text: string };

interface Props {
  health: Health | undefined;
  customers: Customer[];
  orders: Order[];
  /** A refund decision was made in this chat: the merchant view should open it. */
  onDecision: (id: number) => void;
  onActivity: () => void;
}

function toolLine(event: Extract<ChatEvent, { type: "tool_call" }>): string {
  const input = event.input ?? {};
  switch (event.name) {
    case "list_my_orders":
      return "Looked up your orders on PayPal";
    case "get_order":
      return `Looked up order ${String(input.order_id ?? "")} on PayPal`;
    case "issue_refund":
      return `Asked to refund ${money(input.amount as number)} on ${String(input.order_id ?? "")}`;
    case "escalate_to_human":
      return "Opened a ticket for the shop owner";
    default:
      return `Used ${event.name}`;
  }
}

function toItems(events: ChatEvent[]): ChatItem[] {
  const items: ChatItem[] = [];
  for (const event of events) {
    if (event.type === "tool_call" && event.name !== "escalate_to_human") items.push({ kind: "tool", text: toolLine(event) });
    else if (event.type === "guard_decision") items.push({ kind: "verdict", event });
    else if (event.type === "direct_refund") items.push({ kind: "direct", event });
    else if (event.type === "ticket") items.push({ kind: "ticket", summary: event.summary });
    else if (event.type === "guard_read_blocked") items.push({ kind: "hidden", orderId: event.order_id });
  }
  return items;
}

export function StoreChat({ health, customers, orders, onDecision, onActivity }: Props) {
  const [customerId, setCustomerId] = useState("");
  const [guardOn, setGuardOn] = useState(true);
  const [sessionId, setSessionId] = useState<string>();
  const [items, setItems] = useState<ChatItem[]>([]);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const scroller = useRef<HTMLDivElement>(null);
  // Bumped per conversation so a reply that lands after a switch is dropped.
  const conversation = useRef(0);
  const mode: GuardMode = guardOn ? "agentguard" : "unguarded";

  const customer = customers.find((c) => c.customer_id === customerId);
  const myOrders = orders.filter((o) => o.customer_id === customerId);
  const suggestions = suggestionsFor(customerId, orders);
  const llmOff = health ? !health.llm_enabled : false;

  // Default to the first demo customer once the list loads.
  useEffect(() => {
    if (!customerId && customers.length) setCustomerId(customers[0].customer_id);
  }, [customers, customerId]);

  // A new customer or guard mode is a fresh support conversation.
  useEffect(() => {
    if (!customerId) return;
    let cancelled = false;
    conversation.current += 1;
    setItems([]);
    setSessionId(undefined);
    api
      .newSession(customerId, mode)
      .then((s) => !cancelled && setSessionId(s.session_id))
      .catch((err: Error) => !cancelled && setItems([{ kind: "error", text: err.message }]));
    return () => {
      cancelled = true;
    };
  }, [customerId, mode]);

  useEffect(() => {
    scroller.current?.scrollTo({ top: scroller.current.scrollHeight, behavior: "smooth" });
  }, [items, sending]);

  const send = async (text: string) => {
    const message = text.trim();
    if (!message || !sessionId || sending) return;
    setDraft("");
    setItems((prev) => [...prev, { kind: "customer", text: message }]);
    setSending(true);
    const current = conversation.current;
    try {
      let reply;
      try {
        reply = await api.sendMessage(sessionId, message);
      } catch (err) {
        // The backend forgets sessions on reset; start a new one and retry once.
        if (!(err instanceof ApiError && err.status === 404)) throw err;
        const fresh = await api.newSession(customerId, mode);
        setSessionId(fresh.session_id);
        reply = await api.sendMessage(fresh.session_id, message);
      }
      if (current !== conversation.current) return;
      const eventItems = toItems(reply.events);
      setItems((prev) => [...prev, ...eventItems, ...(reply.reply ? [{ kind: "agent", text: reply.reply } as const] : [])]);
      const decided = [...reply.events].reverse().find((e) => e.type === "guard_decision" || e.type === "direct_refund");
      if (decided && "decision_id" in decided) onDecision(decided.decision_id);
      onActivity();
    } catch (err) {
      if (current !== conversation.current) return;
      const text =
        err instanceof ApiError && err.status === 503
          ? `The support bot is offline. ${err.message || "Add ANTHROPIC_API_KEY to chat."}`
          : err instanceof Error
            ? err.message
            : String(err);
      setItems((prev) => [...prev, { kind: "error", text }]);
    } finally {
      setSending(false);
    }
  };

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    void send(draft);
  };

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void send(draft);
    }
  };

  return (
    <section className={`store ${guardOn ? "" : "is-unguarded"}`} aria-label="Kettle & Crow support chat">
      <header className="store-head">
        <div className="store-brand">
          <span className="store-name">Kettle &amp; Crow</span>
          <span className="store-kicker">Coffee Roasters support</span>
        </div>
        <GuardSwitch on={guardOn} onChange={setGuardOn} />
      </header>

      <div className="store-account">
        <CustomerPicker customers={customers} value={customerId} onChange={setCustomerId} />
        {customer && <p className="store-persona">{customer.persona}</p>}
      </div>

      {myOrders.length > 0 && (
        <ul className="store-orders" aria-label="Your orders">
          {myOrders.map((o) => (
            <li key={o.order_id}>
              <button
                type="button"
                className="order-chip"
                title="Add this order ID to your message"
                onClick={() => setDraft((d) => (d.includes(o.order_id) ? d : `${d}${d && !d.endsWith(" ") ? " " : ""}${o.order_id} `))}
              >
                <span className="order-chip-label">{o.label || o.order_id}</span>
                <span className="order-chip-meta">
                  <span className="mono">{o.order_id}</span>
                  <span className="num">{money(o.total?.split(" ")[0])}</span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}

      <div className="chat" ref={scroller} aria-live="polite">
        <div className="bubble is-agent">
          Hi{customer ? ` ${customer.name.split(" ")[0]}` : ""}, I'm the Kettle &amp; Crow assistant. I can look up
          your orders and sort out refunds.
        </div>
        {items.map((item, i) => (
          <ChatLine key={i} item={item} onOpen={onDecision} />
        ))}
        {sending && (
          <div className="bubble is-agent is-typing" aria-label="Assistant is typing">
            <span />
            <span />
            <span />
          </div>
        )}
      </div>

      <form className="composer" onSubmit={onSubmit}>
        {llmOff && (
          <p className="composer-note">
            <ShieldWarning weight="bold" aria-hidden="true" />
            Claude is off, so the bot can't reply. Add ANTHROPIC_API_KEY to chat.
          </p>
        )}
        {items.length === 0 && suggestions.length > 0 && (
          <div className="suggestions">
            {suggestions.map((s) => (
              <button key={s} type="button" className="suggestion" onClick={() => setDraft(s)}>
                {s}
              </button>
            ))}
          </div>
        )}
        <div className="composer-row">
          <label className="sr-only" htmlFor="chat-input">
            Message
          </label>
          <textarea
            id="chat-input"
            className="composer-input"
            rows={2}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder={customer ? `Message as ${customer.name.split(" ")[0]}` : "Message"}
            disabled={!sessionId}
          />
          <button type="submit" className="composer-send" disabled={!draft.trim() || !sessionId || sending} aria-label="Send">
            <ArrowUp weight="bold" />
          </button>
        </div>
      </form>
    </section>
  );
}

function GuardSwitch({ on, onChange }: { on: boolean; onChange: (on: boolean) => void }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      className={`guard-switch ${on ? "is-on" : "is-off"}`}
      onClick={() => onChange(!on)}
      title={on ? "Refunds go through AgentGuard first" : "Refunds go straight to PayPal"}
    >
      <span className="guard-switch-track" aria-hidden="true">
        <span className="guard-switch-thumb" />
      </span>
      <span className="guard-switch-text">
        <span className="guard-switch-label">AgentGuard {on ? "on" : "off"}</span>
        <span className="guard-switch-sub">{on ? "Every refund is checked" : "Unguarded: no checks"}</span>
      </span>
    </button>
  );
}

const VERDICT_ICON: Record<GuardEvent["outcome"], Icon> = {
  allow: CheckCircle,
  escalate: Clock,
  block: Prohibit,
};

function ChatLine({ item, onOpen }: { item: ChatItem; onOpen: (id: number) => void }) {
  switch (item.kind) {
    case "customer":
      return <div className="bubble is-customer">{item.text}</div>;
    case "agent":
      return <div className="bubble is-agent">{item.text}</div>;
    case "tool":
      return (
        <div className="tool-line">
          <MagnifyingGlass weight="bold" aria-hidden="true" />
          {item.text}
        </div>
      );
    case "ticket":
      return (
        <div className="tool-line">
          <Ticket weight="bold" aria-hidden="true" />
          Ticket for the owner: {item.summary}
        </div>
      );
    case "hidden":
      return (
        <div className="tool-line is-guarded">
          <ShieldWarning weight="bold" aria-hidden="true" />
          AgentGuard hid order {item.orderId}: it belongs to another customer on PayPal
        </div>
      );
    case "error":
      return (
        <div className="chat-error" role="alert">
          <ShieldWarning weight="bold" aria-hidden="true" />
          {item.text}
        </div>
      );
    case "verdict": {
      const e = item.event;
      const VerdictIcon = VERDICT_ICON[e.outcome] ?? Clock;
      const tone = e.outcome === "allow" ? "allow" : e.outcome === "escalate" ? "review" : "block";
      return (
        <div className={`verdict tone-${tone}`}>
          <div className="verdict-head">
            <VerdictIcon weight="fill" aria-hidden="true" />
            <span className="verdict-label">AgentGuard: {OUTCOME_LABEL[e.outcome]}</span>
            <button type="button" className="verdict-link" onClick={() => onOpen(e.decision_id)}>
              View evidence
            </button>
          </div>
          <p className="verdict-summary">{e.summary.replace(/^(Allowed|Blocked|Needs review):\s*/, "")}</p>
        </div>
      );
    }
    case "direct":
      return (
        <div className="verdict tone-neutral">
          <div className="verdict-head">
            <ShieldWarning weight="fill" aria-hidden="true" />
            <span className="verdict-label">Refund sent with no checks</span>
            <button type="button" className="verdict-link" onClick={() => onOpen(item.event.decision_id)}>
              Open
            </button>
          </div>
          <p className="verdict-summary">
            {money(item.event.amount)} left the shop's PayPal account. Refund{" "}
            <span className="mono">{item.event.refund_id}</span>.
          </p>
        </div>
      );
  }
}
