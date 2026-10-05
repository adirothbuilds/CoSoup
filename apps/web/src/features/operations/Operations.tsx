import { KitchenScene } from "../../components/Kitchen";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AgentRequest,
  ApiClient,
  ContextPacket,
  Portfolio,
  Report,
  Schedule,
  StorageStatus,
  SystemStatus,
} from "@stock-scanner/client";
import {
  ActionState,
  Badge,
  Disclosure,
  ErrorBox,
  Json,
  Metric,
  Panel,
  useAction,
} from "../../components/UI";

export function Analyst({
  api,
  portfolios,
  reports,
}: {
  api: ApiClient;
  portfolios: Portfolio[];
  reports: Report[];
}) {
  const status = useQuery({
    queryKey: ["status"],
    queryFn: () => api.status(),
  });
  const [prompt, setPrompt] = useState("");
  const [type, setType] = useState<AgentRequest["task_type"]>("daily_review");
  const [portfolio, setPortfolio] = useState("");
  const [report, setReport] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [allowPortfolio, setAllowPortfolio] = useState(false);
  const [allowImages, setAllowImages] = useState(false);
  const [images, setImages] = useState<string[]>([]);
  const [packet, setPacket] = useState<ContextPacket>();
  const [error, setError] = useState<unknown>();
  const [busy, setBusy] = useState(false);
  const run = useAction(api, "/agent/tasks");
  const jobs = useQuery({
    queryKey: ["jobs"],
    queryFn: () => api.jobs(),
    refetchInterval: 5000,
  });
  const taskId = run.data && "job_id" in run.data ? run.data.job_id : undefined;
  const task = jobs.data?.find((job) => job.id === taskId);
  const request: AgentRequest = {
    task_type: type,
    prompt: prompt || "Review the selected context",
    allow_portfolio_data: allowPortfolio,
    allow_uploaded_documents: allowImages,
    ...(portfolio ? { portfolio_id: portfolio } : {}),
    ...(report ? { report_ids: [report] } : {}),
    ...(start ? { start_date: start } : {}),
    ...(end ? { end_date: end } : {}),
    upload_ids: images,
  };
  async function upload(file: File) {
    setBusy(true);
    try {
      const data = new FormData();
      data.append("file", file);
      const result = await api.upload(data);
      setImages((old) => [...old, result.upload_id].slice(0, 4));
      setPacket(undefined);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Panel
      title="A second pair of eyes: Steve"
      aside={<Badge>{status.data?.capabilities.codex ?? "Unknown"}</Badge>}
    >
      <div className="padded">
        <div className="analyst-welcome">
          <div>
            <p className="eyebrow">LET HIM COOK. KEEP YOUR OWN JUDGMENT.</p>
            <p className="muted">
              Steve helps you ask better questions. He doesn't make your
              decisions.
            </p>
          </div>
          <div className="analyst-kitchen">
            <KitchenScene
              working={!!task && ["queued", "running"].includes(task.status)}
            />
          </div>
        </div>
        <p className="muted">
          Ask a question in natural language using dated reports, signal
          observations and explicitly authorized personal evidence.
        </p>
        <label className="full">
          Your question
          <textarea
            rows={4}
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder="Which candidates deserve a closer look, and what information is missing?"
          />
        </label>
        {status.data &&
          status.data.capabilities.codex !== "operator_verified" && (
            <p className="muted small">
              Steve's analysis isn't connected yet. You can still preview the
              research sources below.
            </p>
          )}
        <Disclosure title="Sources, dates & permissions">
          <div className="form-grid">
            <label>
              Task
              <select
                value={type}
                onChange={(e) =>
                  setType(e.target.value as AgentRequest["task_type"])
                }
              >
                {[
                  "daily_review",
                  "weekly_review",
                  "portfolio_review",
                  "document_review",
                ].map((t) => (
                  <option key={t} value={t}>
                    {t.replaceAll("_", " ")}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Report
              <select
                value={report}
                onChange={(e) => setReport(e.target.value)}
              >
                <option value="">Dated reports in range</option>
                {reports.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.data_date} · {r.mode}
                  </option>
                ))}
              </select>
            </label>
            <label>
              From (optional)
              <input
                type="date"
                value={start}
                onChange={(e) => setStart(e.target.value)}
              />
            </label>
            <label>
              Through (optional)
              <input
                type="date"
                value={end}
                onChange={(e) => setEnd(e.target.value)}
              />
            </label>
            <label>
              Portfolio (optional)
              <select
                value={portfolio}
                onChange={(e) => setPortfolio(e.target.value)}
              >
                <option value="">No portfolio</option>
                {portfolios.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="check">
              <input
                type="checkbox"
                checked={allowPortfolio}
                onChange={(e) => setAllowPortfolio(e.target.checked)}
              />
              Authorize selected portfolio/report export to the model service
            </label>
            <label>
              Attach image for vision
              <input
                type="file"
                accept="image/png,image/jpeg"
                disabled={busy || images.length >= 4}
                onChange={(e) => {
                  if (e.target.files?.[0]) void upload(e.target.files[0]);
                }}
              />
            </label>
            <label className="check">
              <input
                type="checkbox"
                checked={allowImages}
                onChange={(e) => setAllowImages(e.target.checked)}
              />
              Authorize attached images to be sent to the model service
            </label>
          </div>
        </Disclosure>
        {images.length > 0 && (
          <p>
            {images.length} image(s) attached{" "}
            <button onClick={() => setImages([])}>Clear attachments</button>
          </p>
        )}
        <div className="inline">
          <button
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              setError(null);
              try {
                setPacket(await api.context(request));
              } catch (e) {
                setError(e);
              } finally {
                setBusy(false);
              }
            }}
          >
            Preview structured context
          </button>
          <button
            className="primary"
            disabled={
              run.isPending ||
              busy ||
              !prompt.trim() ||
              status.data?.capabilities.codex !== "operator_verified" ||
              (!!portfolio && !allowPortfolio) ||
              (images.length > 0 && !allowImages)
            }
            onClick={() => run.mutate(request)}
          >
            Queue analysis
          </button>
        </div>
        <ErrorBox error={error ?? status.error} />
        <ActionState action={run} />
        {packet && (
          <Disclosure
            title={`Agent context v${packet.schema_version} · ${packet.source_ids.length} authorized sources`}
          >
            <Json value={packet} />
          </Disclosure>
        )}
        <p className="muted small">
          Vision supports JPEG/PNG. PDF/CSV use the reviewed import workflow.
          Model output does not change your journal. Operator verification is a
          readiness prerequisite, not proof of a successful model call.
        </p>
      </div>
    </Panel>
  );
}
function ScheduleRow({ api, row }: { api: ApiClient; row: Schedule }) {
  const toggle = useAction(api, `/schedules/${row.id}`, "PATCH");
  const run = useAction(api, `/schedules/${row.id}/run-now`);
  const occurrences = useQuery({
    queryKey: ["occurrences", row.id],
    queryFn: () => api.request(`/schedules/${row.id}/occurrences`),
  });
  return (
    <Disclosure
      title={`${row.name} · ${row.enabled ? "Enabled" : "Disabled"} · Next ${row.next_at ?? "none"}`}
    >
      <Json
        value={{
          trigger: row.trigger,
          task: row.task,
          missed_policy: row.missed_policy,
        }}
      />
      <div className="inline">
        <button
          disabled={toggle.isPending}
          onClick={() => toggle.mutate({ enabled: !row.enabled })}
        >
          {row.enabled ? "Disable" : "Enable"}
        </button>
        <button disabled={run.isPending} onClick={() => run.mutate({})}>
          Run now
        </button>
      </div>
      <ActionState action={toggle} />
      <ActionState action={run} />
      <ErrorBox error={occurrences.error} />
      <Json value={occurrences.data} />
    </Disclosure>
  );
}
function Schedules({ api, status }: { api: ApiClient; status?: SystemStatus }) {
  const list = useQuery({
    queryKey: ["schedules"],
    queryFn: () => api.request<Schedule[]>("/schedules"),
  });
  const action = useAction(api, "/schedules");
  const [kind, setKind] = useState("market_close");
  const [frequency, setFrequency] = useState("daily");
  return (
    <Panel title="Schedules">
      <div className="padded">
        <p className="muted">
          Host clock · Server timezone {status?.server_timezone ?? "unknown"}.
          Market triggers include holidays and early closes.
        </p>
        <form
          className="form-grid"
          onSubmit={(e) => {
            e.preventDefault();
            const f = new FormData(e.currentTarget);
            const trigger =
              kind === "market_close"
                ? { type: kind, frequency }
                : kind === "local_cron"
                  ? {
                      type: kind,
                      expression: f.get("cron"),
                      timezone: f.get("timezone"),
                    }
                  : {
                      type: kind,
                      at: new Date(String(f.get("at"))).toISOString(),
                    };
            action.mutate({
              name: f.get("name"),
              trigger,
              task: { type: f.get("task") },
              enabled: f.get("enabled") === "on",
              missed_run_policy: f.get("missed"),
            });
          }}
        >
          <label>
            Name
            <input name="name" required />
          </label>
          <label>
            Trigger
            <select value={kind} onChange={(e) => setKind(e.target.value)}>
              <option value="market_close">Market close</option>
              <option value="local_cron">Local cron</option>
              <option value="once">Once</option>
            </select>
          </label>
          {kind === "market_close" ? (
            <label>
              Frequency
              <select
                value={frequency}
                onChange={(e) => setFrequency(e.target.value)}
              >
                <option>daily</option>
                <option>weekly</option>
              </select>
            </label>
          ) : kind === "local_cron" ? (
            <>
              <label>
                Cron expression
                <input name="cron" defaultValue="30 23 * * 1-5" required />
              </label>
              <label>
                IANA timezone
                <input
                  name="timezone"
                  defaultValue={status?.server_timezone ?? "UTC"}
                  required
                />
              </label>
            </>
          ) : (
            <label>
              Device-local time
              <input name="at" type="datetime-local" required />
            </label>
          )}
          <label>
            Task
            <select name="task">
              <option value="daily_scan">Daily scan</option>
              <option value="weekly_summary">Weekly summary</option>
              <option value="archive_completed_months">Archive batch</option>
              <option value="database_backup">Database backup</option>
            </select>
          </label>
          <label>
            Missed runs
            <select name="missed">
              <option>run_once</option>
              <option>skip</option>
              <option>catch_up</option>
            </select>
          </label>
          <label className="check">
            <input name="enabled" type="checkbox" />
            Enable immediately
          </label>
          <div className="full">
            <button disabled={action.isPending}>Create schedule</button>
            <ActionState action={action} />
          </div>
        </form>
        <ErrorBox error={list.error} />
        {list.data?.map((r) => (
          <ScheduleRow key={r.id} api={api} row={r} />
        ))}
      </div>
    </Panel>
  );
}
function Storage({ api }: { api: ApiClient }) {
  const data = useQuery({
    queryKey: ["storage"],
    queryFn: () => api.request<StorageStatus>("/storage/status"),
  });
  const archives = useQuery({
    queryKey: ["archives"],
    queryFn: () => api.request("/storage/archives"),
  });
  const archive = useAction(api, "/storage/archive-jobs");
  const restore = useAction(api, "/storage/restore-jobs");
  const policy = useAction(api, "/storage/policy", "PATCH");
  const [ids, setIds] = useState("");
  return (
    <Panel title="Storage & retention">
      <div className="padded">
        <ErrorBox error={data.error} />
        <div className="metrics">
          <Metric
            label="Used"
            value={`${((data.data?.used_bytes ?? 0) / 1e9).toFixed(2)} GB`}
          />
          <Metric
            label="Reserved"
            value={`${((data.data?.reserved_bytes ?? 0) / 1e9).toFixed(2)} GB`}
          />
          <Metric
            label="Capacity"
            value={
              data.data?.policy
                ? `${(data.data.policy.capacity_bytes / 1e9).toFixed(0)} GB`
                : "Unavailable"
            }
          />
        </div>
        <Disclosure title="Configure retention policy">
          {data.data?.policy && (
            <form
              className="form-grid"
              onSubmit={(e) => {
                e.preventDefault();
                const f = new FormData(e.currentTarget);
                const limits = Object.fromEntries(
                  [
                    "capacity_bytes",
                    "target_bytes",
                    "archive_trigger_bytes",
                    "admission_stop_bytes",
                    "hot_sessions",
                    "restore_ttl_days",
                  ].map((k) => [k, Number(f.get(k))]),
                );
                policy.mutate({
                  limits,
                  archive_after_days: Number(f.get("archive_after_days")),
                  archive_evict: f.get("evict") === "on",
                });
              }}
            >
              {[
                "capacity_bytes",
                "target_bytes",
                "archive_trigger_bytes",
                "admission_stop_bytes",
                "hot_sessions",
                "restore_ttl_days",
              ].map((k) => (
                <label key={k}>
                  {k.replaceAll("_", " ")}
                  <input
                    type="number"
                    min="1"
                    step="1"
                    name={k}
                    defaultValue={data.data!.policy![k]}
                    required
                  />
                </label>
              ))}
              <label>
                Archive after days
                <input
                  type="number"
                  min="1"
                  name="archive_after_days"
                  defaultValue={data.data.archive_after_days}
                />
              </label>
              <label className="check">
                <input
                  type="checkbox"
                  name="evict"
                  defaultChecked={data.data.archive_evict}
                />
                Allow verified local eviction
              </label>
              <div className="full">
                <button disabled={policy.isPending}>Save policy</button>
                <ActionState action={policy} />
              </div>
            </form>
          )}
          <p className="muted">
            A hard ceiling requires a host filesystem quota. R2 credentials and
            host settings are provisioned privately.
          </p>
        </Disclosure>
        <div className="inline">
          <button
            disabled={archive.isPending}
            onClick={() => archive.mutate({})}
          >
            Queue archive batch
          </button>
        </div>
        <ActionState action={archive} />
        <label>
          Restore artifact IDs (comma-separated)
          <textarea
            value={ids}
            onChange={(e) => setIds(e.target.value)}
            rows={2}
          />
        </label>
        <button
          disabled={restore.isPending || !ids.trim()}
          onClick={() =>
            restore.mutate({
              artifact_ids: ids
                .split(",")
                .map((s) => s.trim())
                .filter(Boolean),
            })
          }
        >
          Queue bounded restore
        </button>
        <ActionState action={restore} />
        <Disclosure title="Archive inventory">
          <ErrorBox error={archives.error} />
          <Json value={archives.data} />
        </Disclosure>
      </div>
    </Panel>
  );
}
export default function Operations({
  api,
  portfolios,
  reports,
}: {
  api: ApiClient;
  portfolios: Portfolio[];
  reports: Report[];
}) {
  const status = useQuery({
    queryKey: ["status"],
    queryFn: () => api.status(),
  });
  const rules = useQuery({
    queryKey: ["rules"],
    queryFn: () => api.request("/rules"),
  });
  const rule = useAction(api, "/rules");
  const preferences = useAction(api, "/me", "PATCH");
  const [rulesText, setRulesText] = useState("{}");
  const [error, setError] = useState<unknown>();
  return (
    <>
      <Analyst api={api} portfolios={portfolios} reports={reports} />
      <Disclosure title="Kitchen settings: schedules & storage">
        <Schedules api={api} status={status.data} />
        <Storage api={api} />
      </Disclosure>
      <Panel title="Preferences & rule versions">
        <div className="padded">
          <form
            className="inline"
            onSubmit={(e) => {
              e.preventDefault();
              preferences.mutate({
                display_timezone: new FormData(e.currentTarget).get("timezone"),
              });
            }}
          >
            <label>
              Display timezone
              <input name="timezone" placeholder="Asia/Jerusalem" required />
            </label>
            <button disabled={preferences.isPending}>Save preference</button>
          </form>
          <ActionState action={preferences} />
          <Disclosure title="Create immutable screening rules">
            <Json value={rules.data} />
            <label>
              Threshold overrides (JSON)
              <textarea
                rows={5}
                value={rulesText}
                onChange={(e) => setRulesText(e.target.value)}
              />
            </label>
            <button
              disabled={rule.isPending}
              onClick={() => {
                try {
                  rule.mutate(JSON.parse(rulesText));
                } catch (e) {
                  setError(e);
                }
              }}
            >
              Create rule version
            </button>
            <ErrorBox error={error ?? rules.error} />
            <ActionState action={rule} />
          </Disclosure>
          <Disclosure title="Deployment capabilities">
            <ErrorBox error={status.error} />
            <Json value={status.data} />
          </Disclosure>
        </div>
      </Panel>
    </>
  );
}
