import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiClient, dateTime } from "@stock-scanner/client";
import ChatCharts, { ChatChart } from "./ChatCharts";
import { ErrorBox, Metric, statusLabel } from "../../components/UI";

type Mark = {
  equity: string | null;
  cash: string;
  change_pct: number | null;
  drawdown_pct: number | null;
  cost_sensitivity_equity: string | null;
};
type Experiment = {
  id: string;
  name: string;
  status: "active" | "paused";
  start_date: string;
  starting_equity: string;
  note: string;
  policy: {
    max_positions: number;
    max_position_weight: string;
    execution: string;
  };
  books: {
    agent: {
      cash: string;
      positions: Record<string, string>;
      fills: {
        session: string;
        symbol: string;
        side: string;
        quantity: string;
        price: string;
      }[];
    };
  };
  pending: Record<
    string,
    { session: string; status: string; weights: Record<string, string> }
  >;
  snapshots: {
    session: string;
    quality: string;
    books: Record<string, Mark>;
  }[];
  gaps: string[];
  charts: ChatChart[];
  decisions: {
    report_id: string;
    completed_at: string;
    decision: string;
    status: string;
    execution_session: string;
    target_weights: { symbol: string; weight: string; reason: string }[];
  }[];
  manager_job?: { status: string; error?: { message: string } | null } | null;
};
const dollars = (value: string | null | undefined) =>
  value == null
    ? "Unavailable"
    : Number(value).toLocaleString("en-US", {
        style: "currency",
        currency: "USD",
        minimumFractionDigits: 0,
        maximumFractionDigits: 2,
      });

export default function PaperExperiments({ api }: { api: ApiClient }) {
  const client = useQueryClient();
  const data = useQuery({
    queryKey: ["paper-experiments"],
    queryFn: () => api.request<Experiment[]>("/paper/experiments"),
    refetchInterval: 15000,
  });
  const change = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) =>
      api.request("/paper/experiments/" + id, "PATCH", { status }),
    onSuccess: () =>
      client.invalidateQueries({ queryKey: ["paper-experiments"] }),
  });
  if (!data.data?.length) return <ErrorBox error={data.error} />;
  return (
    <details
      className="background-work paper-experiments"
      open={new URLSearchParams(location.search).has("paper")}
    >
      <summary>
        Paper portfolio ·{" "}
        {dollars(
          data.data[0].snapshots.at(-1)?.books.agent.equity ??
            (data.data[0].snapshots.length
              ? null
              : data.data[0].starting_equity),
        )}
      </summary>
      {data.data.map((experiment) => {
        const last = experiment.snapshots.at(-1),
          mark = last?.books.agent,
          decision = experiment.decisions.at(-1),
          pending = experiment.pending.agent;
        return (
          <section
            className="padded"
            key={experiment.id}
            aria-label={experiment.name}
          >
            <div className="inline">
              <h2>{experiment.name}</h2>
              <span className="badge">{experiment.status}</span>
              <button
                disabled={change.isPending}
                onClick={() =>
                  change.mutate({
                    id: experiment.id,
                    status:
                      experiment.status === "active" ? "paused" : "active",
                  })
                }
              >
                {experiment.status === "active"
                  ? "Pause new decisions"
                  : "Resume decisions"}
              </button>
            </div>
            <p className="muted">
              Started {experiment.start_date} ·{" "}
              {dollars(experiment.starting_equity)} simulated cash · No real
              money
            </p>
            <div className="metrics">
              <Metric
                label="Hypothetical equity"
                value={dollars(mark ? mark.equity : experiment.starting_equity)}
                note={
                  last
                    ? `Marked through ${last.session} · ${statusLabel(last.quality)}`
                    : "Opening balance; awaiting first completed valuation"
                }
              />
              <Metric
                label="Cash"
                value={dollars(experiment.books.agent.cash)}
              />
              <Metric
                label="Price-only change"
                value={
                  mark?.change_pct == null
                    ? "Awaiting valuation"
                    : `${mark.change_pct.toFixed(2)}%`
                }
              />
              <Metric
                label="Drawdown from peak"
                value={
                  mark?.drawdown_pct == null
                    ? "Awaiting valuation"
                    : `${mark.drawdown_pct.toFixed(2)}%`
                }
              />
            </div>
            <p>
              {decision
                ? `Latest decision: ${decision.decision} · ${statusLabel(decision.status)} · ${dateTime(decision.completed_at)}`
                : `First manager decision: ${statusLabel(experiment.manager_job?.status ?? "waiting_for_research")}`}
            </p>
            {experiment.manager_job?.error && (
              <p className="muted">{experiment.manager_job.error.message}</p>
            )}
            {pending && (
              <p className="muted">
                Hypothetical execution {pending.status} · target session{" "}
                {pending.session}. Future daily-bar prices determine fills.
              </p>
            )}
            {!!experiment.gaps.length && (
              <p className="muted">
                Research and valuation gaps: {experiment.gaps.join(", ")}
              </p>
            )}
            {experiment.snapshots.length ? (
              <ChatCharts charts={experiment.charts} />
            ) : (
              <p className="muted">
                Equity curves begin with completed market valuations. The
                experiment starts today; proposals use future prices.
              </p>
            )}
            <details>
              <summary>Holdings & decision history</summary>
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Stock</th>
                      <th>Simulated shares</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(experiment.books.agent.positions).map(
                      ([symbol, quantity]) => (
                        <tr key={symbol}>
                          <td>{symbol}</td>
                          <td>
                            {Number(quantity).toLocaleString(undefined, {
                              maximumFractionDigits: 8,
                            })}
                          </td>
                        </tr>
                      ),
                    )}
                  </tbody>
                </table>
              </div>
              {!Object.keys(experiment.books.agent.positions).length && (
                <p>
                  No resolved hypothetical holdings yet. Cash is a valid
                  allocation.
                </p>
              )}
              {experiment.decisions
                .slice()
                .reverse()
                .map((row) => (
                  <p key={row.report_id}>
                    <a href={`?report=${row.report_id}#home`}>
                      {dateTime(row.completed_at)} · {row.decision} ·{" "}
                      {statusLabel(row.status)}
                    </a>
                    {row.target_weights
                      .map(
                        (target) =>
                          ` · ${target.symbol} ${(Number(target.weight) * 100).toFixed(1)}%`,
                      )
                      .join("")}
                  </p>
                ))}
              <p className="muted">
                Up to {experiment.policy.max_positions} positions ·{" "}
                {(Number(experiment.policy.max_position_weight) * 100).toFixed(
                  0,
                )}
                % per position. {experiment.policy.execution}.
              </p>
              <p className="muted">
                Ten-basis-point cost sensitivity:{" "}
                {mark
                  ? dollars(mark.cost_sensitivity_equity)
                  : "Awaiting resolved fills and valuation"}
                . Primary results exclude fees and dividends.
              </p>
            </details>
            <p className="muted">
              {experiment.note} Ask Steve to show the experiment, explain a
              decision, or compare it with SPY.
            </p>
            <ErrorBox error={change.error} />
          </section>
        );
      })}
    </details>
  );
}

export function HistorySummary({ api }: { api: ApiClient }) {
  const data = useQuery({
    queryKey: ["market-history"],
    queryFn: () =>
      api.request<{
        first_session: string;
        last_session: string;
        required_sessions: number;
        missing_sessions: number;
        retained_sessions: number;
      }>("/market/history"),
    refetchInterval: 15000,
  });
  if (!data.data) return <ErrorBox error={data.error} />;
  const value = data.data;
  return (
    <p className="padded muted">
      Market archive · {value.required_sessions - value.missing_sessions}/
      {value.required_sessions} sessions cached for {value.first_session} →{" "}
      {value.last_session}.
      {value.missing_sessions
        ? ` Collecting ${value.missing_sessions} missing sessions.`
        : " Daily data collection complete."}{" "}
      {value.retained_sessions} sessions retained; new daily scans extend the
      archive.
    </p>
  );
}
