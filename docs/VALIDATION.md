# Validation evidence

Validated in the current cloud instance on 2026-10-03. This documents actual outcomes, not a promise of future restoration or uninterrupted scheduled operation. Provider data, generated reports, credentials, private addresses and the signal database remain outside the repository.

## Software and environment

- Python 3.12.14; the pinned dependencies in `requirements.txt` installed successfully in `.venv`.
- `python -m unittest discover -v`: **49 tests passed**, with no skips or expected failures. Tests cover the exchange calendar, early closes, split-adjusted prices and volumes, prior-window calculations, security classification, quality failures, incomplete coverage, secret redaction, destination restrictions, persistent rate limiting, resumable ingestion, SEC parsing, signal observations and delivery/scheduler idempotency.
- The saved setup commands were executed in this instance and repeated successfully. Dependency consistency and source compilation passed.
- The systemd timer syntax was verified. The service was not installed or executed on a durable host; SMTP transmission was not tested or activated.

## Real provider access and complete market scan

The existing Massive credential successfully accessed dated listings, split events, grouped daily US market summaries and individual SPY/IWM histories. No plan was upgraded.

The exact 260-session window was **2025-09-22 through 2026-10-02**. All market-wide daily snapshots were downloaded and cached. Subsequent ingestion reused the complete cache without changing the request-rate ledger, demonstrating zero additional provider calls. Incomplete or corrupt caches are separately covered by resume tests.

Final daily coverage:

| Measure | Actual result |
| --- | ---: |
| Provider listings | 13,258 |
| Selected equities evaluated | 5,559 |
| Common shares | 5,182 |
| Common ADRs | 377 |
| Eligible-type names excluded conservatively | 140 |
| Valid histories | 4,553 |
| Insufficient histories | 599 |
| Unexpected data errors | 407 |
| Stale / missing sessions / missing data | 126 / 278 / 3 |
| Passing candidates | 2 |
| Near-breakout watchlist | 50 |

The result is **`partial_coverage`**, not a fully clean market scan. Unexpected data errors affected about 7.32% of the selected universe, below the configured 10% blocking threshold. All individual results, dates and failed filters are preserved privately. Stocks are not selected by sector or company size; the universe does not establish a fully verified sector classification. LP/unit and fund names classified as common by the provider are excluded conservatively.

SPY and IWM each passed full-window validation with 260 observations. Independent ticker-history checks matched grouped OHLC exactly across all 260 sessions. Endpoint volumes were **not identical**: maximum relative differences were approximately 1.8242% for SPY and 1.6899% for IWM, affecting 53 and 55 sessions respectively. This remains a report warning. Screening consistently uses grouped daily volume for all securities rather than mixing endpoints.

A real NFLX 10-for-1 split on 2025-11-17 was checked over a 135-session subwindow. Local split-adjusted prices matched the provider's adjusted history within approximately 4.44e-7 relative error; volume differed by up to approximately 0.1097% between endpoints. Unit tests independently verify price-times-volume invariance for forward and reverse splits. These checks do not certify every provider corporate action.

## Research limitations and exact access failures

Current issuer descriptions and indexed news were retrieved for the two candidates. Sourced small/mid-cap examples demonstrate that a stock can pass the share-volume floor while failing the dollar-volume floor. Primary linked articles and filings were not all independently retrieved; reports distinguish provider observations from unread primary-source links.

The supported financial endpoints `/stocks/financials/v1/balance-sheets`, `/stocks/financials/v1/cash-flow-statements`, and `/benzinga/v1/earnings` each returned:

> HTTP 403: You are not entitled to this data. Please upgrade your plan at https://massive.com/pricing

No upgrade or repeated entitlement retry was performed. The older `/vX/reference/financials` route returned HTTP 410 during validation; final code does not call it. Any already-cached historical financial facts are labelled archival and do not satisfy current debt, cash-flow or dilution review.

The free SEC companyfacts fallback is implemented and unit-tested. Real requests to `data.sec.gov`, issuer investor-relations sites and the provider terms site were blocked with:

> Tunnel connection failed: 403 Forbidden

Consequently current debt, cash flow, dilution, the next confirmed earnings date and a verified breakout catalyst remain gaps. Terms were not read successfully, and distribution rights have not been established. Raw data and derived reports have not been published. Apply the saved public-site network settings before an explicit `daily --recheck-research`; runtime access has not been verified after applying those settings.

## Weekly monitoring, delivery and persistence

The weekly summary uses one actual daily data date. Four preceding sessions in that week have no daily report and are explicitly marked missing. Both actual signals are awaiting follow-up; no historical price change or trading return was fabricated. Repeated daily scans did not duplicate signal rows.

Saved configuration includes the tested installation script, startup instructions, private recipient requirement, disabled mail setting and public-source network domains. Saving the draft does not apply runtime access or publish a cloud snapshot. Fresh-task restoration has not been tested.

External durable scheduling and private SMTP settings are still required. Templates and an idempotent scheduling entrypoint are prepared, but no timer or cron was activated in this temporary development instance and no email was sent. At the end of validation, no commit, push or pull request had been created. Publication requires the user's explicit approval and their Git identity; the user subsequently approved direct publication to main under the MIT License.
