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
  Panel,
  useAction,
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
  return (
    <>
      <div className="overview-intro">
        <div>
          <p className="eyebrow">YOUR RESEARCH WORKSPACE</p>
          <h2>A clear view of the market.</h2>
          <p className="muted">
            Completed session {latest ?? "unavailable"} · Your reports preserve
            their own dates and coverage.
          </p>
        </div>
        <button className="primary" onClick={onResearch}>
          Open market workspace →
        </button>
      </div>
      <div className="summary-cards">
        <Panel>
          <Metric
            label="Latest daily report"
            value={daily?.data_date ?? "No report"}
            note={daily?.quality}
          />
        </Panel>
        <Panel>
          <Metric
            label="Research candidates"
            value={typeof daily?.summary.candidate_count === 'number' ? daily.summary.candidate_count : daily?.summary.candidates?.length ?? "Unavailable"}
            note="Actual screening results"
          />
        </Panel>
        <Panel>
          <Metric
            label="Active jobs"
            value={jobs.filter((j) => !terminalStatuses.has(j.status)).length}
            note="Durable server work"
          />
        </Panel>
      </div>
      <Panel title="Run a scan">
        <ScanForm api={api} />
      </Panel>
      <Panel
        title="Reports"
        aside={
          <button
            disabled={weekly.isPending || !daily}
            onClick={() =>
              weekly.mutate({ end_date: daily?.data_date, mode: daily?.mode })
            }
          >
            Queue weekly summary
          </button>
        }
      >
        <div className="padded">
          <ActionState action={weekly} />
          <ErrorBox error={next.error} />
        </div>
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
                  <small>{r.mode}</small>
                </div>
                <Badge>{r.quality}</Badge>
                <span>Open ›</span>
              </button>
              {selected === r.id && <ReportView api={api} report={r} />}
            </div>
          ))
        ) : (
          <Empty>
            No reports yet. Preview a scan to see the required data.
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
      </Panel>
    </>
  );
}
