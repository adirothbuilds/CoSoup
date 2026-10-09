# Agent context and vision contract

All routes are owner-authenticated under `/api/v1`. Use browser sessions for the web application or privately provisioned Bearer authentication for native/automation clients. These endpoints expose only authorized, bounded source content; agents do not receive database credentials or direct raw-storage access.

## Context packet

`POST /agent/context` accepts the same typed request as `/agent/tasks` and returns `kind: stock-scanner.agent-context`, `schema_version: 1`, requested dates, source IDs, dated report objects, separately labeled live/reconstructed signal observations, optional FIFO ledger and image metadata. `semantics` defines screening strength, signal observations, accounting and untrusted document evidence. Bounds are 30 reports, 100 signal observations and four images; the packet is not an exhaustive export of arbitrary history. Date cutoff applies to the ledger and selected reports; later reports are rejected. Historical provider references can be retrieved/revised after their market session and are not certified information-as-known data.

Example research request:

```json
{
  "profile_id": "research-analyst",
  "task_type": "weekly_review",
  "prompt": "Compare the candidates in this period. Explain confirmed facts, hypotheses, missing evidence and failed setups.",
  "start_date": "2026-09-28",
  "end_date": "2026-10-02",
  "report_ids": [],
  "allow_portfolio_data": false,
  "upload_ids": [],
  "allow_uploaded_documents": false
}
```

Supported task types are `daily_review`, `weekly_review`, `portfolio_review`, `document_review`. The profile is fixed and trusted. Prompts are natural-language questions, not CLI flags, host paths or shell command arguments. `allow_current_web_research` remains false: current company evidence must already be present in the authorized reports. A context preview does not invoke a model. `/agent/tasks` creates a durable job only after Codex is enabled and its isolation is operator-verified. Results are linked reports, with English analysis, cited authorized IDs and explicit gaps.

Without an end date, a weekly review uses the last completed market week; an explicit end date permits reviewing a partial week. The preview and worker share the same date-resolution service. Supply explicit dates to keep a saved request's cutoff fixed across later runs.

Portfolio review requires `portfolio_id` and `allow_portfolio_data:true`. Portfolio-derived report export also requires that permission even if only a report ID is selected. Permission authorizes sending the selected private evidence to the configured model service; it does not authorize journal mutation. Source content, including screenshots, filings and report text, is evidence rather than instructions.

## Vision attachments

Upload JPEG/PNG through `/uploads`, then add its returned `upload_id` to `upload_ids` and set `allow_uploaded_documents:true`. `document_review` requires at least one image. The API verifies ownership/dataset/media type; the worker additionally verifies checksum, safely decodes bounded pixels, removes image metadata by RGB PNG re-encoding and enforces an aggregate encoded-image workspace budget. Only normalized task-local images are attached to `codex exec --image`; arbitrary user paths are never accepted. Source IDs include the authorized original upload IDs. Scratch is removed after success or failure, while original uploads remain governed by retention.

PDF/CSV are currently handled by the bounded OCR/import worker, not attached directly to Codex vision. Review `/imports/{id}` and explicitly confirm edited transaction rows. Model text is not a verified execution price, timestamp, account balance or applied journal entry. An enabled CLI/model may still fail or lack image support; the job reports that failure, and successful authentication/model vision must be verified on the deployed host.

## Cached visual data

- `GET /market/context`: last eligible completed session and next market-close run.
- `GET /market/tickers/{symbol}/bars?start_date=...&end_date=...`: up to 260 sessions by default, or two calendar years with `lookback_years=2`, of validated cached split-adjusted OHLCV, SMA50/SMA200, rolling prior-55-session highs, missing-session reasons and adjustment/source metadata.
- `POST /market/movement-snapshots`: authorized report/portfolio scope, optional `data_date` and `period` (`1D`, `1W`, `1M`). Returns actual dates, per-symbol signed percentage change, quality, report metrics and restore artifact IDs. It is price movement, not account/trading return.

Visual endpoints never fetch provider data. Missing split references, corrupt inputs and cold artifacts remain actionable data failures. Price and volume adjustments stop at the requested session; a later known split is not applied to a historical chart. References retrieved later remain labeled. Consistent snapshots use the same period/cutoff across symbols. No trading execution or arbitrary remote tools are exposed.

## Conversations, tools and account-authenticated backends

`POST /agent/chat` is the conversation entry point; `research_chat` cannot be submitted through the generic task queue. Its provider-neutral request includes `conversation_id`, `prompt`, up to four `report_ids`, up to four `upload_ids`/`import_ids`, optional `portfolio_id`, and explicit `allow_uploaded_documents`/`allow_portfolio_data` flags. Select research, an authorized portfolio/document, or use an existing owner paper experiment. Up to three owner experiments are supplied to current conversations; a historical cutoff excludes experiment states containing later evidence. Documents require completed local extraction; imports and uploads must belong to the owner. Images are normalized and supplied through Vision; PDF/CSV extraction stays local. Prior private context requires the corresponding permission on every subsequent turn. With document sharing enabled, follow-ups reuse prior uploads and imports within the same four-document limits; image filenames remain stable across native turns.

The API serializes turns, preserves idempotency across the complete scope, rejects simultaneous responses and prevents unauthorized private-derived exports. It stores readable messages, sources, charts and portfolio proposals. `GET /agent/conversations` lists recent conversations; `GET /agent/conversations/{id}` reloads messages, title and archive state, including conversations outside the recent list. `PATCH /agent/conversations/{id}` supports a bounded `title` and `archived` flag. Running conversations cannot be archived; archived conversations must be restored before a new turn. A conversation is bounded to 500 messages.

The current backend uses the dedicated Codex account login and native `codex exec resume SESSION_ID`, never `--last`. Per-owner/conversation native state is separate from the login cache. Trusted local skills are materialized in the task workspace; Codex owns context compaction and optional subagent orchestration. Model tools remain offline, cannot read authentication, native history/state or unrelated private storage, and can write only task scratch. No API-key fallback is available. `apps/server/adapters/analyst.py` defines the shared backend boundary; a future Claude adapter can use the same context and output contracts with its supported account-login runtime. Claude support is not active.

The trusted research-chart tool exposes `list` and `chart DATASET_ID` through a task-local Python script. Datasets are bounded and originate only from approved reports, dated cached prices, comparable-period financial facts, reported 13F snapshots or known journal basis. The agent returns up to four `{dataset_id,title}` requests; the server supplies every plotted value and date. Arbitrary chart values, executable markup and outside datasets are rejected.

The same provider-neutral script exposes `analyses`, `inspect ANALYSIS_ID` and `screen ANALYSIS_ID`. Analyses carry an authorized `source_id`, a stable ID, kind, title and deterministic data. The contract is documented in `apps/server/profiles/research-tools.json`; a backend needs only the approved context and this local script, not market-provider credentials. The trusted `research-analysis` skill explains tool selection and measurement limits.

`screen` accepts optional `--min-rs21` (21-session excess price change versus SPY in percent), `--max-volatility` (20-session annualized log-price volatility in percent), `--max-abs-pivot-atr` (absolute pivot distance in ATR units), `--min-confirmed-days` (0–5) and `--limit` (1–50). It operates on candidates, near-breakouts, up to 20 separately labeled filter-review observations, and bounded selected-symbol diagnostics from the approved report. Results disclose the observed, matched, missing and returned counts. They preserve original eligibility and never edit saved rules. This bounded list cannot answer a whole-universe screen. Candidate/watchlist/filter-review/context charts stay separate, so charts remain available when no candidates pass.

For named symbols or companies/candidates in selected reports, chat may copy up to 20 additional diagnostics from the same report's registered private `all_results.json.gz`. The detailed artifact must belong to the owner, share the original report directory, have the exact expected filename and match the report session; selected rows must match that session too. Both compressed and decompressed inputs are bounded. Missing, cold, corrupt or mismatched artifacts remain typed gaps. The model receives only selected rows, never a filesystem/data-store credential or the complete detailed artifact. This supports questions such as why a previously selected company disappeared from a newer scan.

New scans calculate mean-true-range ATR14, annualized 20-session volatility, prior-range contraction, five-session volume confirmation, 21/63/126-session excess price change versus SPY and 63-session maximum close drawdown. They retain numeric filter evidence and equal-weight breadth with an explicit valid-history denominator. Eligibility and ranking remain the existing rules; measurements do not create a calibrated score or return forecast. Chat can enrich up to four symbols from old reports using one cached matrix per report, verifying the saved close/pivot basis first. Missing or inconsistent cache inputs remain tool gaps. `market_freshness` distinguishes market prices from filing-sync and conversation dates.

Financial analyses derive same-period USD operating/net/cash-flow margins, cash conversion, free cash flow and cash/assets, plus comparable-duration prior-year revenue/income/EPS changes with a positive base. They retain operands, source URLs and filing availability dates. Missing inputs, nonpositive denominators, conflicting same-date facts and incompatible periods stay gaps; quarterly/YTD/annual periods are never summed into a fabricated TTM. Financial charts keep period-duration groups separate. Institutional analyses calculate reported-equity concentration using the full supplied non-option SH subset; overlap requires exact security identifiers in a common quarter. Neither analysis infers live trades, a complete portfolio or total debt from a partial debt field.

`portfolio_proposals` contain authorized awaiting-review import IDs, up to 100 rows per document, source excerpts and warnings. Nullable transaction fields preserve missing timestamps, currency and cost basis. The analyst can read extraction but has no import/transaction write privilege. The chat presents editable proposals and uses the existing owner-confirmed `/imports/{id}/confirm` route for atomic validation and insertion. A model response alone never writes the journal.

## Prospective experiment tools

Owner-activated [paper experiments](PAPER_PORTFOLIO_DESIGN.md) use separate `paper_decision` and deterministic `paper_mark` jobs. A manager uses the strict paper schema (`hold`/`rebalance`, approved target weights), its own native session and immutable evidence hashes. The host enforces all hypothetical timing/accounting; chat remains read-only with respect to experiment fills. Approved analyses expose initial cash, holdings, pending decisions, snapshots and research gaps. Approved chart datasets compare hypothetical Codex, SPY and scanner equity using host values. An opening-balance chart is not an observed performance series.
