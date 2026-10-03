import { FormEvent, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ApiClient,
  ImportReview,
  Portfolio as PortfolioType,
  Transaction,
  reviewableRows,
  money,
} from "@stock-scanner/client";
import {
  ActionState,
  Disclosure,
  Empty,
  ErrorBox,
  Json,
  Metric,
  Panel,
  useAction,
} from "../../components/UI";

export function TransactionForm({
  api,
  portfolioId,
  original,
}: {
  api: ApiClient;
  portfolioId: string;
  original?: Transaction;
}) {
  const [type, setType] = useState<Transaction["type"]>(
    original?.type ?? "buy",
  );
  const action = useAction(
    api,
    `/portfolios/${portfolioId}/transactions${original ? `/${original.id}/corrections` : ""}`,
  );
  const share = ["buy", "sell", "opening", "split"].includes(type);
  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const values: Record<string, unknown> = {
      type,
      at: new Date(String(f.get("at"))).toISOString(),
      fees: f.get("fees") || "0",
      currency: "USD",
      external_ref: f.get("ref") || crypto.randomUUID(),
    };
    if (share) {
      values.symbol = String(f.get("symbol")).trim().toUpperCase();
      values.quantity = f.get("quantity");
      if (type !== "split" && f.get("price")) values.price = f.get("price");
    } else values.amount = f.get("amount");
    action.mutate(values);
  }
  return (
    <form onSubmit={submit} className="form-grid">
      <label>
        Entry type
        <select
          value={type}
          onChange={(e) => setType(e.target.value as Transaction["type"])}
        >
          {[
            "buy",
            "sell",
            "opening",
            "deposit",
            "withdrawal",
            "dividend",
            "fee",
            "split",
          ].map((t) => (
            <option key={t}>{t}</option>
          ))}
        </select>
      </label>
      <label>
        Actual time (device timezone)
        <input
          type="datetime-local"
          name="at"
          required
          defaultValue={
            original
              ? new Date(
                  new Date(original.at).getTime() -
                    new Date(original.at).getTimezoneOffset() * 60000,
                )
                  .toISOString()
                  .slice(0, 16)
              : undefined
          }
        />
      </label>
      {share ? (
        <>
          <label>
            Symbol
            <input
              name="symbol"
              required
              defaultValue={original?.symbol ?? ""}
              autoCapitalize="characters"
            />
          </label>
          <label>
            {type === "split" ? "Split factor" : "Quantity"}
            <input
              name="quantity"
              inputMode="decimal"
              required
              defaultValue={original?.quantity ?? ""}
            />
          </label>
          {type !== "split" && (
            <label>
              {type === "opening"
                ? "Unit cost (optional; blank = unknown)"
                : "Actual unit price"}
              <input
                name="price"
                inputMode="decimal"
                required={type !== "opening"}
                defaultValue={original?.price ?? ""}
              />
            </label>
          )}
        </>
      ) : (
        <label>
          Amount (USD)
          <input
            name="amount"
            inputMode="decimal"
            required
            defaultValue={original?.amount ?? ""}
          />
        </label>
      )}
      {type !== "split" && (
        <label>
          Fees (USD)
          <input
            name="fees"
            inputMode="decimal"
            defaultValue={original?.fees ?? "0"}
          />
        </label>
      )}
      <label>
        External reference (optional)
        <input name="ref" defaultValue="" />
      </label>
      <div className="full">
        <button className="primary" disabled={action.isPending}>
          {original ? "Save audited correction" : "Record journal entry"}
        </button>
        <ActionState action={action} />
      </div>
    </form>
  );
}
export function ImportPanel({
  api,
  portfolioId,
}: {
  api: ApiClient;
  portfolioId: string;
}) {
  const [id, setId] = useState("");
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<unknown>();
  const [rows, setRows] = useState("[]");
  const qc = useQueryClient();
  const review = useQuery({
    queryKey: ["import", id],
    queryFn: () => api.request<ImportReview>(`/imports/${id}`),
    enabled: !!id,
    refetchInterval: (q) => (q.state.data?.status === "queued" ? 3000 : false),
  });
  const confirm = useAction(api, `/imports/${id}/confirm`);
  const reject = useAction(api, `/imports/${id}/reject`);
  async function upload(file: File) {
    setUploading(true);
    setError(null);
    try {
      const type = file.name.endsWith(".csv") ? "text/csv" : file.type;
      const form = new FormData();
      form.append("file", new Blob([file], { type }), file.name);
      const result = await api.upload(form);
      const imported = await api.request<{ import_id: string }>(
        "/imports",
        "POST",
        { portfolio_id: portfolioId, upload_id: result.upload_id },
        crypto.randomUUID(),
      );
      setId(imported.import_id);
      qc.invalidateQueries({ queryKey: ["jobs"] });
    } catch (e) {
      setError(e);
    } finally {
      setUploading(false);
    }
  }
  const data = review.data;
  return (
    <div>
      <p className="muted">
        Upload a transaction CSV, JPEG/PNG or PDF. Extraction proposes entries;
        you review every row before anything enters the journal.
      </p>
      <label className="file-picker">
        Choose document or image
        <input
          type="file"
          accept=".csv,.pdf,.jpg,.jpeg,.png"
          disabled={uploading}
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) void upload(file);
          }}
        />
      </label>
      {uploading && <p role="status">Uploading…</p>}
      <div className="inline">
        <label>
          Existing import ID
          <input
            value={id}
            onChange={(e) => setId(e.target.value)}
            placeholder="Resume a review by ID"
          />
        </label>
      </div>
      <ErrorBox error={error ?? review.error} />
      {data && (
        <>
          <p>Status: {data.status}</p>
          <Disclosure title="Extraction & source evidence">
            <Json value={data.proposal} />
          </Disclosure>
          {data.status === "awaiting_review" && (
            <>
              <button
                onClick={() =>
                  setRows(
                    JSON.stringify(
                      reviewableRows(data.proposal.rows ?? []),
                      null,
                      2,
                    ),
                  )
                }
              >
                Copy proposals into review editor
              </button>
              <label>
                Reviewed transaction rows (JSON)
                <textarea
                  className="code-editor"
                  value={rows}
                  onChange={(e) => setRows(e.target.value)}
                  rows={12}
                />
              </label>
              <p className="muted small">
                Resolve missing values. Each row needs a timezone-aware at,
                currency USD and fees. Server validation checks the effective
                ledger atomically.
              </p>
              <div className="inline">
                <button
                  className="primary"
                  disabled={confirm.isPending}
                  onClick={() => {
                    try {
                      confirm.mutate({ rows: JSON.parse(rows) });
                    } catch (e) {
                      setError(e);
                    }
                  }}
                >
                  Confirm reviewed rows
                </button>
                <button
                  disabled={reject.isPending}
                  onClick={() => reject.mutate({})}
                >
                  Reject import
                </button>
              </div>
              <ActionState action={confirm} />
              <ActionState action={reject} />
            </>
          )}
        </>
      )}
    </div>
  );
}
export default function Portfolio({
  api,
  portfolios,
}: {
  api: ApiClient;
  portfolios: PortfolioType[];
}) {
  const [selected, setSelected] = useState("");
  const p = portfolios.find((p) => p.id === selected) ?? portfolios[0];
  const create = useAction(api, "/portfolios");
  const [correction, setCorrection] = useState<Transaction>();
  const [offset, setOffset] = useState(0);
  const ledger = useQuery({
    queryKey: ["positions", p?.id],
    queryFn: () => api.positions(p!.id),
    enabled: !!p,
  });
  const transactions = useQuery({
    queryKey: ["transactions", p?.id, offset],
    queryFn: () =>
      api.request<Transaction[]>(
        `/portfolios/${p!.id}/transactions?limit=100&offset=${offset}`,
      ),
    enabled: !!p,
  });
  const analysis = useAction(api, `/portfolios/${p?.id}/analysis-jobs`);
  return (
    <>
      <div className="workspace-controls">
        <label>
          Portfolio
          <select
            value={p?.id ?? ""}
            onChange={(e) => {
              setSelected(e.target.value);
              setOffset(0);
            }}
          >
            {portfolios.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </label>
        <Disclosure title="Create portfolio">
          <form
            className="inline"
            onSubmit={(e) => {
              e.preventDefault();
              create.mutate({
                name: new FormData(e.currentTarget).get("name"),
                currency: "USD",
              });
            }}
          >
            <input
              name="name"
              placeholder="Portfolio name"
              aria-label="New portfolio name"
              required
            />
            <button disabled={create.isPending}>Create</button>
          </form>
          <ActionState action={create} />
        </Disclosure>
      </div>
      {!p ? (
        <Empty>Create a portfolio to begin your personal journal.</Empty>
      ) : (
        <>
          <ErrorBox error={ledger.error} />
          <Panel title="Supplied holdings">
            <div className="metrics">
              <Metric
                label="Reconstructed cash"
                value={money(ledger.data?.cash)}
              />
              <Metric
                label="Known realized P&L"
                value={money(ledger.data?.realized_pnl)}
                note="Supplied FIFO history"
              />
            </div>
            <p className="muted padded">{ledger.data?.cash_note}</p>
            {ledger.data?.positions.length ? (
              ledger.data.positions.map((pos) => (
                <div className="holding-row" key={pos.symbol}>
                  <strong>{pos.symbol}</strong>
                  <span>{pos.quantity} shares</span>
                  <span>
                    Basis {pos.basis_known ? money(pos.cost_basis) : "unknown"}
                  </span>
                </div>
              ))
            ) : (
              <Empty>No supplied positions.</Empty>
            )}
            <div className="padded">
              <form
                className="inline"
                onSubmit={(e) => {
                  e.preventDefault();
                  const d = new FormData(e.currentTarget).get("date");
                  analysis.mutate(d ? { data_date: d } : {});
                }}
              >
                <label>
                  Closing valuation date
                  <input type="date" name="date" />
                </label>
                <button disabled={analysis.isPending}>
                  Analyze closing valuation
                </button>
              </form>
              <ActionState action={analysis} />
              <p className="muted small">
                Dated valuation reports appear in Home / Reports. Holdings alone
                are not a current valuation.
              </p>
            </div>
          </Panel>
          <Disclosure title="Record a journal entry">
            <TransactionForm api={api} portfolioId={p.id} />
          </Disclosure>
          <Disclosure title="Import & review a document">
            <ImportPanel api={api} portfolioId={p.id} />
          </Disclosure>
          <Panel title="Journal">
            <ErrorBox error={transactions.error} />
            {transactions.data?.map((tx) => (
              <div className="journal-row" key={tx.id}>
                <div>
                  <strong>
                    {tx.type} {tx.symbol}
                  </strong>
                  <small>
                    {new Date(tx.at).toLocaleString()} ·{" "}
                    {tx.external_ref ?? "No external reference"}
                  </small>
                </div>
                <span>
                  {tx.quantity
                    ? `${tx.quantity} @ ${money(tx.price)}`
                    : money(tx.amount)}{" "}
                  · fees {money(tx.fees)}
                </span>
                {tx.superseded ? (
                  <span className="badge">Superseded</span>
                ) : (
                  <button onClick={() => setCorrection(tx)}>Correct</button>
                )}
              </div>
            ))}
            <div className="pagination">
              <button
                disabled={!offset}
                onClick={() => setOffset(Math.max(0, offset - 100))}
              >
                Previous
              </button>
              <span>
                Rows {offset + 1}–{offset + (transactions.data?.length ?? 0)}
              </span>
              <button
                disabled={transactions.data?.length !== 100}
                onClick={() => setOffset(offset + 100)}
              >
                Next
              </button>
            </div>
          </Panel>
          {correction && (
            <Panel
              title="Audited correction"
              aside={
                <button onClick={() => setCorrection(undefined)}>Close</button>
              }
            >
              <div className="padded">
                <p>
                  The replacement supersedes the selected journal entry. The
                  original remains auditable.
                </p>
                <TransactionForm
                  key={correction.id}
                  api={api}
                  portfolioId={p.id}
                  original={correction}
                />
              </div>
            </Panel>
          )}
        </>
      )}
    </>
  );
}
