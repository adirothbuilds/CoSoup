# Stock research tools

Experimental personal research for US equity swing and medium/long-term opportunities. The project uses Massive and produces English JSON and Markdown reports. It has no broker connection, order execution or paid-plan upgrade mechanism.

## Applications

- [`apps/server`](apps/server/README.md): authenticated FastAPI service, durable jobs and scheduling, configurable private storage/R2 archiving, portfolio journal, reviewed document imports and an optional dedicated Codex worker. Designed for Docker Compose on a home Debian server.
- `stock_scanner/`: reusable provider, calendar, quality checks, screening and source-research library.
- `scanner.py`: standalone daily/weekly CLI. Its dependencies remain separate from the optional server dependencies.

Every server worker has its own module under `apps/server/workers/`; extension contracts live under `apps/server/adapters/`. Additional applications can be added under `apps/`.

## Standalone scanner

From the repository root:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scanner.py preflight
.venv/bin/python scanner.py daily
.venv/bin/python scanner.py weekly
```

Provision `MASSIVE_API_KEY` privately and set `SCANNER_STATE_DIR` to a protected directory outside the checkout. Do not put credentials or personal email addresses in Git. Initial ingestion loads 260 sessions conservatively, resumes cached progress, and can take over an hour. Later runs download missing days only.

Common/ordinary shares and common ADRs on supported US exchanges are screened across sectors and company sizes. SPY and IWM must pass validation. Reports document actual coverage and every failed filter; blocked or missing data is never described as an absence of opportunities.

Default thresholds: $5 minimum price; prior 50-session averages of 500,000 shares and $10 million dollar volume; close above the preceding 55-session high; at least 1.5x prior average volume; positive 63-session price change exceeding SPY; close above SMA50 above SMA200; at most 5% above the pivot and 15% above SMA50. Configure `config.json`; a separate near-breakout watchlist is available. Candidate counts are never forced.

Company research separates sourced facts, hypotheses and gaps. Financial/news access depends on provider entitlements. Signal price changes are observations, not trading returns. Server historical snapshots are separate from live signals.

See [calculation design](docs/DESIGN.md), [CLI operations](docs/OPERATIONS.md), [server deployment](apps/server/README.md), [server architecture](docs/SERVER_PLAN.md), and [validation methods](docs/VALIDATION.md).

## License

Code and documentation use the [MIT License](LICENSE), provided as is without warranty. Outputs are not investment advice or guaranteed results. MIT does not grant rights to Massive market data, third-party news/filings or dependencies; their terms and licenses still apply. Raw data, private reports and personal credentials are excluded from this public repository.
