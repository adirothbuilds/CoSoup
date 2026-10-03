# Stock Scanner

Experimental personal end-of-day research for US equity swing and medium/long-term opportunities. Massive is the data provider. There is no broker connection, trade execution or subscription upgrade.

The scanner covers common/ordinary shares and common ADRs on supported US exchanges across sectors and company sizes. It caches 260 market-wide sessions privately, resumes interrupted ingestion, adjusts prices and share volume consistently for splits, and produces English JSON and Markdown reports with coverage, data errors and every failed filter. SPY and IWM data must pass validation before candidates are reported. Missing data never means that no opportunities exist.

## Run in the cloud

```sh
cd /workspace/stock-scanner
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m unittest discover -v
.venv/bin/python scanner.py preflight
.venv/bin/python scanner.py daily
.venv/bin/python scanner.py weekly
```

`MASSIVE_API_KEY` is supplied through the existing Network secret for `api.massive.com`. Never print or store its value. Personal email addresses and mail credentials belong only in private environment settings.

State and reports default to `/workspace/stock-scanner-state`, **outside the repository**; override with `SCANNER_STATE_DIR`. Initial ingestion takes approximately one hour at fewer than five requests per minute. Later runs fetch missing sessions only. Use `ingest` separately or `daily --offline` to evaluate the exact cache without network access.

## Default rules

Close at least $5; prior 50-session average of 500,000 shares and $10 million daily dollar volume; close above the preceding 55-session high; at least 1.5x prior average volume; positive 63-session price change exceeding SPY; close above SMA50 above SMA200; at most 5% above the breakout pivot and 15% above SMA50. Configure thresholds in `config.json`. A separate near-breakout watchlist is available. Candidate counts are never forced.

The weekly summary follows prior real signals and failures, adjusting their reference prices for subsequent splits. A signal's price change is not a trading return. Company research separates sourced facts, hypotheses and missing information; unverified earnings dates, debt or dilution risks remain explicit gaps.

## Scheduling and delivery

`schedule-plan` shows the next eligible close-plus-buffer time. `scheduled` is an entrypoint for a durable scheduler with persistent private storage. Templates in `deploy/` are prepared for an external systemd host; they are not installed in this temporary cloud environment. Mail requires private configuration and explicit `--send` enablement. A cron job in a temporary development environment must not be assumed to persist.

See [operations and access requirements](docs/OPERATIONS.md), [calculation and coverage design](docs/DESIGN.md), and [actual validation evidence](docs/VALIDATION.md). Company due diligence is currently limited by HTTP 403 on the new financial/earnings endpoints and proxy blocking of free primary sources; see operations for the explicit recheck flow. Review provider terms before distributing source data or derived reports. Terms verification remains pending while the provider's public terms site is blocked by network policy.

## License

The project's code and documentation are available under the [MIT License](LICENSE), provided as is without warranty. This is experimental research software; its outputs are not investment advice or guaranteed results.

The MIT License does not grant rights to Massive market data, third-party news or filings, or dependency packages. Those materials remain subject to their respective terms and licenses. Raw market data, private reports, credentials and personal recipient addresses are not included in this public repository.
