# CoSoup home research server

An experimental FastAPI application for a private Debian home server. Docker Compose runs the API, PostgreSQL, scheduler and independent scanner, import and storage workers. An optional dedicated Codex worker analyzes authorized report copies. The standalone scanner remains available.

For a deployment generated from one private env file, use the [OS-aware setup command](../../docs/SETUP.md). The installation steps below describe the advanced manual configuration path; setup-managed JSON/secret files are generated from their master env.

All reports, API responses, code and documentation are English. There is no brokerage connection or order execution. The first release has one authenticated owner; private records carry owner IDs for future authentication adapters. It does not provide multiple-user login or separate owner-token scopes yet.

The [React web workspace](../web/README.md) and [Expo iOS client](../mobile/README.md) use this API through shared transport/domain contracts. Root `make help` lists combined build/deployment operations. Browser sessions require a privately configured trusted HTTPS origin; native/automation requests retain Bearer authentication. Cached visual endpoints and the versioned context/vision contract are documented in [Agent API](../../docs/AGENT_API.md).

## Install and start

Requirements: x86_64 Debian, Docker Engine with Compose v2, a correct host clock/NTP, and persistent private storage. Default service limits fit within 32 GB RAM; CPU/memory, polling, scheduling and storage settings can be changed. Docker/OS images need additional space beyond application data.

Use a non-root deployment account. Run from the repository root. Choose a deployment directory outside the checkout; this example uses `/srv/stock-scanner`. Create it as an administrator, owned by the account that will run Compose, with mode `0700`.

```sh
docker build --target base -f apps/server/deploy/Dockerfile -t stock-scanner-server:local .

docker run --rm --user "$(id -u):$(id -g)" \
  --mount type=bind,src=/srv/stock-scanner,dst=/private \
  stock-scanner-server:local init --root /private \
  --host-root /srv/stock-scanner --timezone Asia/Jerusalem

docker compose --env-file /srv/stock-scanner/compose.env \
  -f apps/server/deploy/compose.yaml up -d postgres
docker compose --env-file /srv/stock-scanner/compose.env \
  -f apps/server/deploy/compose.yaml run --rm migrate
docker compose --env-file /srv/stock-scanner/compose.env \
  -f apps/server/deploy/compose.yaml up -d \
  api scheduler scanner-worker import-worker storage-worker
```

`init` generates role passwords, an API token and a binary 32-byte archive key, and preserves existing files. Massive/R2 credential files start empty. Configure private `config/server.json` before starting workflows; use [config.example.json](config.example.json) as the field reference. Never copy real secrets into that public example. The container paths in configuration remain `/var/lib/stock-scanner` and `/run/secrets/...`; `compose.env` describes host mounts and UID/GID.

The default API bind is `127.0.0.1:8080`. Set `BIND_ADDRESS` to a specific LAN/VPN interface only when required, with a host firewall; keep PostgreSQL unexposed. Use TLS through a privately configured reverse proxy for access across the LAN/VPN. Tokens grant full owner access; do not send them over an untrusted connection. Docker does not configure the host firewall.

`GET /api/v1/health/live` and `/api/v1/health/ready` are minimal unauthenticated probes. Other endpoints require `Authorization: Bearer <private token>`. Authenticated Swagger is at `/api/v1/docs`; browser Basic authentication uses username `owner` and the API token as password. OpenAPI is `/api/v1/openapi.json`. Keep client credentials in a protected file or credential manager rather than shell history.

Compose bounds each container's RAM/CPU, drops capabilities, uses read-only root filesystems and rotates local-driver logs at 3 x 10 MB per container. Change resource variables in private `compose.env`, for example `SCANNER_MEMORY`, `SCANNER_CPUS`, `API_WORKERS`, `SERVER_PORT`. Changes require service recreation. Neither the Docker socket nor a host home directory is mounted.

## Private configuration and credentials

| File or setting | Purpose |
| --- | --- |
| `secrets/massive_api_key` | Authorized home-server Massive key, used only against HTTPS `api.massive.com`; never provision it by copying a proxy placeholder |
| `secrets/api_token` | Generated owner authentication token; changing it requires API restart |
| `secrets/*_database_password` | Separate admin/API/worker database roles; only migrations receive the admin credential |
| `secrets/archive_key` | Raw 32-byte encryption key; keep an independent offline recovery copy |
| `secrets/r2_access_key`, `secrets/r2_secret_key` | Bucket-scoped R2 access; leave blank until configured |
| `r2_endpoint`, `r2_bucket`, `r2_prefix` | Private R2 S3 account endpoint/bucket/prefix; no public bucket or URLs |
| `data/codex-profile/` | Dedicated Codex authentication/configuration; never mount the operator's `~/.codex` |

Private host directories should be `0700`, secret files `0600`. Protect configuration too. Secret contents are never returned by the API. Worker wrappers receive only their role/provider credentials; import/model child processes do not receive wrapper database credentials. Image inputs and runtime mounts exclude raw data, personal addresses and credentials.

## Scan dates, jobs and reports

Use `POST /api/v1/scan-plans` before a long request. It returns requested trading sessions, skipped nontrading dates, the union of preceding 260-session windows, hot/cold/missing inputs and a grouped-request estimate. Reference pagination and research can add requests. A five-date historical range normally needs 264 market sessions, not five independent downloads of 260 days.

Latest-session scan body:

```json
{"mode":"live","research":"current","offline":false}
```

Inclusive historical range body:

```json
{
  "mode":"historical_snapshot",
  "start_date":"2026-09-28",
  "end_date":"2026-10-02",
  "acquisition":"missing_only",
  "research":"none",
  "offline":false
}
```

Submit to `/api/v1/scans`, optionally with an `Idempotency-Key`. Identical replay returns the existing job; changed input under the same key returns `409`. Operations return `202` with a job/status/events URL. Poll `/api/v1/jobs/{id}` and inspect `progress`, `error` and report quality separately. A succeeded calculation can produce `partial_coverage`. Blocked source access produces a failed job and its diagnostic report; candidate counts are never forced.

Historical research can use `as_of_only`; it gets a date-specific cache and news cutoff. Upcoming earnings knowledge is omitted. Provider financial records are not certified point-in-time data: reports expose that limitation. Reconstructed signals remain separate from live observations and are not a strategy backtest or trading returns.

`offline:true` requires the exact dated cache, including listing/split references, and `research:"none"`. The API rejects offline company-research requests instead of silently skipping sources. Daily reports include `research_run` with requested/state/checked symbols/limit; report-list summaries also retain this state and the UTC run timestamp. Existing reports without those fields remain readable. Online acquisition downloads missing days only under the persistent five-request-per-minute limit and stops on provider errors. Initial ingestion can take more than an hour. Cold inputs cause `waiting_for_archive` with artifact IDs: submit a restore job, then explicitly resume the original job. Correct the cause before resuming any failure; repeated entitlement probes are not automatic.

Get JSON/Markdown with `/api/v1/reports/{id}/content?format=json` or `format=markdown`. Metadata lists date, mode, quality and artifact IDs. `POST /api/v1/weekly-summaries` accepts `end_date` and `mode`; missing daily reports are declared. Live and reconstructed signal histories are not mixed. Missing earlier observations cannot be invented from a new deployment; standalone signal history is not automatically migrated.

## Durable scheduling and logs

The separate scheduler reads the **host system clock** and persists schedules/occurrences in PostgreSQL. Set `timezone` to the host's intended IANA zone; timestamps are stored in UTC. Market-close triggers use the NY exchange calendar with holidays, early closes and configurable settlement minutes. The default `market_data_ready_time: "01:00"` additionally delays acquisition until 01:00 New York time on the following calendar day, because end-of-day entitlement can reject the same-day grouped endpoint after the exchange closes. This is a conservative operator policy, not a provider publication guarantee. Set it to `null` only for a verified provider entitlement that permits post-close same-day acquisition. The scan plan and worker enforce the same availability boundary; exact source errors still stop execution without automatic retries. Local cron triggers use their explicit zone or the server default.

`GET /market/context` separates the latest completed exchange session from the latest provider-ready session, and returns the next acquisition window and its exchange-close timestamp. A Friday session becomes ready on Saturday morning, including after an early close; the following scan waits for Monday's session to become ready on Tuesday. Editing an existing schedule recalculates its persisted next occurrence under the current policy.

Prepare **disabled** daily, weekly, monthly-archive and nightly-backup examples:

```sh
docker compose --env-file /srv/stock-scanner/compose.env \
  -f apps/server/deploy/compose.yaml run --rm migrate seed-schedules
```

Enable selected schedules through `PATCH /api/v1/schedules/{id}` after provisioning their dependencies. Or create a local-clock schedule:

```json
{
  "name":"Evening research",
  "trigger":{"type":"local_cron","expression":"30 23 * * 1-5","timezone":"Asia/Jerusalem"},
  "task":{"type":"daily_scan","research":"current"},
  "missed_run_policy":"run_once",
  "enabled":true
}
```

Supported triggers: `local_cron`, `market_close` (daily/weekly), and `once` with a timezone-aware `at`. Task types: `daily_scan`, `weekly_summary`, `archive_completed_months`, `database_backup`, `agent_task`. `skip` records a late missed occurrence; `run_once` runs the newest eligible work once. Daily `catch_up` converts downtime into a bounded historical date range. Very long downtime can exceed `max_range_sessions`; resolve that explicitly with smaller ranges or adjusted limits.

Nonexistent DST wall times are skipped with an event; repeated local times execute once. Occurrence uniqueness and job idempotency protect restart/clock-change replay. Job leases recover lost workers with checkpoints, up to the configured attempt limit; provider errors require explicit resume. This is at-least-once processing, not exactly-once external effects.

Job logs: `/jobs/{id}/events` and `/events/stream` (SSE with event IDs). Schedule history: `/schedules/{id}/occurrences`. Container diagnostics: `docker compose ... logs --tail 100 scheduler scanner-worker`. Raw credentials, document contents and full model tool events are excluded from structured progress. Defaults keep searchable events for 90 days; storage batches archive older events before removing database rows. Docker stdout rotation is bounded diagnostics and does not preserve every historical stdout line.

## Storage, retention and R2

Defaults are decimal bytes: capacity 200 GB, target 140 GB, pressure trigger 160 GB, admission stop 180 GB; all are configurable. `PATCH /api/v1/storage/policy` changes validated retention/limits at runtime. Other settings use private JSON and service restart. Raising the upload ceiling requires updating JSON and restarting the API before changing runtime policy.

**Provision a dedicated filesystem or enforced host quota before relying on 200 GB as a hard ceiling.** Application reservations do not replace filesystem enforcement. Set `storage_usage_mode:"filesystem"` only on a dedicated application-data filesystem: this counts PostgreSQL/WAL and directories masked from individual containers. The default `tree` mode is a development counter and can undercount masked PostgreSQL data. Reserve OS/image/Docker-log capacity separately and account for it when setting the application's available budget. Admission checks include allocated usage, free bytes and outstanding reservations.

Archiving and local eviction are separate. Defaults: 31-day artifact age, 300 recent market sessions kept hot, 7-day restored-file protection, 256 MB shards; uploads become backup-eligible after one day. The monthly cron runs a batch of eligible artifacts; pressure batching can be enabled with `automatic_archives:true`. Monthly batching does not back up fresh uploads daily unless a daily archive schedule is also enabled. `archive_evict:false` preserves local originals until the operator enables verified eviction. Active readers hold a shared file lock, preventing eviction during scans/imports/model work or report reads.

Packages preserve original bytes in `tar.zst`, grouped by dataset and owner. They include a versioned manifest, then use the documented `SSR1` AES-256-GCM envelope (authenticated 32-byte header, random 12-byte nonce, ciphertext and 16-byte tag). They are **not age files**. The storage worker uploads to private R2 and streams a full remote SHA-256/length verification. Only a verified object plus committed catalog permits eviction. Failures retain originals; recent market windows and restored TTLs remain protected. Hash mismatch/authentication/traversal/size failures prevent restore publication.

`POST /storage/archive-jobs` starts a batch. `POST /storage/restore-jobs` accepts `artifact_ids`, never arbitrary paths or remote keys. Cold report access returns `restore_required`; it does not download unbounded data during the HTTP request. R2 configuration is required for both operations. Application "cold" means infrequently used private data on R2 Standard, not a provider archival tier. Review source terms and R2 charges before activation; MIT grants no market-data redistribution rights. No remote lifecycle deletion or subscription upgrade is configured.

Nightly `database_backup` uses consistent PostgreSQL 17 `pg_dump -Fc`, immediately archives/encrypts/uploads the dump, and requires R2. It is separate from monthly data archiving. Keep private configuration and encryption-key recovery copies separately. A nightly backup has up to a 24-hour metadata/journal loss window; monthly archives alone do not ensure no loss of fresh unique uploads. See [recovery operations](RECOVERY.md), and perform a fresh-instance restore drill before enabling eviction.

## Portfolio journal and reviewed imports

Create a USD portfolio, then journal purchases/sales/opening holdings, deposits, withdrawals, dividends, fees and splits. Timestamps must include a timezone, values use Decimal, and `external_ref` deduplicates actual transactions. Manual requests without an external reference can create duplicates; supply stable references. A split's `quantity` is its ratio (2 for 2-for-1). Corrections supersede the original record and revalidate the effective history; overselling is rejected atomically. Opening holdings without basis remain unknown.

Positions use supplied history and FIFO. As-of analysis ends at the actual market close and uses unadjusted same-date prices. Bad/missing prices or known splits absent from the journal exclude affected valuations. Cached split checks do not establish complete corporate-action history or broker reconciliation. Missing opening cash/basis is explicit; no tax, FX, account-performance or trading-return certification is provided.

Upload CSV, PNG/JPEG or PDF to `/uploads`, then submit `/imports` with `upload_id` and `portfolio_id`. File size/signature, image pixels, PDF pages, child CPU/time/output limits are bounded. CSV yields validated proposals; image/PDF OCR yields source text, available word confidence, and conservative candidate rows. Ambiguous fields stay unresolved. Nothing enters the journal automatically: inspect `/imports/{id}`, then explicitly submit edited `rows` to `/confirm`, or `/reject`. Confirmation is atomic and idempotent, with document/row provenance.

## Optional Codex terminal worker

For the one-env installer, follow [Connect Steve with ChatGPT](../../docs/SETUP.md#connect-steve-with-chatgpt). The setup overlay builds this worker natively on Apple Silicon and keeps core server/PostgreSQL services on their existing platform. Rerun setup after upgrading an older deployment so its generated `compose.env` includes the native worker platform. Changing only Docker's requested platform does not rebuild an existing amd64 image.

Build the dedicated image with `docker compose ... --profile codex build codex-worker`. It contains the pinned official Codex terminal CLI, a dedicated analyst profile and a typed asynchronous API; it does not inherit the host's login/configuration. Provision authentication privately into `data/codex-profile` using the official CLI login workflow. API tasks are `daily_review`, `weekly_review` and `portfolio_review`; API payloads do not accept shell commands, CLI flags, host paths or arbitrary profiles as execution parameters. Portfolio export requires `allow_portfolio_data:true` and an explicit authorized portfolio.

The wrapper copies authorized reports into a per-job workspace, runs headless terminal `codex exec`, validates structured output/source IDs and removes scratch. Current web research is disabled in this adapter. Missing sources are reported; model output cannot directly modify the journal, scheduler or repo. The model service receives authorized input contents, which can include portfolio data only with the explicit flag.

Codex is disabled by default. Set `codex_enabled:true` and `codex_sandbox_verified:true` **only after** verifying authentication, model access and filesystem/tool isolation on the host. The outer Bubblewrap namespace exposes system runtime, the task workspace and only the dedicated `auth.json`, mounted read-only into an ephemeral CLI home. It retains Docker's masked procfs for namespace setup. The official CLI uses a trusted `steve` permissions profile: tools can read runtime/task files, write regular files only under `/work`, and cannot read authentication or procfs. Tool networking, web search, apps, plugins, delegation and approval escalation are disabled. The CLI harness can still authenticate and contact the model service. The legacy `workspace-write` preset does not establish credential secrecy.

Verify denied reads of `/run/secrets`, host files, other tasks and the dedicated auth file, plus denied writes outside the task. Run `tools/validate_steve_sandbox.py` inside the built worker under its actual Compose security settings for synthetic checks; `--real-auth` tests whether tools can open dedicated authentication without reading its contents. These checks do not replace a bounded authenticated model/tool request. Some Docker/kernel policies block Bubblewrap or nested CLI sandboxing. Do not bypass sandboxing, run privileged or mount the Docker socket to make it work. An unenforceable sandbox leaves the feature disabled and requires an alternative operator-managed isolated runtime adapter.

Start it only after those checks: `docker compose ... --profile codex up -d codex-worker`. The trusted analyst profile pins `medium` reasoning. Select the model with `CODEX_MODEL` in the private master env and rerender configuration before restarting the analyst worker. Dedicated terminal access is optional for operator login/diagnostics; keep it separate from untrusted task execution. No model call, paid subscription or authentication is established by building an image.

## API map and extension points

All paths below have prefix `/api/v1`; authenticated OpenAPI provides exact payloads.

| Endpoints | Use |
| --- | --- |
| `GET /system/status`, `GET/PATCH /me`, `GET/POST /rules` | Status, owner preferences, immutable screening presets |
| `GET /market/coverage`, `POST /scan-plans`, `POST /scans`, `POST /weekly-summaries`, `GET /signals` | Date coverage, missing-only acquisition, analysis and signal history |
| `POST /research/sec-sync` | Owner-scoped public SEC research job; symbols/report and selected manager CIKs; no market refresh or model request |
| `POST /agent/chat`, `GET /agent/conversations`, `GET /agent/conversations/{id}` | Source-scoped Codex conversation turns, saved responses and bounded recent history |
| `GET /jobs`, `GET /jobs/{id}`, `POST /jobs/{id}/cancel`, `POST /jobs/{id}/resume` | Durable progress, cooperative cancellation and explicit recovery |
| `GET /jobs/{id}/events`, `GET /jobs/{id}/events/stream` | Persisted events and SSE |
| `GET /reports`, `GET /reports/{id}`, `GET /reports/{id}/content` | Report metadata and authorized JSON/Markdown |
| `GET/POST /schedules`, `PATCH /schedules/{id}`, `POST /schedules/{id}/run-now`, `GET /schedules/{id}/occurrences` | Scheduling and occurrence history |
| `GET /storage/status`, `PATCH /storage/policy`, `GET /storage/archives`, `GET /storage/artifacts`, `POST /storage/archive-jobs`, `POST /storage/restore-jobs` | Retention, admission, archive catalog and bounded restore |
| `GET/POST /portfolios`, `GET/POST /portfolios/{id}/transactions`, `POST /portfolios/{id}/transactions/{tx}/corrections` | Actual journal and corrections |
| `GET /portfolios/{id}/positions`, `POST /portfolios/{id}/analysis-jobs` | Supplied holdings/FIFO and closing-date analysis |
| `POST /uploads`, `POST /imports`, `GET /imports/{id}`, `POST /imports/{id}/confirm`, `POST /imports/{id}/reject` | Upload extraction, review and journal confirmation |
| `GET /agent/profiles`, `POST /agent/tasks`, `GET /agent/tasks/{id}`, `POST /agent/tasks/{id}/cancel` | Optional typed Codex analysis |

`adapters/contracts.py` defines scanner, extractor, object-store and analyst protocols. Each worker has its own folder/entrypoint. Database migrations are explicit; future schema versions require a migration, not a silent runtime upgrade. SQLite is a test adapter; deployment uses PostgreSQL row locks/leases.

SMTP delivery is retained in the standalone CLI and remains privately configured/disabled. This server does not yet include a report-delivery worker or delivery schedule dependency; adding that adapter is required for server-driven mail. It must use private recipient/SMTP credentials and deduplicate deliveries.

See [architecture](../../docs/SERVER_PLAN.md) and [validation methods and appendix](../../docs/VALIDATION.md). Tests and prepared adapters do not establish live R2, Codex, mail or uninterrupted home-host operation.
