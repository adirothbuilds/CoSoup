import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiClient, Job, Report, terminalStatuses } from "@stock-scanner/client";
import {
  ActionState,
  Badge,
  Empty,
  ErrorBox,
  Json,
  Panel,
  useAction,
} from "../../components/UI";

function JobDetail({ api, job }: { api: ApiClient; job: Job }) {
  const qc = useQueryClient();
  const cancel = useAction(api, `/jobs/${job.id}/cancel`);
  const resume = useAction(api, `/jobs/${job.id}/resume`);
  const reports = useQuery({
    queryKey: ["job-reports", job.id, job.status, job.progress.report_ids],
    queryFn: () => api.request<Report[]>(`/reports?job_id=${encodeURIComponent(job.id)}`),
    enabled: job.kind === "scan" && job.error?.code === "scan_blocked",
  });
  const events = useQuery({
    queryKey: ["events", job.id],
    queryFn: () =>
      api.request<
        { id: number; at: string; level: string; code: string; data: unknown }[]
      >(`/jobs/${job.id}/events`),
    refetchInterval: terminalStatuses.has(job.status) ? false : 5000,
  });
  useEffect(() => {
    if (terminalStatuses.has(job.status)) return;
    const stream = new EventSource(`/api/v1/jobs/${job.id}/events/stream`);
    stream.onmessage = () => {
      qc.invalidateQueries({ queryKey: ["jobs"] });
      qc.invalidateQueries({ queryKey: ["events", job.id] });
    };
    stream.onerror = () => {
      stream.close();
    };
    return () => stream.close();
  }, [job.id, job.status, qc]);
  return (
    <Panel title={job.kind} aside={<Badge>{job.status}</Badge>}>
      <div className="padded">
        <p className="muted small">{job.id}</p>
        <ErrorBox
          error={
            job.error
              ? new Error(`${job.error.code}: ${job.error.message}`)
              : null
          }
        />
        {job.kind === "scan" && job.error?.code === "scan_blocked" && (
          <>
            <h3>Scan diagnostics</h3>
            <ErrorBox error={reports.error} />
            {reports.isPending && <p>Loading the scan report…</p>}
            {reports.data?.filter((report) => report.job_id === job.id && report.quality.startsWith("blocked")).map((report) => (
              <div key={report.id}>
                <p>{report.data_date} · <Badge>{report.quality}</Badge></p>
                <Json value={report.summary.errors} />
              </div>
            ))}
            {reports.data?.length === 0 && <p>No saved report was found for this scan.</p>}
          </>
        )}
        <Json value={job.progress} />
        <Json value={job.result} />
        <div className="inline">
          {!terminalStatuses.has(job.status) && (
            <button
              disabled={cancel.isPending || job.cancel_requested}
              onClick={() => cancel.mutate({})}
            >
              {job.cancel_requested
                ? "Cancellation requested"
                : "Cancel cooperatively"}
            </button>
          )}
          {["failed", "cancelled", "waiting_for_archive"].includes(
            job.status,
          ) && (
            <button
              disabled={resume.isPending}
              onClick={() => resume.mutate({})}
            >
              Resume after resolving cause
            </button>
          )}
        </div>
        <ActionState action={cancel} />
        <ActionState action={resume} />
        <h3>Persisted events</h3>
        <ErrorBox error={events.error} />
        {events.data?.map((e) => (
          <div className="event" key={e.id}>
            <small>
              {e.at} · {e.level}
            </small>
            <strong>{e.code}</strong>
            <Json value={e.data} />
          </div>
        ))}
        {events.data?.length === 500 && (
          <p className="muted">
            First 500 events. Use the API event cursor for later events.
          </p>
        )}
      </div>
    </Panel>
  );
}
export default function Activity({
  api,
  jobs,
}: {
  api: ApiClient;
  jobs: Job[];
}) {
  const [selected, setSelected] = useState("");
  const job = jobs.find((j) => j.id === selected) ?? jobs[0];
  const [offset, setOffset] = useState(0);
  const older = useQuery({
    queryKey: ["older-jobs", offset],
    queryFn: () => api.jobs(offset),
    enabled: offset > 0,
  });
  const shown = offset ? (older.data ?? []) : jobs;
  return (
    <div className="two-column">
      <Panel title="Activity">
        <ErrorBox error={older.error} />
        {shown.length ? (
          shown.map((j) => (
            <button
              key={j.id}
              className={`job-row ${j.id === job?.id ? "active" : ""}`}
              onClick={() => setSelected(j.id)}
            >
              <strong>{j.kind}</strong>
              <Badge>{j.status}</Badge>
              <small>{new Date(j.created_at).toLocaleString()}</small>
            </button>
          ))
        ) : (
          <Empty>No jobs yet.</Empty>
        )}
        <div className="pagination">
          <button
            disabled={!offset}
            onClick={() => setOffset(Math.max(0, offset - 100))}
          >
            Previous
          </button>
          <button
            disabled={shown.length !== 100}
            onClick={() => setOffset(offset + 100)}
          >
            Next
          </button>
        </div>
      </Panel>
      {(shown.find((j) => j.id === selected) ?? job) && (
        <JobDetail
          api={api}
          job={(shown.find((j) => j.id === selected) ?? job)!}
        />
      )}
    </div>
  );
}
