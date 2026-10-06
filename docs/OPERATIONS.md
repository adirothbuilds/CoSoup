# Scanner CLI operations

Run commands from the repository root after installing `requirements.txt`. For the Docker/FastAPI application, use the separate [server guide](../apps/server/README.md).

## Private configuration

Provide `MASSIVE_API_KEY` through an authorized private environment/credential mechanism scoped to HTTPS `api.massive.com`. Never print it, put it in a URL, or forward it to another host. Network-proxy credential substitution is not necessarily a portable raw credential for another server.

Set `SCANNER_STATE_DIR` to an owned directory outside the checkout with mode 0700. Raw snapshots, research caches, private JSON/Markdown, `signals.sqlite3` and outbox files belong there. For portability, set this variable explicitly; the legacy CLI default is intended for a workspace deployment. Do not put private state, email addresses or mail authentication in Git.

## Commands

```sh
.venv/bin/python scanner.py preflight
.venv/bin/python scanner.py ingest
.venv/bin/python scanner.py daily
.venv/bin/python scanner.py daily --offline --no-research
.venv/bin/python scanner.py weekly
.venv/bin/python scanner.py schedule-plan
```

Global `--config` and `--state-dir` options precede the subcommand. `--as-of` requires a timezone-qualified observation timestamp; it does not establish a survivorship-free backtest. The server adds explicitly separated historical snapshot workflows.

`preflight` independently checks grouped daily access, complete SPY/IWM history, split history and dated listings. Success does not establish a particular subscription name or guarantee future entitlement.

All provider requests share a persistent limiter, at least 13 seconds apart and at most five per rolling minute. Initial 260-session ingestion can take over an hour. Cached valid days are reused. Connection/read timeout is 15 seconds. There are no automatic provider retries; HTTP 429 persists a cooldown. Diagnose the exact error before an explicit new attempt. Do not delete cooldowns or bypass TLS/access policy. Corrupt caches are replaced atomically during an explicit resumed run.

## Result quality

- `complete`: required market days and benchmarks are valid, and no unexpected stock-level data errors occurred. Documented insufficient-history exclusions can remain.
- `partial_coverage`: unexpected security data errors occurred below the configurable blocking threshold. Read coverage and individual failures.
- `blocked_*`: access/data/quality prevented a usable scan. Opportunity availability is unknown.

Blocked CLI commands return 2. Partial results return 0; consumers must read JSON `status`, `coverage` and `errors`. Technical success does not mean completed company due diligence.

## Scheduling and mail

The server provides persistent schedules, occurrences and job logs. The older templates in `deploy/` are an alternative external systemd entrypoint for the CLI. They require persistent private storage, correct paths and an authorized service account. A temporary process or development cron is not a durable deployment.

The CLI `scheduled` command gates work on NY market close plus the settlement buffer, including holidays, DST and early closes. Weekly work occurs after the final trading session of the week. Delivery is explicit and disabled until configured.

Private mail variables: `SCANNER_REPORT_TO`, `SMTP_FROM`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD` and `SCANNER_EMAIL_ENABLED`. Use verified TLS on 465 or 587. HTTPS proxy placeholders are not SMTP authentication. Prepare a draft with `deliver /private/path/report.md`; `--send` additionally requires explicit enablement. No raw market data is attached. Inspect uncertain delivery before a manual retry.

## Source access and usage

Public references: [terms](https://massive.com/terms), [daily market summary](https://massive.com/docs/rest/stocks/aggregates/daily-market-summary), [history](https://massive.com/docs/rest/stocks/aggregates/custom-bars), [splits](https://massive.com/docs/rest/stocks/corporate-actions/splits), and [SEC](https://www.sec.gov/).

Review applicable terms before copying raw data to remote archives or distributing source data/derived reports. A software license does not authorize redistribution of third-party data. Keep private archives and buckets private.

Supported research endpoints are `/stocks/financials/v1/balance-sheets`, `/stocks/financials/v1/cash-flow-statements` and `/benzinga/v1/earnings`. HTTP 403 is an entitlement failure, not missing company debt. The retired `/vX` route is not queried. Cached legacy statements are labeled archival. SEC company facts can supplement financial data when public access is permitted; SEC never receives the Massive credential.

Failure diagnoses are cached. After a meaningful connectivity/access change, `daily --recheck-research` explicitly rechecks. Headlines are publication evidence, not independently confirmed catalysts. Upcoming earnings, dilution and borrowing obligations require current primary-source review; missing information stays missing.
