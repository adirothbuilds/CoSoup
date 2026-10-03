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
export function ErrorBox({ error }: { error: unknown }) {
  if (!error) return null;
  return (
    <div className="error" role="alert">
      <strong>
        {error instanceof ApiError ? error.code : "Request failed"}
      </strong>
      <span>{error instanceof Error ? error.message : String(error)}</span>
    </div>
  );
}
export function Empty({ children }: { children: ReactNode }) {
  return <div className="empty">{children}</div>;
}
export function Badge({ children }: { children: ReactNode }) {
  return <span className="badge">{children}</span>;
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
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <details className="disclosure">
      <summary>{title}</summary>
      <div className="detail-content">{children}</div>
    </details>
  );
}
