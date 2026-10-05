import { lazy, Suspense, useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  ApiClient,
  Candidate,
  Period,
  Portfolio,
  Report,
  Scope,
  money,
  pct,
  safeSource,
} from "@stock-scanner/client";
import { useBars, useMovement } from "@stock-scanner/client/queries";
import {
  Badge,
  Disclosure,
  Empty,
  ErrorBox,
  Json,
  Metric,
  Panel,
  statusLabel,
  Toggle,
} from "../../components/UI";
import Candles from "../charts/Candles";
const MovementScene = lazy(() => import("../market-scene/MovementScene"));

export default function Research({
  api,
  reports,
  portfolios,
  latest,
}: {
  api: ApiClient;
  reports: Report[];
  portfolios: Portfolio[];
  latest?: string;
}) {
  const params = new URLSearchParams(location.search);
  const [scope, setScope] = useState<Scope>("candidates");
  const [period, setPeriod] = useState<Period>("1D");
  const daily = reports.filter((r) =>
    ["live", "historical_snapshot"].includes(r.mode),
  );
  const [reportId, setReportId] = useState(params.get("report") ?? "");
  const [portfolioId, setPortfolioId] = useState("");
  const [selected, setSelected] = useState(params.get("symbol") ?? "");
  const [view, setView] = useState<"3D" | "List">("List");
  const report = daily.find((r) => r.id === reportId) ?? daily[0];
  const portfolio =
    portfolios.find((p) => p.id === portfolioId) ?? portfolios[0];
  const date = scope === "portfolio" ? latest : report?.data_date;
  const movement = useMovement(
    api,
    scope,
    period,
    report?.id,
    portfolio?.id,
    date,
  );
  const bars = useBars(api, selected, date);
  const content = useQuery({
    queryKey: ["report", report?.id],
    queryFn: () => api.report(report!.id),
    enabled: !!report,
  });
  useEffect(() => {
    if (
      movement.data &&
      !movement.data.items.some((i) => i.symbol === selected)
    )
      setSelected(movement.data.items[0]?.symbol ?? "");
  }, [movement.data]);
  useEffect(() => {
    const url = new URL(location.href);
    if (selected) url.searchParams.set("symbol", selected);
    else url.searchParams.delete("symbol");
    if (report) url.searchParams.set("report", report.id);
    history.replaceState(null, "", url);
  }, [selected, report?.id]);
  const item = movement.data?.items.find((i) => i.symbol === selected);
  const metrics = item?.metrics as Candidate | undefined;
  const research = content.data?.research?.[selected];
  return (
    <>
      <div className="workspace-controls">
        <div className="segmented" role="group" aria-label="Research scope">
          {(["portfolio", "candidates", "near_breakouts"] as const).map((s) => (
            <button
              key={s}
              className={scope === s ? "selected" : ""}
              aria-pressed={scope === s}
              onClick={() => setScope(s)}
            >
              {s === "near_breakouts"
                ? "Near breakouts"
                : s === "portfolio"
                  ? "Portfolio"
                  : "Candidates"}
            </button>
          ))}
        </div>
        <Toggle
          values={["1D", "1W", "1M"]}
          value={period}
          onChange={setPeriod}
          label="Movement period"
        />
        {scope === "portfolio" ? (
          <label className="compact-field">
            Portfolio
            <select
              value={portfolio?.id ?? ""}
              onChange={(e) => setPortfolioId(e.target.value)}
            >
              {portfolios.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </label>
        ) : (
          <label className="compact-field">
            Daily report
            <select
              value={report?.id ?? ""}
              onChange={(e) => setReportId(e.target.value)}
            >
              {daily.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.data_date} · {statusLabel(r.quality)}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>
      <div className="context-line">
        {scope !== "portfolio" && report && (
          <>
            Scan <Badge>{report.quality}</Badge> · {report.mode} ·{" "}
          </>
        )}
        {date
          ? `As of ${date} · Completed session`
          : "No daily report available"}
        {movement.data && (
          <>
            {" "}
            · {movement.data.start_date} → {movement.data.data_date}{" "}
            <Badge>{movement.data.quality}</Badge>
          </>
        )}
      </div>
      <div className="research-grid">
        <Panel
          title="Daily movement"
          aside={
            <Toggle
              values={["3D", "List"]}
              value={view}
              onChange={setView}
              label="Movement view"
            />
          }
        >
          <ErrorBox error={movement.error} />
          {movement.isFetching && (
            <p className="loading" role="status">
              Loading cached market data…
            </p>
          )}
          {!movement.data && !movement.isFetching && !movement.error && (
            <Empty>
              {scope === "portfolio"
                ? "Create a portfolio and supply holdings to see movement."
                : "Run a daily scan to begin research."}
            </Empty>
          )}
          {movement.data && (
            <>
              {!movement.data.items.length ? (
                <Empty>
                  {report?.quality.startsWith("blocked")
                    ? "This scan is blocked. Inspect its data errors."
                    : "No symbols in this scope. Candidate counts are never forced."}
                </Empty>
              ) : (
                <>
                  {view === "3D" && (
                    <Suspense fallback={<p className="loading">Loading 3D…</p>}>
                      <MovementScene
                        items={movement.data.items}
                        selected={selected}
                        onSelect={(symbol) => {
                          setSelected(symbol);
                          if (matchMedia("(max-width:700px)").matches)
                            document
                              .querySelector(".stock-detail")
                              ?.scrollIntoView({ block: "start" });
                        }}
                      />
                    </Suspense>
                  )}
                  <div className="list-header">
                    {
                      movement.data.items.filter(
                        (i) => i.quality === "complete",
                      ).length
                    }{" "}
                    valid of {movement.data.displayed_symbols} displayed ·{" "}
                    {movement.data.total_symbols} in scope
                  </div>
                  <div className="movement-list">
                    {movement.data.items.map((i) => (
                      <button
                        key={i.symbol}
                        className={`stock-row ${i.symbol === selected ? "active" : ""}`}
                        aria-pressed={i.symbol === selected}
                        onClick={() => {
                          setSelected(i.symbol);
                          if (matchMedia("(max-width:700px)").matches)
                            document
                              .querySelector(".stock-detail")
                              ?.scrollIntoView({ block: "start" });
                        }}
                      >
                        <span>
                          <strong>{i.symbol}</strong>
                          <small>{i.name ?? i.quality}</small>
                        </span>
                        <span>{money(i.close)}</span>
                        <strong
                          className={
                            i.change_percent == null
                              ? "muted"
                              : i.change_percent < 0
                                ? "negative"
                                : "positive"
                          }
                        >
                          {pct(i.change_percent)}
                        </strong>
                        <span aria-hidden="true">›</span>
                      </button>
                    ))}
                  </div>
                </>
              )}
              {!!movement.data.restore_artifact_ids.length && (
                <Disclosure title="Cold input restoration">
                  <Json value={movement.data.restore_artifact_ids} />
                  <Restore api={api} ids={movement.data.restore_artifact_ids} />
                </Disclosure>
              )}
            </>
          )}
        </Panel>
        <Panel
          className="stock-detail"
          title={selected || "Select a stock"}
          aside={
            selected ? (
              <button className="mobile-back" onClick={() => setSelected("")}>
                Back to overview
              </button>
            ) : null
          }
        >
          {selected ? (
            <>
              <div className="stock-title">
                <div>
                  <h3>{selected}</h3>
                  <span className="muted">{item?.name}</span>
                </div>
                <div>
                  <strong>{money(item?.close)}</strong>
                  <span
                    className={
                      item?.change_percent != null && item.change_percent < 0
                        ? "negative"
                        : "positive"
                    }
                  >
                    {pct(item?.change_percent)} <small>{period}</small>
                  </span>
                </div>
              </div>
              <ErrorBox error={bars.error} />
              {bars.isFetching && (
                <p className="loading">Loading daily candles…</p>
              )}
              {bars.data && <Candles data={bars.data} pivot={metrics?.pivot} />}
              {metrics && (
                <Disclosure title="Why it made the cut">
                  <div className="metrics">
                    <Metric label="Breakout" value={money(metrics.pivot)} />
                    <Metric
                      label="Extension"
                      value={pct(metrics.pivot_extension * 100)}
                    />
                    <Metric
                      label="Relative volume"
                      value={`${metrics.volume_ratio.toFixed(1)}x`}
                    />
                    <Metric
                      label="Relative strength"
                      value={`${(metrics.rs_excess * 100).toFixed(1)} pp`}
                      note={`${content.data?.rules?.rs_days ?? 63} sessions vs SPY`}
                    />
                  </div>
                </Disclosure>
              )}
              <Disclosure title="Research & sources">
                <ErrorBox error={content.error} />
                {research ? (
                  <>
                    <p className="muted">
                      Checked {research.checked_at ?? "date unavailable"}
                    </p>
                    <h4>Facts</h4>
                    {research.facts?.map((f, i) => (
                      <p key={i}>
                        {String(f.statement ?? f.text ?? "")}{" "}
                        {safeSource(f.source) && (
                          <a
                            href={safeSource(f.source)!}
                            target="_blank"
                            rel="noreferrer"
                          >
                            Source ↗
                          </a>
                        )}
                      </p>
                    ))}
                    <h4>Hypotheses</h4>
                    {research.hypotheses?.map((h, i) => (
                      <p key={i}>{h}</p>
                    ))}
                    <h4>Research gaps</h4>
                    {research.missing?.map((m, i) => (
                      <p className="warning" key={i}>
                        {m}
                      </p>
                    ))}
                  </>
                ) : (
                  <p>
                    Company research is unavailable for this symbol/report.
                    Technical metrics do not establish a catalyst or financial
                    health.
                  </p>
                )}
              </Disclosure>
            </>
          ) : (
            <Empty>Select a stock to inspect its daily candles.</Empty>
          )}
        </Panel>
      </div>
      {content.data && (
        <Disclosure title="Coverage, screening reasons & data errors">
          <div className="coverage-grid">
            <Json value={content.data.coverage} />
            <Json value={content.data.filter_counts} />
          </div>
          <Json value={content.data.errors} />
          {content.data.warnings?.map((w, i) => (
            <p key={i} className="muted">
              {w}
            </p>
          ))}
        </Disclosure>
      )}
    </>
  );
}
function Restore({ api, ids }: { api: ApiClient; ids: string[] }) {
  const [error, setError] = useState<unknown>();
  const [queued, setQueued] = useState(false);
  return (
    <>
      <button
        disabled={queued}
        onClick={async () => {
          try {
            await api.request(
              "/storage/restore-jobs",
              "POST",
              { artifact_ids: ids },
              crypto.randomUUID(),
            );
            setQueued(true);
          } catch (e) {
            setError(e);
          }
        }}
      >
        {queued ? "Restore queued; follow Activity" : "Request bounded restore"}
      </button>
      <ErrorBox error={error} />
    </>
  );
}
