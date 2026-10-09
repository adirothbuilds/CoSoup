# Validation appendix: conversational research and SEC sources on Mac

Validated on 2026-10-08 in the existing local development deployment. This appendix records observed results and limitations; synthetic examples are not current financial evidence.

## Delivered behavior

- Home centers the Steve conversation. Source selection, conversation history and background reports use disclosures; research opens in the list view. Reports render readable Markdown, safe source links, tables and downloads, while raw structured data remains collapsed.
- Conversations persist messages and support new sessions, titles, archive and restore. Follow-ups use an explicit native Codex session ID, scoped to the owner and conversation, with bounded context and idempotent submission. Prior document and portfolio context requires its sharing permission on every turn.
- The backend uses the preserved dedicated ChatGPT account login. There is no API-key fallback. A shared adapter boundary defines context, capabilities and outputs for a future account-authenticated Claude backend; Claude is not connected.
- Trusted task-local skills and an offline chart tool expose only approved, dated datasets. The server validates chart requests and supplies plotted values. Codex retains native context and optional subagent orchestration; this validation does not separately establish that a native subagent ran.
- Chat accepts screenshots and documents through the existing upload/extraction flow. Images are normalized for Vision, and PDF/CSV extraction stays local. Portfolio proposals preserve missing values, remain editable and require explicit owner review before the existing atomic import-confirmation route writes journal entries. The analyst has read-only access to extraction records and no journal write privilege.
- SEC research supports bounded filings, cached filing excerpts, comparable-period financial facts and selected institutional 13F snapshots with dates and coverage limitations. Reported holdings are not presented as live trades.

## Automated and browser validation

The isolated ARM64 test container contained current source, synthetic fixtures and no deployment data, login or network. The temporary filesystem allowed execution of test scripts and adequate storage reservations. An earlier restricted runner failed because it prohibited fixture execution, lacked reservation space and carried stale source files; after correcting that runner, both required suites passed:

- `.venv/bin/python -m unittest discover -s tests -v`: 76 tests passed.
- `.venv/bin/python -m unittest discover -s apps/server/tests -v`: 76 tests passed.
- Shared Vitest suite: 10 tests passed.
- Web TypeScript check and production build passed.
- Final deployed Chromium browser checks: 10 tests passed across desktop and mobile layouts, covering appearance, cached research charts, conversation attachments, explicit sharing and reviewed portfolio proposals. Chat/import writes in these browser tests were intercepted synthetic fixtures, not real journal changes or additional model calls.

Read-only inspection of the real saved answer confirmed reload, original market date and source attribution, JSON/Markdown downloads, navigation, no horizontal overflow or browser runtime errors, and no private data in localStorage. Final cached Research re-entry took approximately 36–37 ms. Earlier first-load measurements were approximately 6.5 seconds; final initial navigation reused the server cache, so it is not a new cold-load benchmark. Mobile web was checked in Chromium; native mobile and WebKit were not validated.

A browser-only SEC fixture rendered financial and holdings charts, retained a filing excerpt as plain text, and did not execute embedded HTML. It was not persisted to the server.

An actual authorized review of the previously selected market report completed and is visible in the app. A separate two-turn account-backed smoke used only invented synthetic chart data and a synthetic holdings screenshot: it produced validated chart/document proposals, retained unknown cost and timestamp, saved the native session and resumed with the prior marker intact. Its scratch was removed. Synthetic model success is not validation of real portfolio extraction.

## Isolation and preservation

Before further agent use, the deployed worker passed all 14 native-session sandbox checks without a model call. Tools could read intended inputs and write task output. They could not open authentication, session history/state, private canaries, deployment secrets, other tasks or process environment; writes outside task scratch were denied. Credential probes only opened and closed file handles and never read credential contents. Probe scratch was removed.

The dedicated profile reported `Logged in using ChatGPT`. Hashes of the master `.env`, generated server configuration and dedicated authentication file matched their earlier baseline. All 278 checked pre-existing market files retained their size and modification time, and all original reports remained present. The shared request ledger was intentionally updated by the SEC attempt and was excluded from the market preservation comparison.

API, web and Codex worker updates were deployed locally as ARM64 images. The generated Compose platform setting was adjusted for the native API image; this does not mean every generated deployment file remained byte-identical. PostgreSQL and the existing scheduler/import/storage services stayed running, as did unrelated local workloads. Docker Desktop and PostgreSQL were not restarted or reset. No commit or push was performed.

## Current real-data limits

The authorized SEC synchronization stopped on its first request: `https://www.sec.gov/files/company_tickers.json` returned HTTP 403. The failed job persisted a diagnostic report and the UI explains the source-access problem. No new company facts, filing documents or institutional holdings were obtained. No retries, host changes, TLS bypass or paid upgrades were used. Successful synthetic SEC tests do not remove this live access failure.

The persistent scheduler service is running, but no daily schedules are enabled. The delivered conversation is separate from deterministic ingestion and screening; a running scheduler process is not proof of active daily synchronization.

## Runtime references

Native execution/resume, local skill discovery and optional subagents follow official Codex documentation: [non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode), [skills](https://learn.chatgpt.com/docs/build-skills), and [subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents). Private reports, account values and task identifiers remain outside this public appendix.
