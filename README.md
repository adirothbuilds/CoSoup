<p align="center">
  <img src="docs/assets/cosoup/banner.svg" alt="CoSoup — research, simmered" width="900" />
</p>

<p align="center">
  <a href="apps/server/README.md"><img src="docs/assets/cosoup/badges/python.svg" alt="Python 3.12+" /></a>
  <a href="apps/web/README.md"><img src="docs/assets/cosoup/badges/node.svg" alt="Node 24 LTS development toolchain" /></a>
  <a href="apps/server/requirements.txt"><img src="docs/assets/cosoup/badges/fastapi.svg" alt="FastAPI 0.142.2" /></a>
  <a href="apps/web/package.json"><img src="docs/assets/cosoup/badges/react.svg" alt="React 19.2.3" /></a>
  <a href="apps/mobile/package.json"><img src="docs/assets/cosoup/badges/expo.svg" alt="Expo 57.0.26" /></a>
  <a href="package.json"><img src="docs/assets/cosoup/badges/typescript.svg" alt="TypeScript 5.9.3" /></a>
  <a href="LICENSE"><img src="docs/assets/cosoup/badges/license.svg" alt="MIT license" /></a>
</p>

<p align="center">
  <strong>A calmer workspace for stock research.</strong><br />
  Market signals, portfolio context and a research companion, in one pot.
</p>

<p align="center">
  <a href="apps/server/README.md">Server</a> ·
  <a href="apps/web/README.md">Web</a> ·
  <a href="apps/mobile/README.md">iOS</a> ·
  <a href="docs/OPERATIONS.md">CLI</a> ·
  <a href="docs/VALIDATION.md">Validation</a>
</p>

# CoSoup

Experimental personal research for US equity swing and medium/long-term opportunities. CoSoup combines Massive end-of-day data, a self-hosted server, web and iOS clients, and an optional Codex research companion called **Steve**. It produces English JSON and Markdown reports and has no broker connection, order execution or paid-plan upgrade mechanism.

| In the pot | What you get |
| --- | --- |
| Market research | Configurable breakout and near-breakout screening, daily candles, relative strength and a 3D movement view on the web. |
| Portfolio context | A personal transaction journal, reviewed photo/document imports and explicitly authorized context for the research agent. |
| Home-server operations | Durable jobs, configurable schedules, historical snapshots and retention, with optional encrypted Cloudflare R2 archiving. |

<details>
  <summary>Meet Steve and the CoSoup bowl</summary>
  <p align="center">
    <img src="docs/assets/cosoup/mascots.png" alt="Steve, an anime chef holding a pan, beside the friendly charcoal and teal CoSoup bowl" width="640" />
  </p>
  <p>Steve cooks the research; you make the decisions. The mascots are decorative, not a representation of live market data.</p>
</details>

This is an alpha: optional integrations require private configuration and verification. Read the [validation notes](docs/VALIDATION.md) for what has actually been tested. Technology badges describe declared dependencies and the documented development toolchain; they are not CI status indicators.

## Applications

- [`apps/server`](apps/server/README.md): authenticated FastAPI service, durable jobs and scheduling, configurable private storage/R2 archiving, portfolio journal, reviewed document imports and an optional dedicated Codex worker. Designed for Docker Compose on a home Debian server.
- [`apps/web`](apps/web/README.md): responsive React research workspace, linked 3D movement and daily candles, portfolio/import review, history and operations.
- [`apps/mobile`](apps/mobile/README.md): Expo/React Native iOS client with native charts, private Keychain credentials and photo/document workflows.
- `packages/client` and `packages/design`: shared web/native transport contracts, metric/query helpers and design tokens.
- `stock_scanner/`: reusable provider, calendar, quality checks, screening and source-research library.
- `scanner.py`: standalone daily/weekly CLI. Its dependencies remain separate from the optional server dependencies.

Every server worker has its own module under `apps/server/workers/`; extension contracts live under `apps/server/adapters/`. Additional applications can be added under `apps/`.

Run `make help` for development, tests, web/iOS builds and Docker deployment. Development requires Python 3.12+ and Node 24 LTS. `make deploy` uses private host configuration and starts persistent services; `make ios-export` bundles native assets, while `make ios-build` requires a Mac with Xcode/signing. See the application guides before configuring private HTTPS and credentials.

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
