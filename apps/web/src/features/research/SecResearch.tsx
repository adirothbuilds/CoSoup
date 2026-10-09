import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Database, FileText, RefreshCw, ArrowUpRight } from "lucide-react";
import { ApiClient, Report, safeSource, money } from "@stock-scanner/client";
import {
  Panel,
  Badge,
  Disclosure,
  ErrorBox,
  useAction,
  ActionState,
} from "../../components/UI";

type Metric = {
  label: string;
  value: number;
  unit: string;
  period_start?: string;
  period_end: string;
  filing_date: string;
  source: string;
};
type Filing = {
  form: string;
  source: string;
  filing_date: string;
  period_end: string;
};
type Holding = {
  issuer: string;
  cusip: string;
  class: string;
  put_call: string;
  shares: number;
  value_usd: number;
  amount_type: string;
};
type Manager = {
  name: string;
  cik: string;
  gaps: string[];
  snapshots: {
    period_end: string;
    filing_date: string;
    source: string;
    holdings: Holding[];
  }[];
  changes: (Holding & { change: string; share_delta: number })[];
};
export type SecReport = {
  as_of: string;
  checked_at: string;
  status: string;
  companies: {
    symbol: string;
    name?: string;
    metrics: Metric[];
    filings: Filing[];
    gaps: string[];
    documents: (Filing & { text_excerpt: string; truncated: boolean })[];
  }[];
  managers: Manager[];
  limitations: string[];
  errors: { endpoint: string; http_status: number | string; message: string }[];
};

function Source({ url, children }: { url: string; children: React.ReactNode }) {
  return safeSource(url) ? (
    <a href={safeSource(url)!} target="_blank" rel="noreferrer">
      {children} <ArrowUpRight size={13} />
    </a>
  ) : (
    <span>{children}</span>
  );
}
function Trend({ rows }: { rows: Metric[] }) {
  // Compare only periods of the same length (a quarter, a year, or an instant).
  const newest = rows[0],
    duration = (r: Metric) =>
      r.period_start
        ? Math.round(
            (Date.parse(r.period_end) - Date.parse(r.period_start)) / 86400000,
          )
        : 0;
  const values = rows
    .filter((r) => Math.abs(duration(r) - duration(newest)) <= 7)
    .sort((a, b) => a.period_end.localeCompare(b.period_end));
  const max = Math.max(...values.map((r) => Math.abs(r.value)), 1);
  return (
    <div
      className="financial-trend"
      role="img"
      aria-label={`${newest.label}: ${values.map((r) => `${r.period_end}: ${r.value} ${r.unit}`).join("; ")}`}
    >
      {values.map((r) => (
        <div
          key={`${r.period_end}-${r.period_start}`}
          title={`${r.period_end}: ${money(r.value)}`}
        >
          <span
            style={{
              height: `${Math.max(3, (Math.abs(r.value) / max) * 100)}%`,
            }}
            className={r.value < 0 ? "negative" : ""}
          />
          <small>{r.period_end.slice(0, 7)}</small>
        </div>
      ))}
    </div>
  );
}
export function SecReportView({
  data,
  preferredSymbol,
}: {
  data: SecReport;
  preferredSymbol?: string;
}) {
  const [chosen, setChosen] = useState("");
  const c =
    data.companies.find((c) => c.symbol === (chosen || preferredSymbol)) ??
    data.companies[0];
  const labels = [...new Set(c?.metrics.map((m) => m.label))];
  return (
    <div className="sec-report">
      <div className="source-context">
        <Badge>{data.status}</Badge>
        <span>SEC knowledge as of {data.as_of}</span>
        <span>Market prices retain their scan date.</span>
      </div>
      {!!data.errors.length && (
        <div className="notice warning" role="status">
          Public source access needs attention.{" "}
          {data.errors.map((e, i) => (
            <p key={i}>
              {e.http_status}: {e.message} ·{" "}
              <Source url={e.endpoint}>Source endpoint</Source>
            </p>
          ))}
        </div>
      )}
      {!!data.companies.length && (
        <div className="source-tabs" role="group" aria-label="SEC companies">
          {data.companies.map((company) => (
            <button
              key={company.symbol}
              aria-pressed={c?.symbol === company.symbol}
              onClick={() => setChosen(company.symbol)}
            >
              {company.symbol}
            </button>
          ))}
        </div>
      )}
      {c && (
        <>
          <h3>
            {c.name ?? c.symbol} <small>{c.symbol}</small>
          </h3>
          <div className="financial-cards">
            {labels.map((label) => {
              const rows = c.metrics.filter((m) => m.label === label),
                m = rows[0];
              return (
                <article className="financial-card" key={label}>
                  <span>{label}</span>
                  <strong>
                    {m.unit === "USD"
                      ? money(m.value)
                      : `${m.value.toFixed(2)} ${m.unit}`}
                  </strong>
                  <Trend rows={rows} />
                  <small>
                    {m.period_start ? `${m.period_start} → ` : "As of "}
                    {m.period_end}
                  </small>
                  <Source url={m.source}>Filed {m.filing_date}</Source>
                </article>
              );
            })}
          </div>
          {!labels.length && (
            <p className="muted">
              Financial data is unavailable. Missing figures are not zero.
            </p>
          )}
          <Disclosure title={`Company filings · ${c.filings.length}`} open>
            <div className="filing-grid">
              {c.filings.map((f, i) => (
                <Source key={i} url={f.source}>
                  <FileText size={18} />
                  <strong>{f.form}</strong>
                  <span>{f.filing_date}</span>
                </Source>
              ))}
            </div>
          </Disclosure>
          {c.documents.map((doc, i) => (
            <Disclosure
              key={i}
              title={`${doc.form} · ${doc.period_end} · Cached document excerpt`}
            >
              <Source url={doc.source}>Read the original filing</Source>
              <p className="muted">
                {doc.truncated
                  ? "Excerpt is limited to the first 40,000 characters; the complete source is cached."
                  : "Text extracted from the cached filing."}
              </p>
              <div className="document-excerpt">{doc.text_excerpt}</div>
            </Disclosure>
          ))}
          <Disclosure title="Company coverage gaps">
            {c.gaps.map((g, i) => (
              <p key={i} className="warning">
                {g}
              </p>
            ))}
          </Disclosure>
        </>
      )}
      <div className="ownership-heading">
        <Database size={20} />
        <div>
          <h3>Inside the reported portfolios</h3>
          <p>
            Selected managers · Quarter-end holdings, with a reporting delay
          </p>
        </div>
      </div>
      <div className="manager-grid">
        {data.managers.map((m) => {
          const s = m.snapshots[0],
            total = s?.holdings.reduce((n, h) => n + h.value_usd, 0) ?? 0;
          return (
            <article className="manager-card" key={m.cik}>
              <h4>{m.name}</h4>
              {s ? (
                <>
                  <p className="muted">
                    As of {s.period_end} · Filed {s.filing_date}
                  </p>
                  <div className="holdings-bars">
                    {s.holdings.slice(0, 8).map((h, i) => (
                      <div key={i}>
                        <div>
                          <span>
                            {h.issuer}
                            {h.put_call ? ` · ${h.put_call}` : ""}
                          </span>
                          <strong>
                            {((h.value_usd / Math.max(total, 1)) * 100).toFixed(
                              1,
                            )}
                            %
                          </strong>
                        </div>
                        <span className="holding-track">
                          <span
                            style={{
                              width: `${(h.value_usd / Math.max(total, 1)) * 100}%`,
                            }}
                          />
                        </span>
                      </div>
                    ))}
                  </div>
                  <small>
                    Share of reported 13F value; not total assets or conviction.
                  </small>
                  <p>
                    <Source url={s.source}>Original holdings table</Source>
                  </p>
                  <Disclosure
                    title={`Changes between reported quarters · ${m.changes.length}`}
                  >
                    <div className="table-scroll">
                      <table>
                        <thead>
                          <tr>
                            <th>Issuer</th>
                            <th>Reported change</th>
                            <th>Amount difference</th>
                          </tr>
                        </thead>
                        <tbody>
                          {m.changes.map((h, i) => (
                            <tr key={i}>
                              <td>
                                {h.issuer} {h.put_call}
                              </td>
                              <td>{h.change.replaceAll("_", " ")}</td>
                              <td>
                                {h.share_delta.toLocaleString()} {h.amount_type}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </Disclosure>
                  <Disclosure
                    title={`All reported holdings · ${s.holdings.length}`}
                  >
                    <div className="table-scroll">
                      <table>
                        <thead>
                          <tr>
                            <th>Issuer / class</th>
                            <th>Amount</th>
                            <th>Reported value</th>
                          </tr>
                        </thead>
                        <tbody>
                          {s.holdings.map((h, i) => (
                            <tr key={i}>
                              <td>
                                {h.issuer} · {h.class} {h.put_call}
                              </td>
                              <td>
                                {h.shares.toLocaleString()} {h.amount_type}
                              </td>
                              <td>{money(h.value_usd)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </Disclosure>
                </>
              ) : (
                <p>
                  Holdings unavailable; no institutional conclusion can be
                  drawn.
                </p>
              )}
              {m.gaps.map((g, i) => (
                <p className="warning" key={i}>
                  {g}
                </p>
              ))}
            </article>
          );
        })}
      </div>
      <Disclosure title="How to read this research">
        {data.limitations.map((g, i) => (
          <p key={i}>{g}</p>
        ))}
      </Disclosure>
    </div>
  );
}

export default function SecResearch({
  api,
  reports,
  reportId,
  selected,
}: {
  api: ApiClient;
  reports: Report[];
  reportId?: string;
  selected?: string;
}) {
  const [symbols, setSymbols] = useState(""),
    [managers, setManagers] = useState("1067983, 1336528");
  const saved = reports.find((r) => r.mode === "sec_research");
  const data = useQuery({
    queryKey: ["sec-report", saved?.id],
    queryFn: () => api.request<SecReport>(`/reports/${saved!.id}/content`),
    enabled: !!saved,
    staleTime: Infinity,
  });
  const sync = useAction(api, "/research/sec-sync");
  return (
    <div id="sec-research">
      <Panel
        title="Company filings & institutional holdings"
        aside={<Badge>Public SEC sources</Badge>}
      >
        <div className="padded">
          <p className="muted">
            Financial statements, original filings and selected institutional
            snapshots. Syncing uses public sources and leaves your market scan
            intact.
          </p>
          <form
            className="sec-sync-form"
            onSubmit={(e) => {
              e.preventDefault();
              sync.mutate({
                symbols: symbols
                  .toUpperCase()
                  .split(/[\s,]+/)
                  .filter(Boolean),
                ...(reportId ? { report_id: reportId } : {}),
                manager_ciks: managers.split(/[\s,]+/).filter(Boolean),
              });
            }}
          >
            <label>
              Stock symbols
              <input
                aria-label="SEC stock symbols"
                placeholder={
                  selected || "Leave blank for this scan's candidates"
                }
                value={symbols}
                onChange={(e) => setSymbols(e.target.value)}
              />
            </label>
            <label>
              Manager CIKs
              <input
                aria-label="SEC manager CIKs"
                value={managers}
                onChange={(e) => setManagers(e.target.value)}
              />
              <small>Default: Berkshire Hathaway and Pershing Square.</small>
            </label>
            <button
              className="primary"
              disabled={sync.isPending || (!symbols.trim() && !reportId)}
            >
              <RefreshCw size={16} /> Sync public research
            </button>
          </form>
          <ActionState action={sync} />
          <ErrorBox error={data.error} />
          {sync.done && (
            <a href="#activity">Follow sync progress in Activity →</a>
          )}
          {data.isPending && saved && (
            <p role="status">Loading saved SEC research…</p>
          )}
          {data.data ? (
            <SecReportView data={data.data} preferredSymbol={selected} />
          ) : (
            !saved && (
              <div className="sec-empty">
                <FileText size={26} />
                <p>Your company research shelf starts here.</p>
                <small>
                  Choose symbols, then sync their public filings. No paid data
                  plan is required.
                </small>
              </div>
            )
          )}
        </div>
      </Panel>
    </div>
  );
}
