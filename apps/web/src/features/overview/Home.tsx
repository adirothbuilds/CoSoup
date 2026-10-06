import { KitchenScene } from "../../components/Kitchen";
import { ArrowRight, UtensilsCrossed } from "lucide-react";
import { useEffect, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  ApiClient,
  Job,
  Report,
  ScanPlan,
  ScanRequest,
  terminalStatuses,
  dateTime,
} from "@stock-scanner/client";
import {
  ActionState,
  Badge,
  Disclosure,
  Empty,
  ErrorBox,
  Json,
  Metric,
  useAction,
  statusLabel,
} from "../../components/UI";

export function ScanForm({ api }: { api: ApiClient }) {
  const params = new URLSearchParams(location.search);
  const requested = params.get("research");
  const initialResearch =
    requested === "current" || requested === "as_of_only" ? requested : "none";
  const [mode, setMode] = useState<ScanRequest["mode"]>(
    initialResearch === "as_of_only" ? "historical_snapshot" : "live",
  );
  const [start, setStart] = useState(params.get("start_date") ?? "");
  const [end, setEnd] = useState(params.get("end_date") ?? "");
  const [offline, setOffline] = useState(initialResearch === "none");
  const [research, setResearch] =
    useState<ScanRequest["research"]>(initialResearch);
  const body: ScanRequest = {
    mode,
    research,
    offline,
    ...(mode === "historical_snapshot" && start && end
      ? { start_date: start, end_date: end }
      : {}),
  };
  const signature = JSON.stringify(body);
  const [previewSignature, setPreviewSignature] = useState("");
  const preview = useMutation({
    mutationFn: () => api.request<ScanPlan>("/scan-plans", "POST", body),
    onSuccess: () => setPreviewSignature(signature),
  });
  const run = useAction(api, "/scans");
  return (
    <div className="padded">
      <div className="form-grid">
        <label>
          Mode
          <select
            aria-label="Mode"
            value={mode}
            onChange={(e) => {
              setMode(e.target.value as ScanRequest["mode"]);
              if (research !== "none")
                setResearch(
                  e.target.value === "live" ? "current" : "as_of_only",
                );
            }}
          >
            <option value="live">Latest completed session</option>
            <option value="historical_snapshot">Historical snapshots</option>
          </select>
        </label>
        <label>
          Company research
          <select
            aria-label="Company research"
            value={research}
            onChange={(e) => {
              setResearch(e.target.value as ScanRequest["research"]);
              if (e.target.value !== "none") setOffline(false);
            }}
          >
            <option value="none">Technical screening only</option>
            <option value={mode === "live" ? "current" : "as_of_only"}>
              {mode === "live" ? "Current sources" : "Dated sources"}
            </option>
          </select>
        </label>
        {mode === "historical_snapshot" && (
          <>
            <label>
              From
              <input
                type="date"
                value={start}
                onChange={(e) => setStart(e.target.value)}
              />
            </label>
            <label>
              Through
              <input
                type="date"
                value={end}
                onChange={(e) => setEnd(e.target.value)}
              />
            </label>
          </>
        )}
        <label className="check full">
          <input
            type="checkbox"
            aria-label="Offline: require existing dated cache"
            checked={offline}
            onChange={(e) => {
              setOffline(e.target.checked);
              if (e.target.checked) setResearch("none");
            }}
          />
          Offline: require existing dated cache
        </label>
      </div>
      <p className="muted small" role="status">
        {research === "none"
          ? "Company research is off. Select current or dated sources to include it; this requires online access."
          : "Company research is on, so offline is off. Source requests use the shared provider rate limit."}
      </p>
      <div className="inline">
        <button
          disabled={
            preview.isPending ||
            (mode === "historical_snapshot" && (!start || !end))
          }
          onClick={() => preview.mutate()}
        >
          Preview date coverage
        </button>
        <button
          className="primary"
          disabled={
            run.isPending || previewSignature !== signature || !preview.data
          }
          onClick={() => run.mutate(body)}
        >
          Queue scan
        </button>
      </div>
      <ErrorBox error={preview.error} />
      <ActionState action={run} />
      {preview.data && previewSignature === signature && (
        <>
          <div className="metrics">
            <Metric
              label="Scan sessions"
              value={preview.data.sessions.length}
            />
            <Metric
              label="Missing days"
              value={preview.data.missing_sessions.length}
            />
            <Metric
              label="Cold days"
              value={preview.data.cold_sessions.length}
            />
            <Metric label="Warmup from" value={preview.data.warmup_start} />
          </div>
          <Disclosure title="Coverage details">
            <Json value={preview.data} />
          </Disclosure>
        </>
      )}
      <p className="muted small">
        Online runs download only missing days at the server's shared provider
        rate limit. Jobs continue when the browser is closed.
      </p>
    </div>
  );
}
function ReportView({ api, report }: { api: ApiClient; report: Report }) {
  const data = useQuery({
    queryKey: ["report", report.id],
    queryFn: () => api.report(report.id),
  });
  const [error, setError] = useState<unknown>();
  function save(text: string, type: string, extension: string) {
    const url = URL.createObjectURL(new Blob([text], { type }));
    const a = document.createElement("a");
    a.href = url;
    a.download = `research-${report.data_date}-${report.id}.${extension}`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  return (
    <div className="padded">
      <ErrorBox error={data.error ?? error} />
      <div className="inline">
        <button
          disabled={!data.data}
          onClick={() =>
            save(JSON.stringify(data.data, null, 2), "application/json", "json")
          }
        >
          Download JSON
        </button>
        <button
          onClick={async () => {
            try {
              save(await api.markdown(report.id), "text/markdown", "md");
            } catch (e) {
              setError(e);
            }
          }}
        >
          Download Markdown
        </button>
      </div>
      {data.data && (
        <>
          <p className="muted">
            {statusLabel(data.data.status)} · Data {data.data.data_date}
          </p>
          <Json value={data.data} />
        </>
      )}
    </div>
  );
}
export default function Home({
  api,
  reports,
  jobs,
  latest,
  onResearch,
  reportsReady = true,
}: {
  api: ApiClient;
  reports: Report[];
  jobs: Job[];
  latest?: string;
  onResearch: () => void;
  reportsReady?: boolean;
}) {
  const [selected, setSelected] = useState("");
  const [offset, setOffset] = useState(0);
  const next = useQuery({
    queryKey: ["report-page", offset],
    queryFn: () => api.reports(offset),
    enabled: offset > 0,
  });
  const shown = offset ? (next.data ?? []) : reports;
  const daily = reports.find((r) =>
    ["live", "historical_snapshot"].includes(r.mode),
  );
  const [scanTouched, setScanTouched] = useState(false);
  const [scanOpen, setScanOpen] = useState(
    new URLSearchParams(location.search).has("research"),
  );
  useEffect(() => {
    if (
      reportsReady &&
      !scanTouched &&
      !new URLSearchParams(location.search).has("research")
    )
      setScanOpen(!daily);
  }, [reportsReady, daily?.id, scanTouched]);
  const weekly = useAction(api, "/weekly-summaries");
  const active = jobs.filter((j) => !terminalStatuses.has(j.status));
  const candidateCount = daily?.quality.startsWith("blocked")
    ? "Unavailable"
    : typeof daily?.summary.candidate_count === "number"
      ? daily.summary.candidate_count
      : (daily?.summary.candidates?.length ?? "Unavailable");
  return (
    <div className="home-page">
      <section className="home-hero">
        <div className="hero-copy">
          <p className="eyebrow">
            <span /> A LITTLE CLARITY, FRESH DAILY
          </p>
          <h2>
            Good research.
            <br />
            <em>Slow simmer.</em>
          </h2>
          <p className="hero-description">
            A quieter place to make sense of the market.
            <br className="desktop-break" /> Steve does the prep. You do the
            thinking.
          </p>
          <button className="primary hero-cta" onClick={onResearch}>
            Explore your research <ArrowRight size={18} />
          </button>
          <p className="hero-footnote">Your own workspace. Your own pace.</p>
        </div>
        <KitchenScene
          working={active.some((j) =>
            ["scan", "weekly", "agent"].includes(j.kind),
          )}
          reportId={
            daily?.quality.startsWith("blocked") ? undefined : daily?.id
          }
        />
      </section>
      <section className="daily-serving" aria-label="Your daily serving">
        <div className="serving-intro">
          <UtensilsCrossed size={19} />
          <span>
            On today's menu
            <small>{latest ?? "Waiting for a market date"}</small>
          </span>
        </div>
        <Metric
          label="Latest daily report"
          value={daily?.data_date ?? "Not served yet"}
          note={
            daily
              ? `Scan outcome: ${statusLabel(daily.quality)}`
              : "Start with a fresh scan"
          }
        />
        <Metric
          label="Research candidates"
          value={candidateCount}
          note={
            daily?.quality.startsWith("blocked")
              ? "Scan blocked; inspect its diagnostics"
              : daily?.quality === "partial_coverage"
                ? "Passed screening among valid histories; coverage is incomplete"
                : "Stocks that passed every screening rule"
          }
        />
        <Metric
          label="Active jobs"
          value={active.length}
          note={
            active.length
              ? "Let him cook. Follow along in Activity."
              : "The kitchen is taking a breather"
          }
        />
      </section>
      <details className="scan-drawer" open={scanOpen}>
        <summary
          onClick={(event) => {
            event.preventDefault();
            setScanTouched(true);
            setScanOpen((open) => !open);
          }}
        >
          <span>Make a fresh serving</span>
          <small>Preview the dates, then start a scan</small>
        </summary>
        <ScanForm api={api} />
      </details>
      <details className="saved-servings">
        <summary>
          <span>Saved servings</span>
          <small>Your reports, with their original dates and coverage</small>
        </summary>
        <div className="reports-toolbar">
          <h2>Your research journal</h2>
          <button
            disabled={weekly.isPending || !daily}
            onClick={() =>
              weekly.mutate({ end_date: daily?.data_date, mode: daily?.mode })
            }
          >
            Queue weekly summary
          </button>
        </div>
        <ActionState action={weekly} />
        <ErrorBox error={next.error} />
        {shown.length ? (
          shown.map((r) => (
            <div key={r.id}>
              <button
                className="report-row"
                onClick={() => setSelected(selected === r.id ? "" : r.id)}
                aria-expanded={selected === r.id}
              >
                <div>
                  <strong>{r.data_date}</strong>
                  <small>
                    {statusLabel(r.mode)} ·{" "}
                    {r.summary.run_at_utc
                      ? dateTime(r.summary.run_at_utc)
                      : `Run ${r.id.slice(0, 8)}`}
                  </small>
                </div>
                <Badge>{r.quality}</Badge>
                <span>
                  Open <ArrowRight size={14} />
                </span>
              </button>
              {selected === r.id && <ReportView api={api} report={r} />}
            </div>
          ))
        ) : (
          <Empty>
            No servings yet. Preview a scan to see the dates it needs.
          </Empty>
        )}
        <div className="pagination">
          <button
            disabled={!offset}
            onClick={() => setOffset(Math.max(0, offset - 100))}
          >
            Previous
          </button>
          <span>Page {offset / 100 + 1}</span>
          <button
            disabled={shown.length !== 100}
            onClick={() => setOffset(offset + 100)}
          >
            Next
          </button>
        </div>
      </details>
    </div>
  );
}
