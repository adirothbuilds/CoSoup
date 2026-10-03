# Calculation and reliability

## Supplied baseline

Rules were adapted from `scanner.py` and `config.json` in the supplied ZIP. Its documentation, historical results and instructions were treated as input to review, not authority to use the prior provider or distribute data. Previous Yahoo failures are not validation evidence for this implementation. There is no yfinance dependency.

## Data and coverage

The dated Massive listing query uses `market=stocks`, `locale=us`, `active=true`, and the data date, with complete pagination. Eligible types are `CS`, `OS`, `ADRC`, and `NYRS` on `XNAS`, `XNYS`, `XASE`, `ARCX`, `BATS`, and `IEXG`, in USD. Funds, ETFs, preferred shares, warrants, units, rights and other security types are excluded and counted by reason. Actual provider listings contained funds classified as CS, so a conservative security-name guard also excludes fund/unit/preferred/warrant/right/debt labels even when the type is common. LP/L.P. and limited-partnership names are also conservatively excluded: the supplied exchange directory identifies examples such as AB, ARLP and XIFR as units even when Massive labels them CS. This guard can omit ambiguous names and is reported separately; REIT common shares are retained. OTC and unidentified exchanges are outside coverage. Duplicate or empty listings fail validation. No sector or market-cap floor is imposed. Sector and cap metadata are not fetched for every stock, so the report does not claim a fully audited sector mapping.

For each of 260 XNYS sessions, one unadjusted market-wide snapshot is stored (`adjusted=false`, `include_otc=false`) using atomic writes. A missing market day cannot silently pass. Split events are paginated for the entire window. For observations preceding a split execution date, prices are divided by `split_to/split_from` and share volume is multiplied by the same factor. The basis is the data date; later splits are excluded. Price-times-volume remains invariant. Reverse splits are handled identically. Invalid or ambiguous events reject the affected security. Dividends are not adjusted. Ticker changes, mergers and ADR ratio changes absent from the source can still impair coverage.

A compact NumPy matrix holds equities by sessions by OHLCV. It avoids thousands of separate downloads and DataFrames. Raw data remains outside Git. Cached completed sessions are not refreshed automatically; a late provider correction can require an intentional refresh after diagnosis. Provider accuracy is not certified by basic validation. Independent real-data checks found matching benchmark OHLC but differing grouped-versus-ticker-history volume. The discrepancy is preserved as validation evidence and a report warning; the scanner uses one consistent grouped source rather than mixing endpoint volumes.

## Configurable rules

Defaults in `config.json`:

- Close at least $5.
- Average of the **prior 50 sessions**, excluding the current session: at least 500,000 shares and $10 million close-times-volume.
- Close strictly above the maximum intraday high of the **prior 55 sessions**. Current high cannot raise the pivot.
- Current volume at least 1.5x the prior 50-session average.
- Positive 63-session price change exceeding SPY over the identical dates.
- Close above SMA50 above SMA200, with at least 220 consecutive recent observations.
- At most 5% above the pivot and 15% above SMA50, preserving the supplied baseline.
- Separate near-breakout watchlist within 3% below the pivot. It must satisfy price, liquidity, trend and relative strength, but may lack breakout and volume confirmation.

Candidates sort by excess price change versus SPY and then volume ratio. This is not a calibrated probability. All passing candidates are retained; detailed research defaults to the leading five. No arbitrary candidate count is filled.

A small company can fail liquidity without a cap floor: at $5, approximately 2 million daily shares are required for $10 million dollar volume. Examples of liquidity exclusions are illustrative rather than a representative small-cap sample. Size is stated only when market cap was fetched and sourced; otherwise it remains unknown.

## Quality and failure handling

The data date is the latest XNYS session whose close plus 30 minutes has elapsed, using America/New_York. Holidays, daylight savings and early closes are included. Both SPY and IWM require valid data for **the entire** window. IWM is a health cross-check, not an extra ranking rule.

Security checks include the expected last date, consecutive recent sessions, finite positive prices, nonnegative volume and consistent OHLC. Missing observations are never forward-filled or silently dropped. IPOs with fewer than 220 observations are documented separately. An internal gap in the required recent window is a data error. A data-error fraction above the configurable 10% threshold, or no valid histories, blocks a shortlist. All individual failures and checks are retained privately.

`complete` means the entire selected universe was evaluated with no unexpected data errors; documented insufficient-history exclusions may remain. `partial_coverage` means unexpected security data errors occurred below the blocking threshold. A blocked run cannot be interpreted as a zero-opportunity result.

## Signal monitoring

Verified signals are stored in SQLite with a date/symbol/rules-hash key to prevent duplicates. Weekly reports follow signals produced by actual runs rather than a synthetic historical backtest. They measure observed price change, maximum drawdown in closing prices and closes below the original pivot. Later splits rebase both original signal close and pivot.

A failed signal is a close below its original split-adjusted pivot; a later recovery is recorded separately. Missing follow-up data stays unavailable. No simulated portfolio, entry, exit, execution price, dividend-adjusted return or trading return is claimed. The first deployment may have only one daily report; its week is marked partial rather than inventing earlier observations.
