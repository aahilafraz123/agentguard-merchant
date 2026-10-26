import { ArrowRight, Check, Sparkle } from "@phosphor-icons/react";
import { useEffect, useState } from "react";
import { ApiError, api, type CompiledPolicy, type Outcome, type Policy } from "../../api";
import { EmptyState } from "../../components/EmptyState";
import { money } from "../../format";
import { usePoll } from "../../hooks";

type NumberField = "refund_window_days" | "auto_approve_limit" | "max_refunds_per_customer_30d" | "max_refund_total_per_customer_30d";
type OutcomeField = "shipped_but_not_received" | "changed_mind_after_shipping" | "outside_window";

const NUMBER_FIELDS: { key: NumberField; label: string; unit: string; step: string }[] = [
  { key: "refund_window_days", label: "Refund window", unit: "days", step: "1" },
  { key: "auto_approve_limit", label: "Auto-approve up to", unit: "USD", step: "0.01" },
  { key: "max_refunds_per_customer_30d", label: "Refunds per customer", unit: "per 30 days", step: "1" },
  { key: "max_refund_total_per_customer_30d", label: "Refund total per customer", unit: "USD per 30 days", step: "0.01" },
];

const OUTCOME_FIELDS: { key: OutcomeField; label: string }[] = [
  { key: "shipped_but_not_received", label: "Says it never arrived, but tracking shows it shipped" },
  { key: "changed_mind_after_shipping", label: "Changed their mind after it shipped" },
  { key: "outside_window", label: "Asks after the refund window" },
];

const OUTCOME_CHOICES: { value: Outcome; label: string }[] = [
  { value: "allow", label: "Allow" },
  { value: "escalate", label: "Review" },
  { value: "block", label: "Block" },
];

const FIELD_LABEL: Record<keyof Policy, string> = {
  refund_window_days: "Refund window (days)",
  auto_approve_limit: "Auto-approve limit",
  max_refunds_per_customer_30d: "Refunds per customer, 30 days",
  max_refund_total_per_customer_30d: "Refund total per customer, 30 days",
  shipped_but_not_received: "Shipped but 'never arrived'",
  changed_mind_after_shipping: "Change of mind after shipping",
  outside_window: "Outside the window",
  manipulation_threshold: "Manipulation threshold",
};

const OUTCOME_WORD: Record<string, string> = { allow: "Allow", escalate: "Send for review", block: "Block" };

function showValue(field: keyof Policy, value: string): string {
  if (field === "auto_approve_limit" || field === "max_refund_total_per_customer_30d") return money(value);
  return OUTCOME_WORD[value] ?? value;
}

const EXAMPLE = `We take refunds within 14 days of payment. Anything over $60 I want to look at myself.
If someone says a package never arrived but it has tracking, don't refund it, block it.
No more than 3 refunds per customer a month.`;

export function PolicyTab() {
  const policy = usePoll(api.policy, 0);
  const [draft, setDraft] = useState<Policy>();
  const [saved, setSaved] = useState<string>();
  const [saveError, setSaveError] = useState<string>();
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (policy.data) setDraft(policy.data.policy);
  }, [policy.data]);

  if (policy.error) return <p className="form-error">Could not load the policy: {policy.error.message}</p>;
  if (!policy.data || !draft) return <div className="skeleton-block" aria-busy="true" />;

  const dirty = JSON.stringify(draft) !== JSON.stringify(policy.data.policy);

  const save = async (next: Policy, sourceText?: string): Promise<boolean> => {
    setSaving(true);
    setSaveError(undefined);
    setSaved(undefined);
    try {
      await api.savePolicy(next, sourceText);
      await policy.refresh();
      setSaved("Policy saved. New refund requests use it immediately.");
      return true;
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : String(err));
      return false;
    } finally {
      setSaving(false);
    }
  };

  const set = <K extends keyof Policy>(key: K, value: Policy[K]) => {
    setSaved(undefined);
    setDraft((d) => (d ? { ...d, [key]: value } : d));
  };

  return (
    <div className="policy">
      <section className="policy-main">
        <div className="section-head">
          <h2 className="section-title">Refund policy</h2>
          <p className="section-sub">What AgentGuard enforces on every refund the bot attempts.</p>
        </div>

        <ul className="rules">
          {policy.data.rules.map((rule) => (
            <li key={rule}>
              <Check weight="bold" aria-hidden="true" />
              {rule}
            </li>
          ))}
        </ul>

        <form
          className="card policy-form"
          onSubmit={(e) => {
            e.preventDefault();
            void save(draft);
          }}
        >
          <h3 className="card-title">Edit the rules</h3>
          <div className="form-grid">
            {NUMBER_FIELDS.map((f) => (
              <label key={f.key} className="field">
                <span className="field-label">{f.label}</span>
                <span className="input-unit">
                  <input
                    className="input num"
                    type="number"
                    min="0"
                    step={f.step}
                    value={String(draft[f.key])}
                    onChange={(e) =>
                      set(f.key, (f.step === "1" ? Number.parseInt(e.target.value || "0", 10) : e.target.value) as never)
                    }
                  />
                  <span className="unit">{f.unit}</span>
                </span>
              </label>
            ))}
          </div>

          <div className="outcome-fields">
            {OUTCOME_FIELDS.map((f) => (
              <div key={f.key} className="outcome-field">
                <span className="field-label" id={`lbl-${f.key}`}>
                  {f.label}
                </span>
                <div className="segmented" role="radiogroup" aria-labelledby={`lbl-${f.key}`}>
                  {OUTCOME_CHOICES.map((c) => (
                    <button
                      key={c.value}
                      type="button"
                      role="radio"
                      aria-checked={draft[f.key] === c.value}
                      className={`tone-${c.value === "escalate" ? "review" : c.value}`}
                      onClick={() => set(f.key, c.value)}
                    >
                      {c.label}
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>

          <label className="field">
            <span className="field-label">
              Manipulation threshold
              <span className="field-hint">
                Conversations scoring at or above <strong className="num">{draft.manipulation_threshold.toFixed(2)}</strong> go to
                review
              </span>
            </span>
            <input
              className="range"
              type="range"
              min="0"
              max="1"
              step="0.05"
              value={draft.manipulation_threshold}
              onChange={(e) => set("manipulation_threshold", Number(e.target.value))}
            />
          </label>

          <div className="form-actions">
            {saveError && (
              <p className="form-error" role="alert">
                {saveError}
              </p>
            )}
            {saved && !dirty && <p className="form-ok">{saved}</p>}
            <button type="button" className="btn btn-ghost" disabled={!dirty || saving} onClick={() => setDraft(policy.data!.policy)}>
              Discard
            </button>
            <button type="submit" className="btn btn-primary" disabled={!dirty || saving}>
              {saving ? "Saving" : "Save policy"}
            </button>
          </div>
        </form>
      </section>

      <PlainEnglish
        initial={policy.data.source_text}
        saving={saving}
        onSave={(compiled, text) => save(compiled.policy, text)}
      />
    </div>
  );
}

function PlainEnglish({
  initial,
  saving,
  onSave,
}: {
  initial: string;
  saving: boolean;
  onSave: (compiled: CompiledPolicy, text: string) => Promise<boolean>;
}) {
  const [text, setText] = useState(initial);
  const [compiled, setCompiled] = useState<CompiledPolicy>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();

  const compile = async () => {
    setBusy(true);
    setError(undefined);
    setCompiled(undefined);
    try {
      setCompiled(await api.compilePolicy(text));
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 503
          ? `Claude is off. ${err.message}`
          : err instanceof Error
            ? err.message
            : String(err),
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <aside className="card policy-compose">
      <h3 className="card-title">Write your policy in plain English</h3>
      <p className="card-text">
        Claude turns it into the rules above. You see every change before anything is saved.
      </p>
      <label className="field">
        <span className="field-label">Your refund policy</span>
        <textarea
          className="input textarea"
          rows={7}
          value={text}
          placeholder={EXAMPLE}
          onChange={(e) => {
            setText(e.target.value);
            setCompiled(undefined);
          }}
        />
      </label>
      <div className="form-actions">
        {!text.trim() && (
          <button type="button" className="btn btn-ghost" onClick={() => setText(EXAMPLE)}>
            Use an example
          </button>
        )}
        <button type="button" className="btn btn-primary" disabled={!text.trim() || busy} onClick={compile}>
          <Sparkle weight="bold" aria-hidden="true" />
          {busy ? "Compiling" : "Compile"}
        </button>
      </div>
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}

      {compiled && (
        <div className="diff">
          <h4 className="diff-title">Proposed changes</h4>
          {compiled.changes.length === 0 ? (
            <EmptyState title="No changes">Your text matches the current policy.</EmptyState>
          ) : (
            <ul className="diff-list">
              {compiled.changes.map((c) => (
                <li key={c.field} className="diff-row">
                  <span className="diff-field">{FIELD_LABEL[c.field] ?? c.field}</span>
                  <span className="diff-values">
                    <span className="diff-before num">{showValue(c.field, c.before)}</span>
                    <ArrowRight weight="bold" aria-hidden="true" />
                    <span className="diff-after num">{showValue(c.field, c.after)}</span>
                  </span>
                </li>
              ))}
            </ul>
          )}
          {compiled.unsupported.length > 0 && (
            <div className="diff-unsupported">
              <p className="field-label">Not enforceable yet, so not saved</p>
              <ul>
                {compiled.unsupported.map((u) => (
                  <li key={u}>{u}</li>
                ))}
              </ul>
            </div>
          )}
          {compiled.notes && <p className="diff-notes">{compiled.notes}</p>}
          <div className="form-actions">
            <button type="button" className="btn btn-ghost" onClick={() => setCompiled(undefined)}>
              Discard
            </button>
            <button
              type="button"
              className="btn btn-primary"
              disabled={saving || compiled.changes.length === 0}
              onClick={() => onSave(compiled, text).then((ok) => ok && setCompiled(undefined))}
            >
              Save these rules
            </button>
          </div>
        </div>
      )}
    </aside>
  );
}
