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
- `GET /market/tickers/{symbol}/bars?start_date=...&end_date=...`: up to 260 sessions of validated cached split-adjusted OHLCV, SMA50/SMA200, rolling prior-55-session highs, missing-session reasons and adjustment/source metadata.
- `POST /market/movement-snapshots`: authorized report/portfolio scope, optional `data_date` and `period` (`1D`, `1W`, `1M`). Returns actual dates, per-symbol signed percentage change, quality, report metrics and restore artifact IDs. It is price movement, not account/trading return.

Visual endpoints never fetch provider data. Missing split references, corrupt inputs and cold artifacts remain actionable data failures. Price and volume adjustments stop at the requested session; a later known split is not applied to a historical chart. References retrieved later remain labeled. Consistent snapshots use the same period/cutoff across symbols. No trading execution or arbitrary remote tools are exposed.
