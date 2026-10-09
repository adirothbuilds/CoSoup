# Prospective paper portfolio

CoSoup supports an owner-activated hypothetical portfolio alongside background research. It has no broker connection or real order execution. Historical backtesting is a separate problem: an accumulating price archive does not establish a dated universe or historical information availability.

## Starting and observing an experiment

Create an experiment through `POST /api/v1/paper/experiments`. Defaults are USD 100,000 hypothetical cash, long-only exposure, at most ten positions and at most 20% target weight per position. No borrowing is supported. Creation fixes the policy, actual start time, configured analyst/model and comparison books. An idempotency key prevents duplicate creation. Up to ten owner-scoped experiments are supported.

The account-authenticated Codex manager uses its own explicitly resumed native session, approved research context and trusted offline tools. A successful current live scan is a durable dependency for each subsequent decision. Each experiment/session/stage is queued once; failed model or provider jobs are preserved without automatic repeats. An initial decision can use the latest provider-ready live report available at creation. Daily acquisition and deterministic valuation remain independent of model availability.

The manager proposes `hold` or `rebalance`, target weights, reasons, cited authorized sources and research gaps. Cash is legitimate; a missing or incomplete source does not establish that no opportunities exist. The host validates unique approved symbols, finite positive weights, total exposure, count and position limits. The approved universe is the bounded supplied candidate/watchlist/filter-review set plus existing holdings; it is not the whole stock market.

Decisions preserve their completion/cutoff timestamps, supplied artifact hashes, model/profile provenance and validation outcome in immutable reports and a separate private ledger. The model cannot choose fill prices, share quantities or account balances. Experiment tools cannot modify the owner's personal portfolio.

## Hypothetical timing and accounting

A completed decision can first execute at a daily-bar open on a trading date strictly after its completion's New York calendar date. Future execution stays pending until that session's cached data is available. A provider daily open is not certified as the official 09:30 auction price. Prices that informed a decision cannot be used as earlier hypothetical fills.

Deterministic accounting uses raw prices, fractional shares rounded down to eight decimal places, sells before buys, and available cash. Supported splits change shares once before valuation. Missing prices and unknown split bases create explicit blocked fills or unavailable valuations; they never become invented prices, stale substitutions or zero-value liquidations. Original decisions and gaps remain inspectable. Blocked executions are not automatically repeated.

The primary view excludes fees, dividends, cash interest and taxes. Daily snapshots calculate hypothetical equity, cash, price-only percentage change and drawdown. A separately labeled 10-basis-point notional cost sensitivity is an assumption, not a spread/slippage model. Neither series certifies real trading returns.

Two separate comparisons start with the same cash and future-open price convention: SPY buy-and-hold, and the deterministic original-candidate scanner baseline. The scanner selects equal target weights capped at the experiment's position maximum, retains cash otherwise, and is prepared independently of model success. These comparisons help distinguish market exposure, screening and analyst decisions. A short observation window and incomplete research remain interpretation limits.

## Interface and lifecycle

Home keeps a compact expandable paper-portfolio card with cash, valuation, decision links, holdings, gaps and comparison charts once valuations exist. Chat can inspect approved experiment analyses and request host-calculated charts, including the opening balance before the first valuation. Personal portfolio/documents still require their existing explicit sharing permissions.

`GET /api/v1/paper/experiments` and `GET /api/v1/paper/experiments/{id}` return owner-scoped state. `PATCH /api/v1/paper/experiments/{id}` accepts only `status: active` or `status: paused`. Pausing prevents new manager decisions; deterministic valuation and previously accepted pending commitments continue. Starting a comparison with another policy or analyst requires a new experiment.

The existing provider-neutral analyst adapter and structured tool contracts remain reusable by a future account-authenticated backend. Codex currently uses the dedicated account login; there is no API-key fallback. Claude is not connected. The durable scheduler runs while the home deployment is awake; host sleep or Docker downtime suspends processing.

## Price archive

`GET /api/v1/market/history` reports the two-calendar-year target, missing sessions and retained archive. `POST /api/v1/market/history/backfills` freezes that target in a durable missing-only acquisition job. It reuses original cached daily files, collects recent missing dates first, and obtains the matching dated split reference through the same persistent provider rate limiter. Exact provider rejection is saved and stops acquisition without retries or entitlement bypass.

Daily scans append new sessions. Retaining raw data lets the archive grow beyond the provider's current retrieval window, provided storage policy keeps those originals; old retained data is not re-requested merely because it lies outside that window. Normal screening still uses its existing 260-session analytical window. The web's explicit `2Y` candle option reads the cached archive and never initiates provider acquisition. Missing dates remain disclosed, and full historical candles do not imply complete historical fundamentals.
