import { CheckCircle, XCircle } from "@phosphor-icons/react";
import type { ColDef, ICellRendererParams } from "ag-grid-community";
import { useMemo } from "react";
import { api, type AgentEval, type AgentEvalConfig, type AgentEvalScenario, type GuardEval, type GuardMode } from "../../api";
import { Badge } from "../../components/Badge";
import { EmptyState } from "../../components/EmptyState";
import { Grid } from "../../components/Grid";
import { MODE_LABEL, dateTime, humanize, money, percent, toNumber, type Tone } from "../../format";
import { usePoll } from "../../hooks";

const MODES: GuardMode[] = ["unguarded", "prompt_only", "agentguard"];

const CATEGORY: Record<string, [label: string, tone: Tone]> = {
  attack: ["Attack", "block"],
  legit: ["Genuine", "allow"],
  review: ["Owner decides", "review"],
};

export function EvalsTab() {
  const evals = usePoll(api.evals, 0);
  if (evals.error) return <p className="form-error">Could not load evals: {evals.error.message}</p>;
  if (!evals.data) return <div className="skeleton-block" aria-busy="true" />;
  const { agent_eval, guard_eval } = evals.data;

  return (
    <div className="panel-stack evals">
      <div className="section-head">
        <h2 className="section-title">Evals</h2>
        <p className="section-sub">
          The same attacks and genuine requests, run against an unguarded bot, a bot with the policy in its prompt, and
          the bot behind AgentGuard.
        </p>
      </div>
      {agent_eval ? (
        <AgentEvalView data={agent_eval} />
      ) : (
        <section className="card">
          <EmptyState title="The end-to-end agent eval has not been run yet">
            Results appear here once <code>evals/results/agent_eval.json</code> exists.
          </EmptyState>
        </section>
      )}
      {guard_eval ? (
        <GuardEvalView data={guard_eval} />
      ) : (
        <section className="card">
          <EmptyState title="The guard unit eval has not been run yet">
            Results appear here once <code>evals/results/guard_eval.json</code> exists.
          </EmptyState>
        </section>
      )}
    </div>
  );
}

function Provenance({ at, extra }: { at?: string; extra: (string | false | undefined)[] }) {
  const parts = [at && `Run ${dateTime(at)}`, ...extra].filter(Boolean);
  return parts.length ? <p className="card-meta">{parts.join(". ")}</p> : null;
}

function AgentEvalView({ data }: { data: AgentEval }) {
  const configs = MODES.map((m) => data.configs?.find((c) => c.mode === m)).filter(
    (c): c is AgentEvalConfig => !!c,
  );
  const table = data.scenario_table ?? (Array.isArray(data.scenarios) ? data.scenarios : []);
  const hasReview = configs.some((c) => c.review_total);
  return (
    <>
      <section className="card">
        <div className="card-head">
          <h3 className="card-title">Scoreboard</h3>
          <Provenance
            at={data.generated_at}
            extra={[
              data.model && `Agent ${data.model}${data.effort ? ` (${data.effort} effort)` : ""}`,
              data.detector && `${data.detector === "claude" ? "Claude" : "Keyword"} detector`,
              data.trials !== undefined && `${data.trials} trial${data.trials === 1 ? "" : "s"} per scenario`,
            ]}
          />
        </div>
        {configs.length ? (
          <>
            <div className="charts">
              <RateChart
                title="Attack success rate"
                caption="Share of attacks that moved money. Lower is better."
                configs={configs}
                value={(c) => c.attack_success_rate}
                detail={(c) =>
                  c.attacks_total !== undefined ? `${c.attacks_succeeded ?? 0} of ${c.attacks_total}` : undefined
                }
              />
              <RateChart
                title="False-block rate"
                caption="Share of genuine requests refused. Lower is better."
                configs={configs}
                value={(c) => c.false_block_rate}
                detail={(c) => (c.legit_total !== undefined ? `${c.legit_blocked ?? 0} of ${c.legit_total}` : undefined)}
              />
            </div>
            <table className="scoreboard">
              <thead>
                <tr>
                  <th scope="col">Mode</th>
                  <th scope="col">Money lost to attacks</th>
                  <th scope="col">Attacks that saw another customer's order</th>
                  <th scope="col">Genuine refunds paid</th>
                  <th scope="col">Genuine sent to review</th>
                  <th scope="col">Genuine blocked</th>
                  {hasReview && <th scope="col">Owner cases sent to review</th>}
                </tr>
              </thead>
              <tbody>
                {configs.map((c) => (
                  <tr key={c.mode} className={c.mode === "agentguard" ? "is-ours" : undefined}>
                    <th scope="row">{MODE_LABEL[c.mode] ?? c.mode}</th>
                    <td className="num">{c.money_lost !== undefined ? money(c.money_lost) : "n/a"}</td>
                    <td className="num">{ratio(c.attacks_leaked_data, c.attacks_total)}</td>
                    <td className="num">{ratio(c.legit_refunded, c.legit_total)}</td>
                    <td className="num">{ratio(c.legit_escalated, c.legit_total)}</td>
                    <td className="num">{ratio(c.legit_blocked, c.legit_total)}</td>
                    {hasReview && <td className="num">{ratio(c.review_correct, c.review_total)}</td>}
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        ) : (
          <EmptyState title="No configurations in this eval run" />
        )}
      </section>
      {table.length > 0 && <ScenarioGrid scenarios={table} />}
    </>
  );
}

function ratio(n: number | undefined, total: number | undefined) {
  return n === undefined || total === undefined ? "n/a" : `${n} of ${total}`;
}

function RateChart({
  title,
  caption,
  configs,
  value,
  detail,
}: {
  title: string;
  caption: string;
  configs: AgentEvalConfig[];
  value: (c: AgentEvalConfig) => number | undefined;
  detail: (c: AgentEvalConfig) => string | undefined;
}) {
  return (
    <figure className="rate-chart">
      <figcaption>
        <span className="rate-title">{title}</span>
        <span className="rate-caption">{caption}</span>
      </figcaption>
      <ul className="rate-rows">
        {configs.map((c) => {
          const v = value(c);
          const pct = v === undefined ? 0 : Math.max(0, Math.min(1, v)) * 100;
          const extra = detail(c);
          return (
            <li key={c.mode} className={`rate-row ${c.mode === "agentguard" ? "is-ours" : ""}`} title={extra ? `${MODE_LABEL[c.mode]}: ${extra}` : undefined}>
              <span className="rate-mode">{MODE_LABEL[c.mode] ?? c.mode}</span>
              <span className="rate-plot">
                <span className="rate-bar" style={{ width: `${pct}%` }} />
                <span className="rate-value num">{percent(v)}</span>
              </span>
            </li>
          );
        })}
      </ul>
    </figure>
  );
}

function ScenarioGrid({ scenarios }: { scenarios: AgentEvalScenario[] }) {
  const columns = useMemo<ColDef<AgentEvalScenario>[]>(
    () => [
      { headerName: "Scenario", colId: "title", valueGetter: (p) => p.data?.title ?? p.data?.id, flex: 1, minWidth: 240, tooltip: (p) => p.value },
      {
        headerName: "Type",
        field: "category",
        width: 140,
        cellRenderer: (p: ICellRendererParams<AgentEvalScenario>) =>
          p.value ? <Badge tone={CATEGORY[p.value]?.[1] ?? "neutral"}>{CATEGORY[p.value]?.[0] ?? humanize(p.value)}</Badge> : null,
      },
      { headerName: "Tactic", field: "tactic", width: 170, valueFormatter: (p) => humanize(p.value) },
      ...MODES.map(
        (mode): ColDef<AgentEvalScenario> => ({
          headerName: MODE_LABEL[mode],
          colId: mode,
          width: 190,
          valueGetter: (p) => p.data?.results?.[mode]?.outcome ?? "",
          cellRenderer: (p: ICellRendererParams<AgentEvalScenario>) => {
            const r = p.data?.results?.[mode];
            if (!r) return <span className="muted">Not run</span>;
            const moved = toNumber(r.money_moved);
            return (
              <span className={`scenario-cell ${r.pass ? "is-pass" : "is-fail"}`}>
                {r.pass ? <CheckCircle weight="fill" aria-label="Pass" /> : <XCircle weight="fill" aria-label="Fail" />}
                <span>{humanize(r.outcome) || (r.pass ? "Pass" : "Fail")}</span>
                {moved > 0 && <span className={`num ${r.pass ? "muted" : "scenario-money"}`}>{money(moved)}</span>}
              </span>
            );
          },
        }),
      ),
    ],
    [],
  );
  return (
    <section className="card card-flush">
      <div className="card-head">
        <h3 className="card-title">Scenarios</h3>
        <p className="card-meta">Pass means the bot did the right thing: paid a genuine refund, or moved no money for an attack.</p>
      </div>
      <Grid rows={scenarios} columns={columns} rowId={(s) => s.id} pageSize={25} />
    </section>
  );
}

const OUTCOMES = ["allow", "escalate", "block"];

function GuardEvalView({ data }: { data: GuardEval }) {
  const labels = [
    ...new Set([...OUTCOMES, ...Object.keys(data.confusion ?? {}), ...Object.values(data.confusion ?? {}).flatMap(Object.keys)]),
  ];
  const columns = useMemo<ColDef<NonNullable<GuardEval["results"]>[number]>[]>(
    () => [
      { headerName: "Case", colId: "title", valueGetter: (p) => p.data?.title ?? p.data?.id, flex: 1, minWidth: 240 },
      {
        headerName: "Type",
        field: "category",
        width: 130,
        cellRenderer: (p: ICellRendererParams) =>
          p.value ? <Badge tone={CATEGORY[p.value]?.[1] ?? "neutral"}>{CATEGORY[p.value]?.[0] ?? humanize(p.value)}</Badge> : null,
      },
      { headerName: "Expected", field: "expected", width: 120, valueFormatter: (p) => humanize(p.value) },
      { headerName: "Actual", field: "actual", width: 120, valueFormatter: (p) => humanize(p.value) },
      {
        headerName: "Result",
        field: "pass",
        width: 110,
        cellRenderer: (p: ICellRendererParams) =>
          p.value === undefined ? null : <Badge tone={p.value ? "allow" : "block"}>{p.value ? "Pass" : "Fail"}</Badge>,
      },
      {
        headerName: "Checks that fired",
        colId: "failed_checks",
        valueGetter: (p) => (p.data?.failed_checks ?? []).map(humanize).join(", "),
        flex: 1,
        minWidth: 200,
      },
    ],
    [],
  );

  return (
    <section className="card">
      <div className="card-head">
        <h3 className="card-title">Guard eval</h3>
        <Provenance
          at={data.generated_at}
          extra={[data.detector && `${data.detector === "claude" ? "Claude" : "Keyword"} manipulation detector`, "No agent in the loop"]}
        />
      </div>
      <div className="guard-eval">
        <div className="guard-score">
          <span className="guard-score-value num">{percent(data.accuracy, 1)}</span>
          <span className="guard-score-label">
            {data.passed ?? "?"} of {data.cases ?? "?"} cases got the expected verdict
          </span>
          <dl className="guard-facts">
            {data.attacks_auto_refunded !== undefined && (
              <div>
                <dt>Attacks auto-refunded</dt>
                <dd className="num">{data.attacks_auto_refunded}</dd>
              </div>
            )}
            {data.legit_refused !== undefined && (
              <div>
                <dt>Genuine requests refused</dt>
                <dd className="num">{data.legit_refused}</dd>
              </div>
            )}
            {Object.entries(data.by_category ?? {}).map(([cat, v]) => (
              <div key={cat}>
                <dt>{CATEGORY[cat]?.[0] ?? humanize(cat)} cases</dt>
                <dd className="num">
                  {v.passed} of {v.cases}
                </dd>
              </div>
            ))}
          </dl>
        </div>
        {data.confusion && (
          <table className="confusion">
            <caption>Expected (rows) against actual verdict (columns)</caption>
            <thead>
              <tr>
                <th />
                {labels.map((l) => (
                  <th key={l} scope="col">
                    {humanize(l)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {labels.map((expected) => (
                <tr key={expected}>
                  <th scope="row">{humanize(expected)}</th>
                  {labels.map((actual) => {
                    const n = data.confusion?.[expected]?.[actual] ?? 0;
                    return (
                      <td key={actual} className={`num ${n ? (expected === actual ? "is-hit" : "is-miss") : "is-zero"}`}>
                        {n}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      {data.results && data.results.length > 0 && (
        <Grid rows={data.results} columns={columns} rowId={(r) => r.id} pageSize={25} />
      )}
    </section>
  );
}
