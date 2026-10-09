import { useEffect, useRef, useState } from "react";
import {
  useMutation,
  useQueries,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import {
  ArrowUp,
  Plus,
  Sparkles,
  FileText,
  MessageSquare,
  Check,
  Clock3,
  ExternalLink,
  Paperclip,
  Archive,
  Pencil,
} from "lucide-react";
import {
  ApiClient,
  Report,
  Job,
  Portfolio,
  ImportReview,
  terminalStatuses,
  usableDailyReport,
} from "@stock-scanner/client";
import {
  Badge,
  Disclosure,
  ErrorBox,
  useAction,
  statusLabel,
} from "../../components/UI";
import Markdown from "../../components/Markdown";
import ChatCharts, { ChatChart } from "./ChatCharts";
import ChatPortfolioReview, { PortfolioProposal } from "./ChatPortfolioReview";
import ChatDocuments, { ChatDocument } from "./ChatDocuments";

type Turn = {
  job_id: string;
  prompt: string;
  status: string;
  report_id?: string;
  report_ids: string[];
  error?: { message: string };
  document_export_authorized?: boolean;
  portfolio_export_authorized?: boolean;
  import_ids?: string[];
  upload_ids?: string[];
  portfolio_id?: string;
  answer?: {
    charts?: ChatChart[];
    portfolio_proposals?: PortfolioProposal[];
    markdown: string;
    sources: string[];
    gaps: string[];
    data_date: string;
    status: string;
  };
};
type Conversation = {
  id: string;
  title: string;
  status: string;
  archived?: boolean;
};
const ideas = [
  {
    title: "Understand the setup",
    question:
      "Use the research tools to explain the selected scan: original filter thresholds, volatility, distance from the pivot in ATR units and relative strength over different windows. Show a useful chart and disclose the market-data date and coverage gaps.",
  },
  {
    title: "Check financial quality",
    question:
      "Inspect the financial research tools and compare the available companies using same-period margins, free cash flow, cash conversion and year-over-year growth where supported. Show a useful chart. Explain missing inputs and cite filing dates.",
  },
  {
    title: "Follow the reported holdings",
    question:
      "Inspect the institutional research tools. Explain reported concentration, exact-security overlap and share-count changes using comparable quarters. Show a useful chart, cite filing dates and explain coverage limits. Do not interpret snapshots as live purchases.",
  },
];
export default function SteveChat({
  api,
  reports,
}: {
  api: ApiClient;
  reports: Report[];
}) {
  const qc = useQueryClient();
  const [conversation, setConversation] = useState(
    new URLSearchParams(location.search).get("chat") ?? "",
  );
  const [draft, setDraft] = useState(""),
    [selected, setSelected] = useState<string[] | null>(null);
  const [awaiting, setAwaiting] = useState(false);
  const [sentJob, setSentJob] = useState("");
  const bottom = useRef<HTMLDivElement>(null);
  const [documents, setDocuments] = useState<ChatDocument[]>([]),
    [attachmentsOpen, setAttachmentsOpen] = useState(false);
  const [portfolioId, setPortfolioId] = useState(""),
    [sharePortfolio, setSharePortfolio] = useState(false),
    [shareDocuments, setShareDocuments] = useState(false);
  const [showArchived, setShowArchived] = useState(false),
    [renaming, setRenaming] = useState(false),
    [title, setTitle] = useState("");
  const portfolios = useQuery({
    queryKey: ["portfolios"],
    queryFn: () => api.portfolios(),
  });
  const extracts = useQueries({
    queries: documents.map((d) => ({
      queryKey: ["chat-extraction", d.import_id],
      queryFn: async () => {
        const job = await api.request<Job>(`/jobs/${d.job_id}`);
        if (job.status === "failed")
          throw new Error(
            job.error?.message ?? "Document extraction needs attention",
          );
        return api.request<ImportReview>(`/imports/${d.import_id}`);
      },
      refetchInterval: (q: any) =>
        q.state.data?.status === "queued" ? 3000 : false,
      retry: false,
    })),
  });
  const extractionReady = documents.every((_, i) =>
    ["awaiting_review", "confirmed"].includes(extracts[i].data?.status ?? ""),
  );
  const pendingDocumentContext = documents.length > 0 || false;
  const daily = usableDailyReport(reports),
    sec = reports.find(
      (r) => r.mode === "sec_research" && !r.quality.startsWith("blocked"),
    );
  const available = reports.filter(
    (r) =>
      ["live", "historical_snapshot", "sec_research"].includes(r.mode) &&
      !r.quality.startsWith("blocked"),
  );
  const approved = (
    selected ?? [daily?.id, sec?.id].filter((id): id is string => !!id)
  ).filter((id) => available.some((r) => r.id === id));
  const profiles = useQuery({
    queryKey: ["agent-profiles"],
    queryFn: () =>
      api.request<{ ready: boolean; backend?: { provider: string } }[]>(
        "/agent/profiles",
      ),
    staleTime: 60000,
  });
  const history = useQuery({
    queryKey: ["conversations"],
    queryFn: () => api.request<Conversation[]>("/agent/conversations"),
    staleTime: 10000,
  });
  const thread = useQuery({
    queryKey: ["conversation", conversation],
    queryFn: () =>
      api.request<{ messages: Turn[]; title?: string; archived?: boolean }>(
        `/agent/conversations/${conversation}`,
      ),
    enabled: !!conversation,
    refetchInterval: (q) =>
      q.state.data?.messages.some((t) => !terminalStatuses.has(t.status)) ||
      awaiting
        ? 3000
        : false,
  });
  const send = useAction(api, "/agent/chat");
  const turns = thread.data?.messages ?? [];
  const running =
    awaiting ||
    send.isPending ||
    turns.some((t) => !terminalStatuses.has(t.status));
  const ready = profiles.data?.[0]?.ready;
  const provider = profiles.data?.[0]?.backend?.provider ?? "codex";
  const current =
    history.data?.find((c) => c.id === conversation) ??
    (thread.data?.title
      ? {
          id: conversation,
          title: thread.data.title,
          archived: thread.data.archived,
          status: turns.at(-1)?.status ?? "succeeded",
        }
      : undefined);
  const privateDocuments =
    pendingDocumentContext || turns.some((t) => t.document_export_authorized);
  const privatePortfolio =
    sharePortfolio || turns.some((t) => t.portfolio_export_authorized);
  const evidenceReady =
    approved.length > 0 ||
    documents.length > 0 ||
    (sharePortfolio && !!portfolioId);
  const permissionsReady =
    (!privateDocuments || shareDocuments) &&
    (!privatePortfolio || sharePortfolio);
  const updateConversation = useMutation({
    mutationFn: (change: { title?: string; archived?: boolean }) =>
      api.request(`/agent/conversations/${conversation}`, "PATCH", change),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["conversations"] });
      setRenaming(false);
    },
  });
  useEffect(() => {
    if (awaiting && sentJob && turns.some((t) => t.job_id === sentJob))
      setAwaiting(false);
  }, [turns, awaiting, sentJob]);
  useEffect(() => {
    if (!turns.length) return;
    const body = bottom.current?.parentElement;
    body?.scrollTo({
      top: body.scrollHeight,
      behavior:
        document.documentElement.dataset.motion === "off"
          ? "instant"
          : "smooth",
    });
  }, [turns.length, turns.at(-1)?.status]);
  function open(id: string) {
    setConversation(id);
    setAwaiting(false);
    const url = new URL(location.href);
    if (id) url.searchParams.set("chat", id);
    else url.searchParams.delete("chat");
    historyReplace(url);
  }
  async function submit() {
    if (
      !draft.trim() ||
      running ||
      !evidenceReady ||
      !ready ||
      !permissionsReady ||
      !extractionReady ||
      current?.archived
    )
      return;
    const id = conversation || crypto.randomUUID().replaceAll("-", "");
    open(id);
    setAwaiting(true);
    try {
      const result = await send.mutateAsync({
        conversation_id: id,
        prompt: draft.trim(),
        report_ids: approved,
        portfolio_id: sharePortfolio ? portfolioId || undefined : undefined,
        allow_portfolio_data: sharePortfolio,
        upload_ids: documents.filter((d) => d.image).map((d) => d.upload_id),
        import_ids: documents.map((d) => d.import_id),
        allow_uploaded_documents: shareDocuments,
      });
      if ("job_id" in result) setSentJob(result.job_id);
      setDraft("");
      setDocuments([]);
      setAttachmentsOpen(false);
      await qc.invalidateQueries({ queryKey: ["conversation", id] });
      await qc.invalidateQueries({ queryKey: ["conversations"] });
    } catch {
      setAwaiting(false);
    }
  }
  return (
    <section className="steve-workspace" aria-label="Chat with Steve">
      <aside className="steve-sources">
        <div className="steve-identity">
          <img src="/mascots/steve.webp" alt="Steve" />
          <div>
            <strong>Steve</strong>
            <small>Your research companion</small>
          </div>
          <span
            className={`connection-dot ${ready ? "ready" : ""}`}
            title={ready ? "Codex connected" : "Connection needs attention"}
          />
        </div>

        <button
          className="new-chat"
          disabled={running}
          onClick={() => {
            open("");
            setDraft("");
            setDocuments([]);
            setShareDocuments(false);
            setSharePortfolio(false);
          }}
        >
          <Plus size={16} /> New conversation
        </button>
        <details className="chat-context">
          <summary>Sources & conversations</summary>
          <div className="chat-context-body">
            <h3>On the research desk</h3>
            <p className="muted small">
              Choose the evidence for your next question.
            </p>
            <div className="source-list">
              {available.slice(0, 10).map((r) => (
                <label className="source-card" key={r.id}>
                  <input
                    type="checkbox"
                    checked={approved.includes(r.id)}
                    onChange={(e) =>
                      setSelected(
                        e.target.checked
                          ? [...approved, r.id].slice(0, 4)
                          : approved.filter((id) => id !== r.id),
                      )
                    }
                  />
                  <FileText size={17} />
                  <span>
                    <strong>{statusLabel(r.mode)}</strong>
                    <small>
                      {r.data_date} · {statusLabel(r.quality)}
                    </small>
                  </span>
                </label>
              ))}
            </div>
            {!available.length && (
              <p className="muted">
                Sync public filings or finish a market scan to give Steve
                evidence.
              </p>
            )}
            <a className="source-link" href="#research">
              Explore charts & filings <ExternalLink size={13} />
            </a>
            {!!history.data?.length && (
              <>
                <h3>Recent conversations</h3>
                <div className="conversation-list">
                  {history.data
                    .filter((c) => !!c.archived === showArchived)
                    .map((c) => (
                      <button
                        key={c.id}
                        disabled={running}
                        className={c.id === conversation ? "selected" : ""}
                        onClick={() => open(c.id)}
                      >
                        <MessageSquare size={14} />
                        <span>{c.title}</span>
                      </button>
                    ))}
                </div>
              </>
            )}
            {!!history.data?.length && (
              <button
                className="muted small"
                onClick={() => setShowArchived(!showArchived)}
              >
                {showArchived
                  ? "Active conversations"
                  : "Archived conversations"}
              </button>
            )}
          </div>
        </details>
      </aside>
      <div className="steve-chat">
        <header className="chat-head">
          <div>
            <Sparkles size={17} />
            <span>{current?.title ?? "Research, together."}</span>
          </div>
          <span className="muted small">
            {ready ? `${provider} connected` : "Steve needs a connection"}
          </span>
          {conversation && current && (
            <div className="conversation-actions">
              <button
                aria-label="Rename conversation"
                onClick={() => {
                  setTitle(current.title);
                  setRenaming(!renaming);
                }}
              >
                <Pencil size={14} />
              </button>
              <button
                disabled={running || updateConversation.isPending}
                aria-label={
                  current.archived
                    ? "Restore conversation"
                    : "Archive conversation"
                }
                onClick={() =>
                  updateConversation.mutate({ archived: !current.archived })
                }
              >
                <Archive size={14} />
              </button>
            </div>
          )}
        </header>
        {renaming && (
          <form
            className="inline rename-conversation"
            onSubmit={(e) => {
              e.preventDefault();
              updateConversation.mutate({ title: title.trim() });
            }}
          >
            <input
              aria-label="Conversation name"
              value={title}
              maxLength={120}
              onChange={(e) => setTitle(e.target.value)}
            />
            <button disabled={!title.trim() || updateConversation.isPending}>
              Save name
            </button>
          </form>
        )}
        <ErrorBox error={updateConversation.error} />
        <div className="chat-body" aria-live="polite" aria-busy={running}>
          {!turns.length && (
            <div className="chat-welcome">
              <span className="steve-signature">
                <Sparkles size={20} /> ASK STEVE
              </span>
              <h2>What would you like to understand?</h2>
              <p>
                Explore your research, compare the evidence or attach a
                portfolio document.
              </p>
              <div className="question-cards">
                {ideas.map((idea, i) => (
                  <button key={i} onClick={() => setDraft(idea.question)}>
                    <span>0{i + 1}</span>
                    <strong>{idea.title}</strong>
                    <ArrowUp size={17} />
                  </button>
                ))}
              </div>
            </div>
          )}
          {thread.isPending && conversation && (
            <p className="muted">Loading your saved conversation…</p>
          )}
          <ErrorBox error={thread.error ?? history.error} />
          {turns.map((t) => (
            <div className="chat-turn" key={t.job_id}>
              <div className="chat-question">
                <span>You</span>
                <p>{t.prompt}</p>
              </div>
              <div className="chat-answer">
                <div className="answer-byline">
                  <Sparkles size={16} />
                  <strong>Steve</strong>
                  <Badge>{t.status}</Badge>
                  {t.answer && (
                    <small>Knowledge cutoff {t.answer.data_date}</small>
                  )}
                </div>
                {t.answer ? (
                  <>
                    <Markdown
                      text={t.answer.markdown}
                      sourceLabels={Object.fromEntries(
                        reports.map((r) => [
                          r.id,
                          `${statusLabel(r.mode)} · ${r.data_date}`,
                        ]),
                      )}
                    />
                    {!!t.answer.charts?.length && (
                      <ChatCharts charts={t.answer.charts} />
                    )}
                    {t.answer.portfolio_proposals?.map((p) => (
                      <ChatPortfolioReview
                        key={p.import_id}
                        api={api}
                        proposal={p}
                      />
                    ))}
                    <div className="answer-sources">
                      {t.answer.sources.map((id) => {
                        const r = reports.find((r) => r.id === id);
                        if (!r)
                          return (
                            <span className="source-reference" key={id}>
                              <FileText size={13} />
                              {id === t.portfolio_id
                                ? "Portfolio context"
                                : t.import_ids?.includes(id) ||
                                    t.upload_ids?.includes(id)
                                  ? "Attached document"
                                  : "Dated evidence"}
                            </span>
                          );
                        return (
                          <a
                            key={id}
                            href={`?report=${encodeURIComponent(id)}#home`}
                          >
                            <FileText size={13} />
                            {r
                              ? `${statusLabel(r.mode)} · ${r.data_date}`
                              : `Evidence ${id.slice(0, 8)}`}
                          </a>
                        );
                      })}
                    </div>
                    {!!t.answer.gaps.length && (
                      <Disclosure
                        title={`What remains uncertain · ${t.answer.gaps.length}`}
                      >
                        {t.answer.gaps.map((gap, i) => (
                          <p key={i} className="warning">
                            {gap}
                          </p>
                        ))}
                      </Disclosure>
                    )}
                    <a
                      className="muted small"
                      href={`?report=${t.report_id}#home`}
                    >
                      Open saved analysis & downloads →
                    </a>
                  </>
                ) : t.error ? (
                  <>
                    <ErrorBox error={new Error(t.error.message)} />
                    <a href="#activity">Inspect this job in Activity →</a>
                  </>
                ) : (
                  <div className="thinking">
                    <span />
                    <span />
                    <span />
                    <p>
                      Steve is reading your selected sources. The answer will be
                      saved here.
                    </p>
                  </div>
                )}
              </div>
            </div>
          ))}
          <div ref={bottom} />
        </div>
        <div className="chat-composer">
          {current?.archived && (
            <p className="notice">
              This conversation is archived. Restore it to continue.
            </p>
          )}
          <div className="chat-sharing">
            {!!portfolios.data?.length && (
              <label className="check">
                <input
                  type="checkbox"
                  checked={sharePortfolio}
                  onChange={(e) => {
                    setSharePortfolio(e.target.checked);
                    if (!portfolioId) setPortfolioId(portfolios.data![0].id);
                  }}
                />
                Include my portfolio
                {sharePortfolio && (
                  <select
                    aria-label="Portfolio to discuss"
                    value={portfolioId || portfolios.data[0].id}
                    onChange={(e) => setPortfolioId(e.target.value)}
                  >
                    {portfolios.data.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.name}
                      </option>
                    ))}
                  </select>
                )}
              </label>
            )}
            {privateDocuments && (
              <label className="check">
                <input
                  type="checkbox"
                  checked={shareDocuments}
                  onChange={(e) => setShareDocuments(e.target.checked)}
                />
                Share attachments and prior document context with {provider}
              </label>
            )}
          </div>
          <ErrorBox error={send.error ?? profiles.error} />
          {attachmentsOpen && (
            <ChatDocuments
              api={api}
              portfolios={portfolios.data ?? []}
              documents={documents}
              onAdd={(d) => setDocuments((current) => [...current, d])}
              onRemove={(id) =>
                setDocuments(documents.filter((d) => d.import_id !== id))
              }
              disabled={running}
              selectedPortfolio={portfolioId || portfolios.data?.[0]?.id || ""}
              onPortfolio={setPortfolioId}
            />
          )}
          {documents.map((d, i) => (
            <p className="muted small" key={d.import_id}>
              {d.name} ·{" "}
              {extracts[i].data?.status === "awaiting_review"
                ? "Ready for Steve"
                : "Extracting locally…"}
              <ErrorBox error={extracts[i].error} />
            </p>
          ))}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void submit();
            }}
          >
            <textarea
              aria-label="Message Steve"
              placeholder="Ask a question. Follow the evidence."
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              rows={3}
              maxLength={8000}
              onKeyDown={(e) => {
                if (
                  e.key === "Enter" &&
                  !e.shiftKey &&
                  !e.nativeEvent.isComposing
                ) {
                  e.preventDefault();
                  void submit();
                }
              }}
            />
            <div className="composer-actions">
              <span>
                <button
                  type="button"
                  aria-label="Attach documents"
                  className="attach-button"
                  disabled={running}
                  onClick={() => setAttachmentsOpen(!attachmentsOpen)}
                >
                  <Paperclip size={18} />
                </button>
                <Check size={13} /> {approved.length} selected sources
                {turns.length ? " + previous response" : ""}
              </span>
              <button
                className="primary"
                aria-label="Send to Steve"
                disabled={
                  !ready ||
                  !draft.trim() ||
                  !evidenceReady ||
                  running ||
                  !permissionsReady ||
                  !extractionReady ||
                  !!current?.archived
                }
              >
                {running ? <Clock3 size={18} /> : <ArrowUp size={18} />}
              </button>
            </div>
          </form>
          <p className="composer-note">
            Your message shares the selected dated research, cached chart data
            and conversation with {provider}. Private attachments and portfolio
            data require the permissions above.
          </p>
          {!ready && <a href="#settings">Check Steve's connection →</a>}
        </div>
      </div>
    </section>
  );
}
function historyReplace(url: URL) {
  window.history.replaceState(null, "", url);
}
