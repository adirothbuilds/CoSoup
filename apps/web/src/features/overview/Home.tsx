import { KitchenScene } from "../../components/Kitchen";
import { ArrowRight, Plus, UtensilsCrossed } from "lucide-react";
import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  ApiClient,
  Job,
  Report,
  ScanPlan,
  ScanRequest,
  terminalStatuses,
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
  const [mode, setMode] = useState<ScanRequest["mode"]>("live");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [offline, setOffline] = useState(true);
  const [research, setResearch] = useState<ScanRequest["research"]>("none");
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
            value={mode}
            onChange={(e) => {
              setMode(e.target.value as ScanRequest["mode"]);
              setResearch("none");
            }}
          >
            <option value="live">Latest completed session</option>
            <option value="historical_snapshot">Historical snapshots</option>
          </select>
        </label>
        <label>
          Company research
          <select
            value={research}
            onChange={(e) =>
              setResearch(e.target.value as ScanRequest["research"])
            }
          >
            <option value="none">None</option>
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
            checked={offline}
            onChange={(e) => setOffline(e.target.checked)}
          />
          Offline: require existing dated cache
        </label>
      </div>
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
              const r = await fetch(
                `/api/v1/reports/${report.id}/content?format=markdown`,
                { credentials: "include" },
              );
              if (!r.ok)
                throw new Error(`Report download failed (${r.status})`);
              save(await r.text(), "text/markdown", "md");
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
            {data.data.status} · Data {data.data.data_date}
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
}: {
  api: ApiClient;
  reports: Report[];
  jobs: Job[];
  latest?: string;
  onResearch: () => void;
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
          note={daily ? statusLabel(daily.quality) : "Start with a fresh scan"}
        />
        <Metric
          label="Research candidates"
          value={candidateCount}
          note={
            daily?.quality.startsWith("blocked")
              ? "Scan blocked; inspect its diagnostics"
              : daily?.quality === "partial_coverage"
                ? "Results with coverage gaps"
                : "Screening results, as they are"
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
      <details className="scan-drawer" open={!daily}>
        <summary>
          <span>
            <Plus size={18} /> Make a fresh serving
          </span>
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
                    {r.mode === "live"
                      ? "Daily research"
                      : r.mode === "historical_snapshot"
                        ? "Historical research"
                        : "Weekly review"}
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
