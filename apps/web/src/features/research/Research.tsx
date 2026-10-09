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
  usableDailyReport,
  researchState,
  dateTime,
  DailyReport,
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
import SecResearch from "./SecResearch";
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
  const [selection, setSelection] = useState({
    context: `candidates:${usableDailyReport(reports, params.get("report"))?.id}`,
    symbol: params.get("symbol") ?? "",
  });
  const [view, setView] = useState<"3D" | "List">("List");
  const report = usableDailyReport(daily, reportId);
  const portfolio =
    portfolios.find((p) => p.id === portfolioId) ?? portfolios[0];
  const date = scope === "portfolio" ? latest : report?.data_date;
  const selectionContext =
    scope === "portfolio"
      ? `portfolio:${portfolio?.id}:${date}`
      : `${scope}:${report?.id}`;
  const selected =
    selection.context === selectionContext ? selection.symbol : "";
  const setSelected = (symbol: string) =>
    setSelection({ context: selectionContext, symbol });
  const movement = useMovement(
    api,
    scope,
    period,
    report?.id,
    portfolio?.id,
    date,
  );
  const [candleRange,setCandleRange]=useState<"1M"|"3M"|"1Y"|"2Y">('1M');
  const bars = useBars(api, selected, date, candleRange==='2Y'?2:1);
  const content = useQuery({
    queryKey: ["report", report?.id],
    queryFn: () => api.report(report!.id),
    enabled: !!report,
    staleTime: Infinity,
  });
  useEffect(() => {
    if (
      movement.data &&
      !movement.isFetching &&
      !movement.data.items.some((i) => i.symbol === selected)
    )
      setSelected(movement.data.items[0]?.symbol ?? "");
  }, [movement.data, movement.isFetching, selectionContext]);
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
  const blocked =
    scope !== "portfolio" && report?.quality.startsWith("blocked");
  const latestBlocked =
    daily[0]?.quality.startsWith("blocked") && daily[0].id !== report?.id;
  const runResearchUrl =
    report?.mode === "historical_snapshot"
      ? `?research=as_of_only&start_date=${report.data_date}&end_date=${report.data_date}#home`
      : "?research=current#home";
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
              aria-label="Portfolio"
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
              aria-label="Daily report"
              value={report?.id ?? ""}
              onChange={(e) => {
                setReportId(e.target.value);
                setSelection({ context: "reset", symbol: "" });
              }}
            >
              {daily.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.data_date} · {statusLabel(r.quality)} ·{" "}
                  {r.summary.run_at_utc
                    ? dateTime(r.summary.run_at_utc)
                    : `Run ${r.id.slice(0, 8)}`}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>
      {scope !== "portfolio" && latestBlocked && (
        <div className="notice warning" role="status">
          A newer scan needs attention. Showing the latest usable report, with
          its original date and coverage.
          <button
            onClick={() => {
              setReportId(daily[0].id);
              setSelection({ context: "reset", symbol: "" });
            }}
          >
            Inspect the blocked scan
          </button>
        </div>
      )}
      {content.data && scope !== "portfolio" && (
        <ResearchNotice report={content.data} href={runResearchUrl} />
      )}
      <div className="context-line">
        {scope !== "portfolio" && report && (
          <>
            Scan <Badge>{report.quality}</Badge> · {statusLabel(report.mode)}{" "}
            ·{" "}
          </>
        )}
        {date
          ? `As of ${date} · Completed session`
          : "No daily report available"}
        {movement.data && !blocked && (
          <>
            {" "}
            · {movement.data.start_date} → {movement.data.data_date} · Movement
            data: <Badge>{movement.data.quality}</Badge>
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
          <ErrorBox
            error={movement.error}
            onRetry={() => void movement.refetch()}
          />
          {movement.isFetching && (
            <p className="loading" role="status">
              Reading your dated market cache. The first load can take longer;
              returning views reuse it.
            </p>
          )}
          {!movement.data && !movement.isFetching && !movement.error && (
            <Empty>
              {scope === "portfolio" ? (
                <>
                  <p>Create a portfolio and supply holdings to see movement.</p>
                  <a className="primary" href="#portfolio">
                    Create a portfolio
                  </a>
                </>
              ) : (
                "Run a daily scan to begin research."
              )}
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
          {selected && !blocked ? (
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
              <ErrorBox
                error={bars.error}
                onRetry={() => void bars.refetch()}
              />
              {bars.isFetching &&
                (!bars.data ? (
                  <div className="chart-skeleton" role="status">
                    <span />
                    <p>Loading dated daily candles…</p>
                  </div>
                ) : (
                  <p className="loading">Refreshing cached daily candles…</p>
                ))}
              {bars.data && <Candles data={bars.data} pivot={metrics?.pivot} range={candleRange} onRangeChange={setCandleRange}/>}
              {metrics && (
                <Disclosure title="Why it made the cut" open>
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
              <Disclosure title="Research & sources" open={!research}>
                <ErrorBox
                  error={content.error}
                  onRetry={() => void content.refetch()}
                />
                {research ? (
                  <>
                    <p className="muted">
                      Checked {dateTime(research.checked_at)}
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
                    {content.isPending
                      ? "Loading company research…"
                      : content.data &&
                          [
                            "not_requested",
                            "not_run",
                            "offline_unavailable",
                          ].includes(researchState(content.data))
                        ? "Company research was not run in this scan."
                        : "No company research was produced for this symbol; candidate limits and source gaps may apply."}{" "}
                    Technical metrics do not establish a catalyst or financial
                    health.{" "}
                    <button
                      onClick={() =>
                        document
                          .getElementById("sec-research")
                          ?.scrollIntoView({ behavior: "smooth" })
                      }
                    >
                      Read company filings & reported holdings ↓
                    </button>
                  </p>
                )}
              </Disclosure>
            </>
          ) : (
            <Empty>
              {blocked
                ? "This scan is blocked. Its exact errors are shown below."
                : "Select a stock to inspect its daily candles."}
            </Empty>
          )}
        </Panel>
      </div>
      <SecResearch
        api={api}
        reports={reports}
        reportId={report?.id}
        selected={selected}
      />
      {content.data && (
        <Disclosure
          title="Coverage, screening reasons & data errors"
          open={!!blocked}
        >
          <Coverage report={content.data} />
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
function ResearchNotice({
  report,
  href,
}: {
  report: DailyReport;
  href: string;
}) {
  const state = researchState(report);
  const message: Record<string, string> = {
    not_requested: "Company research was not enabled in this scan.",
    not_run:
      "Company research was not run in this scan. Older reports do not record whether it was disabled or unavailable offline.",
    offline_unavailable:
      "Company research was requested, but offline mode prevented source access.",
    blocked:
      "Company research could not finish because the scan was blocked. Resolve the exact error below before running again.",
    no_candidates:
      "Research was enabled; no candidates passed screening in the valid histories evaluated.",
    partial:
      "Company research ran with source gaps. Review each company's facts and missing information.",
    complete:
      "Company research ran for the leading candidates, within the configured limit.",
    legacy_available:
      "Company research is available for some symbols. Review their sources and gaps.",
    unknown: "This older report does not record whether company research ran.",
  };
  return (
    <div className="notice" role="status">
      <strong>Company research</strong>
      <p>{message[state] ?? "Company research status is unavailable."}</p>
      {["not_requested", "not_run", "offline_unavailable", "unknown"].includes(
        state,
      ) && <a href={href}>Prepare a scan with research →</a>}
      {!!report.research_run?.unchecked_candidates && (
        <p>
          {report.research_run.unchecked_candidates} candidates were outside
          this run's company-research limit.
        </p>
      )}
    </div>
  );
}
function Coverage({ report }: { report: DailyReport }) {
  const coverage = report.coverage ?? {};
  const fields = [
    ["required_sessions", "Required trading sessions"],
    ["cached_sessions", "Cached trading sessions"],
    ["selected_equities", "Selected equities"],
    ["valid_histories", "Valid histories"],
    ["insufficient_history", "Insufficient histories"],
    ["data_errors", "Histories with data errors"],
  ];
  return (
    <>
      <dl className="coverage-facts">
        {fields.map(([key, label]) => (
          <div key={key}>
            <dt>{label}</dt>
            <dd>
              {typeof coverage[key] === "number"
                ? Number(coverage[key]).toLocaleString("en-US")
                : "Unavailable"}
            </dd>
          </div>
        ))}
      </dl>
      {!!Object.keys(report.filter_counts ?? {}).length && (
        <div className="table-scroll">
          <table>
            <caption>
              Screening exclusions — one stock can fail multiple rules
            </caption>
            <thead>
              <tr>
                <th>Rule</th>
                <th>Stocks</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(report.filter_counts ?? {}).map(
                ([rule, count]) => (
                  <tr key={rule}>
                    <td>{rule.replaceAll("_", " ")}</td>
                    <td>{count.toLocaleString("en-US")}</td>
                  </tr>
                ),
              )}
            </tbody>
          </table>
        </div>
      )}
      {!!report.errors?.length && (
        <div className="table-scroll">
          <table>
            <caption>Exact data and source errors</caption>
            <thead>
              <tr>
                <th>Source / type</th>
                <th>Issue</th>
                <th>Next step</th>
              </tr>
            </thead>
            <tbody>
              {report.errors.map((error, i) => {
                const e =
                  typeof error === "object" && error !== null
                    ? (error as Record<string, unknown>)
                    : {};
                const message = String(
                  e.message ??
                    (typeof error === "string" ? error : JSON.stringify(error)),
                );
                return (
                  <tr key={i}>
                    <td>
                      {String(e.provider ?? e.type ?? "Data")}{" "}
                      {String(e.http_status ?? "")}
                      <small>{String(e.endpoint ?? "")}</small>
                    </td>
                    <td>{message}</td>
                    <td>
                      {String(e.http_status) === "403"
                        ? "Verify source entitlement and configured credential."
                        : /timed out|timeout/i.test(message)
                          ? "Check source connectivity, then resume manually in Activity."
                          : "Resolve this exact source/cache issue before resuming in Activity."}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      <Disclosure title="Raw diagnostics">
        <Json value={coverage} />
        <Json value={report.filter_counts} />
        <Json value={report.errors} />
      </Disclosure>
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
