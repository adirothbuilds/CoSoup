import { useState } from "react";
import { ApiClient, Portfolio } from "@stock-scanner/client";
import { ErrorBox, useAction } from "../../components/UI";
export type ChatDocument = {
  name: string;
  upload_id: string;
  import_id: string;
  job_id: string;
  image: boolean;
};
export default function ChatDocuments({
  api,
  portfolios,
  documents,
  onAdd,
  onRemove,
  disabled,
  selectedPortfolio,
  onPortfolio,
}: {
  api: ApiClient;
  portfolios: Portfolio[];
  documents: ChatDocument[];
  onAdd: (d: ChatDocument) => void;
  onRemove: (id: string) => void;
  disabled: boolean;
  selectedPortfolio: string;
  onPortfolio: (id: string) => void;
}) {
  const [busy, setBusy] = useState(false),
    [error, setError] = useState<unknown>(),
    [name, setName] = useState("");
  const create = useAction(api, "/portfolios");
  async function upload(files: FileList) {
    setBusy(true);
    setError(null);
    try {
      for (const file of Array.from(files).slice(0, 4 - documents.length)) {
        const type = file.name.toLowerCase().endsWith(".csv")
          ? "text/csv"
          : file.type;
        const form = new FormData();
        form.append("file", new Blob([file], { type }), file.name);
        const u = await api.upload(form);
        const i = await api.request<{ import_id: string; job_id: string }>(
          "/imports",
          "POST",
          { upload_id: u.upload_id, portfolio_id: selectedPortfolio },
          crypto.randomUUID(),
        );
        onAdd({
          name: file.name,
          upload_id: u.upload_id,
          import_id: i.import_id,
          job_id: i.job_id,
          image: ["image/png", "image/jpeg"].includes(type),
        });
      }
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="chat-document-picker">
      <p className="muted small">
        Attach a holdings screenshot, statement, PDF or CSV. Local extraction
        prepares evidence; Steve can interpret images and propose entries for
        review.
      </p>
      {portfolios.length ? (
        <label>
          Destination portfolio
          <select
            value={selectedPortfolio}
            disabled={disabled || busy || documents.length > 0}
            onChange={(e) => onPortfolio(e.target.value)}
          >
            <option value="">Choose a portfolio</option>
            {portfolios.map((p) => (
              <option value={p.id} key={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </label>
      ) : (
        <div className="inline">
          <label>
            Portfolio name
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="My portfolio"
            />
          </label>
          <button
            disabled={!name.trim() || create.isPending}
            onClick={async () => {
              try {
                const result = await create.mutateAsync({
                  name: name.trim(),
                  currency: "USD",
                });
                if ("id" in result) onPortfolio(String(result.id));
              } catch (e) {
                setError(e);
              }
            }}
          >
            Create portfolio
          </button>
        </div>
      )}
      <label className="file-picker">
        {busy ? "Preparing attachments…" : "Choose screenshots or documents"}
        <input
          aria-label="Attach screenshots or documents"
          type="file"
          accept=".png,.jpg,.jpeg,.pdf,.csv"
          multiple
          disabled={
            disabled || busy || !selectedPortfolio || documents.length >= 4
          }
          onChange={(e) => {
            if (e.target.files) void upload(e.target.files);
            e.target.value = "";
          }}
        />
      </label>
      {documents.map((d) => (
        <div className="attachment-chip" key={d.import_id}>
          <span>{d.name}</span>
          <button
            disabled={disabled || busy}
            aria-label={`Remove ${d.name}`}
            onClick={() => onRemove(d.import_id)}
          >
            ×
          </button>
        </div>
      ))}
      <ErrorBox error={error ?? create.error} />
    </div>
  );
}
