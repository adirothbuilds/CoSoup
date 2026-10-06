import { z } from "zod";

export const periodSchema = z.enum(["1D", "1W", "1M"]);
export type Period = z.infer<typeof periodSchema>;
export type Scope = "portfolio" | "candidates" | "near_breakouts";
export interface Candidate {
  symbol: string;
  name?: string;
  close: number;
  pivot: number;
  volume_ratio: number;
  rs_excess: number;
  pivot_extension: number;
  failed_filters?: string[];
}
export interface Research {
  facts?: {
    statement?: string;
    text?: string;
    source?: string;
    [key: string]: unknown;
  }[];
  hypotheses?: string[];
  missing?: string[];
  checked_at?: string;
}
export interface DailyReport {
  status: string;
  data_date: string;
  candidates?: Candidate[];
  near_breakouts?: Candidate[];
  research?: Record<string, Research>;
  coverage?: Record<string, unknown>;
  filter_counts?: Record<string, number>;
  errors?: unknown[];
  warnings?: string[];
  run_at_utc?: string;
  research_run?: {
    requested: boolean;
    status: string;
    checked_symbols: string[];
    limit: number;
    unchecked_candidates?: number;
  };
  rules?: { rs_days?: number };
  [key: string]: unknown;
}
export interface Report {
  id: string;
  job_id: string;
  data_date: string;
  mode: string;
  quality: string;
  artifact_id: string;
  markdown_id: string;
  summary: DailyReport;
}
export interface Portfolio {
  id: string;
  name: string;
  currency: string;
}
export interface Position {
  symbol: string;
  quantity: string;
  cost_basis: string | null;
  basis_known: boolean;
}
export interface Ledger {
  portfolio_id: string;
  currency: string;
  cash: string;
  cash_note: string;
  positions: Position[];
  realized_pnl: string | null;
  accounting: string;
}
export interface Job {
  id: string;
  kind: string;
  status: string;
  created_at: string;
  progress: Record<string, unknown>;
  result: Record<string, unknown>;
  error: { code?: string; message?: string } | null;
  cancel_requested: boolean;
}
export interface Submitted {
  job_id: string;
  status: string;
  import_id?: string;
}
export interface Session {
  owner_id: string;
  csrf_token: string;
  expires_at: string;
}
export interface Schedule {
  id: string;
  name: string;
  enabled: boolean;
  next_at: string | null;
  trigger: Record<string, unknown>;
  task: Record<string, unknown>;
  missed_policy: string;
}
export interface Transaction {
  id?: string;
  type:
    | "buy"
    | "sell"
    | "opening"
    | "deposit"
    | "withdrawal"
    | "dividend"
    | "fee"
    | "split";
  at: string;
  symbol?: string | null;
  quantity?: string | null;
  price?: string | null;
  amount?: string | null;
  fees: string;
  currency: "USD";
  external_ref?: string | null;
  superseded?: boolean;
}
export interface ImportReview {
  id: string;
  portfolio_id: string;
  status: string;
  proposal: { source_text?: string; rows?: unknown[]; [key: string]: unknown };
  confirmed_ids: string[];
}
export interface SystemStatus {
  server_timezone: string;
  capabilities: {
    codex: string;
    archive: string;
    mail: string;
    browser_sessions: boolean;
  };
  storage: StorageStatus;
}
export interface StorageStatus {
  used_bytes: number;
  reserved_bytes: number;
  filesystem_free_bytes: number;
  policy?: Record<string, number>;
  archive_after_days?: number;
  archive_evict?: boolean;
  [key: string]: unknown;
}
export interface AgentRequest {
  profile_id?: "research-analyst";
  task_type:
    "daily_review" | "weekly_review" | "portfolio_review" | "document_review";
  prompt: string;
  start_date?: string;
  end_date?: string;
  report_ids?: string[];
  portfolio_id?: string;
  allow_portfolio_data: boolean;
  upload_ids?: string[];
  allow_uploaded_documents: boolean;
}
export interface ContextPacket {
  schema_version: number;
  kind: string;
  start_date: string;
  end_date: string;
  source_ids: string[];
  reports: unknown[];
  portfolio: Ledger | null;
  images: unknown[];
  semantics: Record<string, string>;
}

const metricSchema = z.object({
  symbol: z.string(),
  name: z.string().nullable().optional(),
  change_percent: z.number().nullable(),
  close: z.number().nullable(),
  quality: z.string(),
  metrics: z.unknown().optional(),
});
export const movementSchema = z.object({
  data_date: z.string(),
  start_date: z.string(),
  period: periodSchema,
  basis: z.literal("split_adjusted"),
  items: z.array(metricSchema),
  total_symbols: z.number(),
  displayed_symbols: z.number(),
  quality: z.string(),
  restore_artifact_ids: z.array(z.string()),
});
export type Movement = z.infer<typeof movementSchema>;
export type MovementItem = Movement["items"][number];
const indicatorSchema = z.object({ session: z.string(), value: z.number() });
export const barsSchema = z.object({
  symbol: z.string(),
  data_date: z.string(),
  basis: z.literal("split_adjusted"),
  adjustment_cutoff: z.string(),
  bars: z.array(
    z.object({
      session: z.string(),
      open: z.number(),
      high: z.number(),
      low: z.number(),
      close: z.number(),
      volume: z.number(),
    }),
  ),
  missing_sessions: z.array(
    z.object({ session: z.string(), reason: z.string() }),
  ),
  indicators: z.object({
    sma50: z.array(indicatorSchema),
    sma200: z.array(indicatorSchema),
    breakout55: z.array(indicatorSchema),
  }),
  quality: z.string(),
  restore_artifact_ids: z.array(z.string()),
  note: z.string(),
});
export type Bars = z.infer<typeof barsSchema>;
export type ScanRequest = {
  mode: "live" | "historical_snapshot";
  start_date?: string;
  end_date?: string;
  research: "none" | "current" | "as_of_only";
  offline: boolean;
  rules_id?: string;
};
export interface ScanPlan {
  sessions: string[];
  required_sessions: string[];
  missing_sessions: string[];
  cold_sessions: { session: string; artifact_id: string }[];
  warmup_start: string;
  estimated_minimum_grouped_requests: number;
  [key: string]: unknown;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}
type Options = {
  baseUrl?: string;
  credential?: () => Promise<string | null>;
  fetcher?: typeof fetch;
  onUnauthorized?: () => void;
  requestTimeoutMs?: number;
};
export class ApiClient {
  private csrf: string | null = null;
  constructor(private options: Options = {}) {}
  private async bounded<T>(
    task: (signal: AbortSignal) => Promise<T>,
    milliseconds = this.options.requestTimeoutMs ?? 30000,
  ): Promise<T> {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    const timeout = new Promise<never>((_, reject) => {
      timer = setTimeout(() => {
        reject(
          new ApiError(
            0,
            "request_timeout",
            "The server request timed out. Jobs may continue on the server; check Activity before resubmitting.",
          ),
        );
        controller.abort();
      }, milliseconds);
    });
    try {
      return await Promise.race([task(controller.signal), timeout]);
    } finally {
      clearTimeout(timer!);
    }
  }
  async request<T>(
    path: string,
    method = "GET",
    body?: unknown,
    key?: string,
    responseType: "json" | "text" = "json",
  ): Promise<T> {
    return this.bounded(
      async (signal) => {
        const headers: Record<string, string> = {};
        const token = await this.options.credential?.();
        if (token) headers.Authorization = `Bearer ${token}`;
        if (this.csrf) headers["X-Scanner-CSRF"] = this.csrf;
        if (key) headers["Idempotency-Key"] = key;
        const multipart =
          typeof FormData !== "undefined" && body instanceof FormData;
        if (body !== undefined && !multipart)
          headers["Content-Type"] = "application/json";
        const response = await (this.options.fetcher ?? fetch)(
          `${this.options.baseUrl ?? ""}/api/v1${path}`,
          {
            method,
            signal,
            headers,
            credentials: this.options.credential ? "omit" : "include",
            body:
              body === undefined
                ? undefined
                : multipart
                  ? (body as FormData)
                  : JSON.stringify(body),
          },
        );
        if (!response.ok) {
          let error: {
            error?: { code?: string; message?: string };
            detail?: unknown;
          } = {};
          try {
            error = await response.json();
          } catch {
            /* A proxy may return a non-JSON failure. */
          }
          if (response.status === 401) this.options.onUnauthorized?.();
          throw new ApiError(
            response.status,
            error.error?.code ?? `http_${response.status}`,
            error.error?.message ??
              (typeof error.detail === "string"
                ? error.detail
                : `Request failed (${response.status})`),
          );
        }
        const value =
          responseType === "text"
            ? await response.text()
            : await response.json();
        if (signal.aborted)
          throw new ApiError(
            0,
            "request_timeout",
            "The server request timed out.",
          );
        return value as T;
      },
      typeof FormData !== "undefined" && body instanceof FormData
        ? (this.options.requestTimeoutMs ?? 120000)
        : undefined,
    );
  }
  async connect(token: string): Promise<Session> {
    return this.bounded(async (signal) => {
      const response = await (this.options.fetcher ?? fetch)(
        `${this.options.baseUrl ?? ""}/api/v1/auth/session`,
        {
          method: "POST",
          signal,
          credentials: "include",
          headers: { Authorization: `Bearer ${token}` },
        },
      );
      if (!response.ok) {
        const body = await response.json();
        throw new ApiError(
          response.status,
          body.error?.code ?? "connect_failed",
          body.error?.message ?? "Could not connect",
        );
      }
      const session = (await response.json()) as Session;
      if (signal.aborted)
        throw new ApiError(
          0,
          "request_timeout",
          "The server request timed out.",
        );
      this.csrf = session.csrf_token;
      return session;
    }, this.options.requestTimeoutMs ?? 15000);
  }
  async session(): Promise<Session> {
    const s = await this.request<Session>("/auth/session");
    this.csrf = s.csrf_token;
    return s;
  }
  async disconnect() {
    await this.request("/auth/session", "DELETE");
    this.csrf = null;
  }
  reports(offset = 0) {
    return this.request<Report[]>(`/reports?limit=100&offset=${offset}`);
  }
  report(id: string) {
    return this.request<DailyReport>(
      `/reports/${encodeURIComponent(id)}/content`,
    );
  }
  markdown(id: string) {
    return this.request<string>(
      `/reports/${encodeURIComponent(id)}/content?format=markdown`,
      "GET",
      undefined,
      undefined,
      "text",
    );
  }
  portfolios() {
    return this.request<Portfolio[]>("/portfolios");
  }
  positions(id: string) {
    return this.request<Ledger>(
      `/portfolios/${encodeURIComponent(id)}/positions`,
    );
  }
  jobs(offset = 0) {
    return this.request<Job[]>(`/jobs?limit=100&offset=${offset}`);
  }
  movement(input: {
    scope: Scope;
    report_id?: string;
    portfolio_id?: string;
    data_date?: string;
    period: Period;
  }) {
    return this.request<unknown>(
      "/market/movement-snapshots",
      "POST",
      input,
    ).then((x) => movementSchema.parse(x));
  }
  bars(symbol: string, end?: string) {
    return this.request<unknown>(
      `/market/tickers/${encodeURIComponent(symbol)}/bars${end ? `?end_date=${encodeURIComponent(end)}` : ""}`,
    ).then((x) => barsSchema.parse(x));
  }
  status() {
    return this.request<SystemStatus>("/system/status");
  }
  context(input: AgentRequest) {
    return this.request<ContextPacket>("/agent/context", "POST", input);
  }
  upload(data: FormData) {
    return this.request<{ upload_id: string }>("/uploads", "POST", data);
  }
}

export const pct = (value: number | null | undefined, digits = 1) =>
  value == null
    ? "Unavailable"
    : `${value > 0 ? "+" : ""}${value.toFixed(digits)}%`;
export const money = (value: number | string | null | undefined) =>
  value == null
    ? "Unavailable"
    : `$${Number(value).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
export const metricDefinitions = {
  movement:
    "Close-to-close price change over the selected trading-session period; split-adjusted, excludes dividends.",
  relativeStrength:
    "Excess price change versus SPY over the screening window, measured in percentage points.",
};
export const terminalStatuses = new Set([
  "succeeded",
  "failed",
  "cancelled",
  "waiting_for_archive",
]);
export function usableDailyReport(
  reports: Report[],
  explicitId?: string | null,
) {
  const daily = reports.filter((r) =>
    ["live", "historical_snapshot"].includes(r.mode),
  );
  return (
    daily.find((r) => r.id === explicitId) ??
    daily.find((r) => !r.quality.startsWith("blocked")) ??
    daily[0]
  );
}
export function researchState(report: DailyReport) {
  if (report.research_run) return report.research_run.status;
  if (Object.keys(report.research ?? {}).length) return "legacy_available";
  if (report.status.startsWith("blocked")) return "blocked";
  if (report.warnings?.some((w) => w.includes("research was not run")))
    return "not_run";
  return "unknown";
}
// UI timestamps use ISO dates and UTC throughout; journal entry inputs still use device time.
export function dateTime(value: string | undefined | null) {
  if (!value) return "Time unavailable";
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? "Time unavailable"
    : `${date.toISOString().slice(0, 19).replace("T", " ")} UTC`;
}
export const shares = (value: number) =>
  value.toLocaleString("en-US", { maximumFractionDigits: 0 });
export function rangeBars(bars: Bars["bars"], range: "1M" | "3M" | "1Y") {
  return bars.slice(-{ "1M": 21, "3M": 63, "1Y": 252 }[range]);
}
export function chartWindow(data: Bars, range: "1M" | "3M" | "1Y") {
  const sessions = [
    ...new Set([
      ...data.bars.map((b) => b.session),
      ...data.missing_sessions.map((b) => b.session),
    ]),
  ]
    .sort()
    .slice(-{ "1M": 21, "3M": 63, "1Y": 252 }[range]);
  const included = new Set(sessions);
  return { sessions, bars: data.bars.filter((b) => included.has(b.session)) };
}
export function safeSource(value: unknown): string | null {
  if (typeof value !== "string") return null;
  try {
    const u = new URL(value);
    return ["https:", "http:"].includes(u.protocol) ? u.href : null;
  } catch {
    return null;
  }
}
export function nativeServerUrl(value: string): string {
  const url = new URL(value.trim());
  if (
    url.protocol !== "https:" ||
    url.username ||
    url.password ||
    url.search ||
    url.hash ||
    url.pathname !== "/"
  )
    throw new Error("Use the trusted HTTPS origin of your private server");
  return url.origin;
}
export function reviewableRows(rows: unknown[]): unknown[] {
  return rows.map((row) => {
    const r = row as {
      transaction?: unknown;
      recognized?: Record<string, unknown>;
    };
    return (
      r.transaction ?? {
        ...r.recognized,
        at: null,
        currency: r.recognized?.currency ?? "USD",
        fees: "0",
      }
    );
  });
}
