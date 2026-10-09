import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ApiClient, ImportReview } from "@stock-scanner/client";
import { ErrorBox, useAction, Disclosure } from "../../components/UI";
export type ProposedRow = {
  type: string;
  symbol: string | null;
  quantity: string | null;
  price: string | null;
  amount: string | null;
  at: string | null;
  fees: string | null;
  currency: string | null;
  source_text: string | null;
};
export type PortfolioProposal = {
  import_id: string;
  rows: ProposedRow[];
  warnings: string[];
};
export default function ChatPortfolioReview({
  api,
  proposal,
}: {
  api: ApiClient;
  proposal: PortfolioProposal;
}) {
  const [rows, setRows] = useState(proposal.rows),
    [error, setError] = useState<unknown>();
  const confirm = useAction(api, `/imports/${proposal.import_id}/confirm`),
    reject = useAction(api, `/imports/${proposal.import_id}/reject`);
  const saved = useQuery({
    queryKey: ["import", proposal.import_id],
    queryFn: () => api.request<ImportReview>(`/imports/${proposal.import_id}`),
  });
  const confirmed = !!confirm.data || saved.data?.status === "confirmed";
  const done = confirmed || !!reject.data || saved.data?.status === "rejected";
  const update = (i: number, key: keyof ProposedRow, value: string) =>
    setRows(
      rows.map((r, index) =>
        index === i ? { ...r, [key]: value || null } : r,
      ),
    );
  return (
    <section
      className="chat-portfolio-review"
      aria-label="Review proposed portfolio entries"
    >
      <h3>
        {done
          ? confirmed
            ? "Saved to your portfolio"
            : "Document dismissed"
          : "Review before saving to your portfolio"}
      </h3>
      <p className="muted small">
        {rows.length} proposed entries. Check the document, amounts, dates and
        currency. Missing values stay unknown.
      </p>
      {!done && (
        <>
          {proposal.warnings.map((w, i) => (
            <p key={i} className="warning small">
              {w}
            </p>
          ))}
          {rows.map((r, i) => {
            const shares = ["opening", "buy", "sell", "split"].includes(r.type);
            return (
              <fieldset className="proposal-entry" key={i}>
                <legend>Entry {i + 1}</legend>
                <div className="proposal-fields">
                  <label>
                    Type
                    <select
                      value={r.type}
                      onChange={(e) => update(i, "type", e.target.value)}
                    >
                      {[
                        "opening",
                        "buy",
                        "sell",
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
                  {shares ? (
                    <>
                      <label>
                        Symbol
                        <input
                          value={r.symbol ?? ""}
                          onChange={(e) =>
                            update(i, "symbol", e.target.value.toUpperCase())
                          }
                        />
                      </label>
                      <label>
                        {r.type === "split" ? "Split factor" : "Quantity"}
                        <input
                          inputMode="decimal"
                          value={r.quantity ?? ""}
                          onChange={(e) =>
                            update(i, "quantity", e.target.value)
                          }
                        />
                      </label>
                      {r.type !== "split" && (
                        <label>
                          {r.type === "opening"
                            ? "Unit cost (optional)"
                            : "Unit price"}
                          <input
                            inputMode="decimal"
                            value={r.price ?? ""}
                            onChange={(e) => update(i, "price", e.target.value)}
                          />
                        </label>
                      )}
                    </>
                  ) : (
                    <label>
                      Amount
                      <input
                        inputMode="decimal"
                        value={r.amount ?? ""}
                        onChange={(e) => update(i, "amount", e.target.value)}
                      />
                    </label>
                  )}
                  <label>
                    Actual timestamp with timezone
                    <input
                      placeholder="2026-10-08T10:00:00+03:00"
                      value={r.at ?? ""}
                      onChange={(e) => update(i, "at", e.target.value)}
                    />
                  </label>
                  <label>
                    Currency
                    <select
                      value={r.currency ?? ""}
                      onChange={(e) => update(i, "currency", e.target.value)}
                    >
                      <option value="">Confirm currency</option>
                      <option>USD</option>
                    </select>
                  </label>
                  {r.type !== "split" && (
                    <label>
                      Fees
                      <input
                        inputMode="decimal"
                        value={r.fees ?? ""}
                        onChange={(e) => update(i, "fees", e.target.value)}
                      />
                    </label>
                  )}
                </div>
                <Disclosure title="Source evidence">
                  <p>
                    {r.source_text ??
                      "No source excerpt was supplied. Check the original document."}
                  </p>
                </Disclosure>
                <button
                  className="muted small"
                  onClick={() =>
                    setRows(rows.filter((_, index) => index !== i))
                  }
                >
                  Remove this entry
                </button>
              </fieldset>
            );
          })}
          <div className="inline">
            <button
              className="primary"
              disabled={confirm.isPending || !rows.length}
              onClick={() => {
                try {
                  const cleaned = rows.map(({ source_text, ...r }) => {
                    if (!r.at || !r.currency || (r.type !== "split" && !r.fees))
                      throw new Error(
                        "Review the timestamp, currency and fees for every entry.",
                      );
                    const shares = ["opening", "buy", "sell", "split"].includes(
                      r.type,
                    );
                    return {
                      ...r,
                      symbol: shares ? r.symbol : null,
                      quantity: shares ? r.quantity : null,
                      price: shares && r.type !== "split" ? r.price : null,
                      amount: shares ? null : r.amount,
                      fees: r.type === "split" ? "0" : r.fees,
                    };
                  });
                  confirm.mutate({ rows: cleaned });
                  setError(null);
                } catch (e) {
                  setError(e);
                }
              }}
            >
              Save reviewed entries
            </button>
            <button
              disabled={reject.isPending}
              onClick={() => reject.mutate({})}
            >
              Dismiss document
            </button>
          </div>
        </>
      )}
      <ErrorBox error={error ?? confirm.error ?? reject.error} />
    </section>
  );
}
