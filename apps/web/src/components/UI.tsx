import { ReactNode, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ApiClient, ApiError, Submitted } from "@stock-scanner/client";

export function Panel({
  title,
  aside,
  children,
  className = "",
}: {
  title?: string;
  aside?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`panel ${className}`}>
      {title && (
        <header className="panel-head">
          <h2>{title}</h2>
          {aside}
        </header>
      )}
      {children}
    </section>
  );
}
export function ErrorBox({
  error,
  onRetry,
}: {
  error: unknown;
  onRetry?: () => void;
}) {
  if (!error) return null;
  return (
    <div className="error" role="alert">
      <strong>
        {error instanceof ApiError ? error.code : "Request failed"}
      </strong>
      <span>{error instanceof Error ? error.message : String(error)}</span>
      {onRetry && <button onClick={onRetry}>Try again</button>}
    </div>
  );
}
export function Empty({ children }: { children: ReactNode }) {
  return <div className="empty">{children}</div>;
}
export function statusLabel(status: string) {
  return (
    (
      {
        complete: "Ready",
        partial_coverage: "Coverage gaps",
        blocked_error: "Needs attention",
        blocked_quality: "Data needs attention",
        blocked_provider: "Provider needs attention",
        blocked_benchmarks: "Benchmark data missing",
        succeeded: "Served",
        failed: "Needs attention",
        running: "Cooking",
        queued: "On the stove",
        cancelled: "Stopped",
        waiting_for_archive: "Waiting for data",
        disabled: "Not connected",
        ready: "Ready",
        live: "Daily research",
        historical_snapshot: "Historical research",
        weekly: "Weekly summary",
        weekly_live: "Weekly summary",
        weekly_historical_snapshot: "Historical weekly summary",
        scan: "Market scan",
        agent: "Steve's analysis",
        sec_sync: "SEC research sync",
        sec_research: "Company filings & holdings",
      } as Record<string, string>
    )[status] ?? status
  );
}
export function Badge({ children }: { children: ReactNode }) {
  const raw = typeof children === "string" ? children : undefined;
  return (
    <span className="badge" data-status={raw} title={raw}>
      {raw ? statusLabel(raw) : children}
    </span>
  );
}
export function Json({ value }: { value: unknown }) {
  return <pre className="json">{JSON.stringify(value, null, 2)}</pre>;
}
export function Toggle<T extends string>({
  values,
  value,
  onChange,
  label,
}: {
  values: readonly T[];
  value: T;
  onChange: (v: T) => void;
  label: string;
}) {
  return (
    <div className="segmented" role="group" aria-label={label}>
      {values.map((v) => (
        <button
          key={v}
          type="button"
          aria-pressed={v === value}
          className={v === value ? "selected" : ""}
          onClick={() => onChange(v)}
        >
          {v}
        </button>
      ))}
    </div>
  );
}
export function Metric({
  label,
  value,
  note,
}: {
  label: string;
  value: ReactNode;
  note?: string;
}) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{value}</strong>
      {note && <small>{note}</small>}
    </div>
  );
}
export function useAction(api: ApiClient, path: string, method = "POST") {
  const qc = useQueryClient();
  const [done, setDone] = useState<string>();
  // Preserve one intentional request's key across a manual retry of unchanged input.
  const [intent] = useState(() => new Map<string, string>());
  const mutation = useMutation({
    mutationFn: async (body: unknown) => {
      const signature = JSON.stringify(body);
      let key = intent.get(signature);
      if (!key) {
        key = crypto.randomUUID();
        intent.set(signature, key);
      }
      const result = await api.request<
        Submitted | { id?: string; status?: string }
      >(path, method, body, key);
      intent.delete(signature);
      return result;
    },
    onSuccess: (result) => {
      setDone("job_id" in result ? `Job queued: ${result.job_id}` : "Saved");
      qc.invalidateQueries();
    },
  });
  return { ...mutation, done };
}
export function ActionState({
  action,
}: {
  action: { error: unknown; done?: string; isPending: boolean };
}) {
  return (
    <>
      <ErrorBox error={action.error} />
      {action.done && (
        <p className="success" role="status">
          {action.done}
        </p>
      )}
    </>
  );
}
export function Disclosure({
  title,
  children,
  open,
}: {
  title: string;
  children: ReactNode;
  open?: boolean;
}) {
  return (
    <details className="disclosure" open={open}>
      <summary>{title}</summary>
      <div className="detail-content">{children}</div>
    </details>
  );
}
