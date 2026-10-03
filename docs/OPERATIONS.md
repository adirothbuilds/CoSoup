# Private operations and scheduling

This is personal research software. It does not connect to a broker, execute orders or upgrade a provider subscription.

## Current cloud environment

The checkout is `/workspace/stock-scanner`. Use the existing checkout: cloud tasks are already isolated, and a Git worktree is unnecessary unless explicitly requested.

```sh
cd /workspace/stock-scanner
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m unittest discover -v
.venv/bin/python scanner.py preflight
.venv/bin/python scanner.py ingest
.venv/bin/python scanner.py daily
.venv/bin/python scanner.py weekly
.venv/bin/python scanner.py schedule-plan
```

`MASSIVE_API_KEY` is supplied by the existing Network secret scoped to `api.massive.com`. Do not copy its value into code, files or command arguments. Proxy secret values may be placeholders: do not extract credentials or assume they are usable as raw credentials elsewhere.

Private state defaults to `/workspace/stock-scanner-state`, or an external `SCANNER_STATE_DIR`. It contains compressed raw market snapshots, listings, splits, reports, source-research caches and `signals.sqlite3`. Keep it on protected persistent storage. Do not attach it to Git, public artifacts, outgoing email or open backups.

```sh
.venv/bin/python scanner.py daily --offline
```

Offline mode requires the exact snapshots and does not perform current-source company research. A missing required file is a blocked run.

Global `--config /path/to/private-rules.json` and `--state-dir /path/to/private-state` options precede the command. `--as-of` requires a timezone-qualified timestamp; default runs use the real clock. Historical dated snapshots are not survivorship-free backtests.

## Ingestion, errors and resuming

The initial load fetches 260 market sessions, one request per whole-market day rather than per ticker. All provider processes share a persistent lock and ledger: at least 13 seconds between requests and at most five requests in a rolling 60-second window. Pagination, reference metadata, split history and company research use that same limit. Initial loading can take over one hour. Subsequent runs fetch only missing days.

There are no automatic retries. HTTP 429 also persists a cooldown. Read the exact failure first. After fixing access or connectivity, `ingest` or `daily` resumes from valid cached sessions. Do not delete caches or cooldowns to evade a provider restriction. Corrupted caches are detected and replaced atomically in a new explicit run. TLS and artifact verification stay enabled.

Statuses:

- `complete`: the selected listing universe was evaluated, all market days and both benchmarks are valid; insufficient-history exclusions remain documented.
- `partial_coverage`: unexpected stock-level data errors occurred below the blocking threshold. Passing candidates are individually verified; coverage is incomplete.
- `blocked_*`: data, access or quality prevented a valid result. No conclusion about opportunity availability is justified.
- Research can be incomplete even when technical screening succeeds. Facts, hypotheses and gaps are distinct.

Blocked commands return exit code 2. Partial coverage returns 0 but consumers must inspect `status` and `errors`. `preflight` separately checks grouped daily, complete SPY/IWM history, split access and listings. Successful access does not identify a subscription name or guarantee future entitlements. No subscription change is performed.

## Durable scheduling and delivery

No cron or service is installed in this temporary development environment. Live processes must not be assumed to survive future tasks.

Templates in `deploy/` target a **durable** Linux systemd host with persistent storage. They are prepared only, not installed or activated. The operator must create the `scanner` account, deploy to `/opt/stock-scanner`, prepare its `.venv`, and manage a private `/etc/stock-scanner/private.env` file with mode 0600. Adapt paths and the account before activation. The service restricts writes to its private state directory.

The timer checks `scheduled` every 15 minutes after the prior run finishes. Application logic gates execution on the XNYS calendar and America/New_York close plus 30 minutes, including early closes, holidays and DST. Weekly output is generated on the last trading session of the week, including Thursday when Friday is a holiday. Host timezone does not determine the market session. An initial deployment cannot invent a full week of observations.

Configure these names securely on the durable host; never put personal values in public Git:

| Variable | Purpose |
|---|---|
| `MASSIVE_API_KEY` | Authorized provider access; a Network secret already exists in this cloud |
| `SCANNER_STATE_DIR` | Protected persistent state outside the checkout |
| `SCANNER_REPORT_TO` | The requested private recipient address |
| `SMTP_FROM` | Authorized sender address |
| `SMTP_HOST` / `SMTP_PORT` | SMTP server and verified TLS port 465 or 587 |
| `SMTP_USER` / `SMTP_PASSWORD` | Secure mail authentication; an app password if required by the provider |
| `SCANNER_EMAIL_ENABLED` | `1` explicitly enables the sending step |

SMTP needs real credentials injected securely into the durable service; a secret substituted only by an HTTPS proxy is not SMTP authentication. Do not copy proxy placeholders to another host. Choose a durable host or managed scheduler, persistent storage, and authorized connectivity to SMTP and `api.massive.com`; these connections do not exist automatically.

Prepare a private email draft after configuring the recipient and sender variables:

```sh
.venv/bin/python scanner.py deliver /path/to/private-state/runs/daily/RUN/report.md
```

`--send` sends via verified TLS and requires `SCANNER_EMAIL_ENABLED=1`. Draft `.eml` files remain in the private outbox. No raw data is attached. Daily/weekly checkpoints prevent every timer tick from sending another copy. Failed or uncertain scheduled delivery stops automatic attempts; check whether mail was accepted before a manual retry. A delivery failure and a screening failure are separate outcomes.

No mail was sent and no Gmail permissions or durable service were configured during development. Before continuous use, verify a real post-close run, receipt by the authorized recipient and state retention after a service restart.

## Data usage and research sources

Official references:

- Terms: https://massive.com/terms
- Daily market summary: https://massive.com/docs/rest/stocks/aggregates/daily-market-summary
- History: https://massive.com/docs/rest/stocks/aggregates/custom-bars
- Splits: https://massive.com/docs/rest/stocks/corporate-actions/splits
- Pricing: https://massive.com/pricing

Public-site access initially failed through the proxy with `Tunnel connection failed: 403 Forbidden`, while `api.massive.com` worked. Required public-site domains were saved in the environment draft. Until the updated policy is applied and terms are read, **terms verification remains incomplete**. Do not redistribute source data or claim that distribution is authorized. Review personal-use restrictions, derived-report rights and each research source's terms. No source data was distributed during validation.

Research uses Massive company details and dated news, supported /stocks/financials/v1 endpoints when entitled, and public SEC company facts as a free fallback. The retired /vX financial endpoint is never called by the final implementation. Previously cached legacy statements are explicitly labeled archival, not current latest-filing verification. A headline is evidence of a publication, not independent proof of every claim in it. Price movement does not prove a causal catalyst. Missing debt is not zero debt; total liabilities are not financial debt; basic-versus-diluted share counts do not prove an offering. Upcoming earnings and ATM/shelf/convertible risks require updated primary sources; missing information is stated explicitly.

News and financial endpoint access is tested during research. An inaccessible endpoint is not repeatedly probed for every ticker in the same run. There is no automatic paid-plan upgrade.

## Verified research access limitations

The retired `/vX/reference/financials` returned HTTP 410: `This endpoint has been deprecated and is undergoing a brownout.` The official Massive Python SDK at commit `481e5c270ea85e8eae5e96f8b9fda34e5e2a674a` confirms the supported replacement paths.

The current account returned HTTP 403 (`You are not entitled to this data`) for `/stocks/financials/v1/balance-sheets`, `/stocks/financials/v1/cash-flow-statements` and `/benzinga/v1/earnings`. No upgrade was performed. Failure diagnoses are cached per research date and not repeated for every candidate. After an actual access/network settings change, explicitly use `daily --recheck-research` to recheck; a failed recheck still stops further attempts to that endpoint in the run.

The free SEC company-facts path and investor-relations sites returned proxy `Tunnel connection failed: 403 Forbidden`. Required additions were saved in the environment draft: `data.sec.gov`, `www.sec.gov`, `investor.arrow.com`, `ir.avnet.com`, and `www.avnet.com`, preserving existing allowed domains. Apply the policy before rechecking public research. SEC requests never receive the Massive Authorization header. `SEC_USER_AGENT` can privately override the truthful project identifier to meet SEC identification requirements.

The SEC parser has synthetic unit coverage, including issuer matching, future-filing exclusion and invalid values. Its live behavior remains unverified because public access is blocked. Primary filing links use the issuer CIK, never the filing-agent accession prefix. Each fact records where its data was retrieved and whether a linked primary page was independently fetched.

Upcoming earnings, an established catalyst and current dilution obligations remain unverified until primary sources are read. An archived operating-cash-flow number is historical evidence only. Technical screen success must not be presented as completed company due diligence.
