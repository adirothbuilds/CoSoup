# Validation appendix: deterministic analytics and conversational tools on Mac

Validated on 2026-10-08 in the existing local development deployment. This appendix distinguishes synthetic tests, real cached-data calculations, authenticated agent execution and browser checks. It does not certify strategy returns or broader financial coverage.

## Delivered behavior

New daily scans retain their original eligibility and ranking while adding simple-mean ATR14, annualized 20-session log-price volatility, prior-range contraction, five-session rolling volume confirmation, 21/63/126-session excess price changes versus SPY, maximum 63-session close drawdown and numeric evidence for all original filters. Breadth uses the verified-history denominator and discloses excluded histories. A separate bounded filter-review list never becomes a candidate list.

The provider-neutral offline research script exposes approved analysis discovery, inspection, conversational screening and chart datasets. Matching-period financial calculations retain operands, units, filing dates, original source URLs and explicit gaps. Institutional weights use the complete supplied non-option SH subset; overlap requires exact identifiers and a common quarter. No inferred live trades, fabricated TTM, net debt from noncurrent debt alone, model-provider API key or new agent harness was added.

Chat can enrich old reports from a batched cached matrix. Selected-symbol diagnostics come only from the approved report's owner-scoped, session-matched detailed artifact, with compressed/decompressed limits. Financial/tool acronyms do not silently select unrelated stocks; an explicit $TICKER or ticker reference can resolve an ambiguous symbol. Charts also support watchlist, filter-review and selected-symbol measurements when no stocks pass the original screen. The main interface retains its conversational layout with three updated prompts.

## Synthetic validation

- Required scanner command passed 89 tests: `.venv/bin/python -m unittest discover -s tests -v`.
- Required server command passed 88 tests: `.venv/bin/python -m unittest discover -s apps/server/tests -v`.
- Both suites ran in an isolated native ARM64 runtime with existing dependencies, no network and no private deployment mounts. Temporary execution and sufficient filesystem capacity were provided for the suites' existing shell-fixture and storage-reservation checks.
- Arithmetic fixtures cover gap-aware true range, base exclusion, zero-range/volatility behavior, breadth denominators, aligned financial periods/units, filing cutoffs, restatements/conflicts, invalid denominators, institutional concentration/overlap, missing screening measurements and canonical percentage conversion.
- Server fixtures cover standalone CLI authorization, batched cache reads, stale dates, cache-basis mismatch, zero-candidate watchlist charts, diagnostic ownership/date checks, decompressed input limits and acronym/ticker ambiguity.
- Web/client checks and the production web build passed. Vitest passed 10 tests. Eight targeted desktop/mobile appearance and chat fixtures passed; chat/portfolio/document writes were intercepted by those fixtures.
- The broader workspace typecheck also reached the separate mobile app, whose optional native dependencies are absent in this Mac checkout. No successful mobile-app typecheck is claimed. The full browser workflow suite was stopped before its real scan/journal workflows; no full-suite success is claimed.

## Real data and authenticated conversation

An offline historical reconstruction through 2026-10-02 completed without provider requests. It evaluated 5,559 equities, found 4,553 valid histories, retained the same two candidates and 50 near-breakouts, and added 20 filter-review observations plus breadth and per-symbol measurements.

An authorized online refresh then acquired missing data through 2026-10-07 using the existing shared maximum-five-per-minute request ledger. It succeeded with partial coverage: 5,551 evaluated equities, 4,545 valid histories, no original-rule candidates and 46 near-breakouts. This zero-candidate result describes verified histories under the existing rules, not an absence of opportunities. Existing SEC coverage remains the bounded October 8 sync for two companies and two managers; no new SEC fetch was required for the analytics.

The dedicated account-authenticated `gpt-6.1-sol` analyst completed real public-data analysis and follow-ups in one native conversation. Native records confirm discovery, inspection, screening and chart-tool execution; follow-up provenance confirms explicit native-session resumption. Analysis distinguishes original eligibility from conversational filters, market dates from SEC sync dates, and incompatible company reporting periods. The selected-symbol follow-up retrieved exact original October 7 failures for AVT/ARW: both failed breakout and volume confirmation. Saved charts use host-supplied approved values.

The final acronym-selection correction was verified through the actual read-only context preview: AVT/ARW diagnostics were included, while ATR remained a measurement unless explicitly named as a ticker. A further native follow-up completed with no gaps, explicit session resumption and one host-rendered chart containing exactly AVT and ARW.

All six saved conversation charts were inspected in installed Chrome at 1440px and 390px, including reload persistence, dated explanations, financial charts, final two-company labels, no horizontal overflow and no runtime errors. Browser inspection made no model, provider or journal writes.

## Isolation, scheduling and preservation

The actual final native wrapper's sandbox probe passed: authorized task input/read and scratch/write were allowed; auth, secrets, unrelated private data, other task files, process environment and outside-workspace writes were denied. The auth probe only opened/closed a descriptor and never read its contents. Probe scratch was removed.

A durable owner-scoped daily market-close schedule is enabled in the existing database and serviced by the existing scheduler. It requests missing market data and deterministic calculations, with company-source research disabled and no automatic model calls. Its next occurrence at validation is 2026-10-08 20:30 UTC. Execution requires the local Docker deployment to remain running; future scheduled completion is not asserted here.

All existing private env/config/credential/login files matched their preservation references. All 281 pre-existing raw market files and all original saved reports remained intact; new cache files, reports, native conversation state and the authorized schedule are expected additions. PostgreSQL, the existing scheduler/storage/import workers and unrelated Docker workloads were preserved. No Docker Desktop restart, private env replacement, login reset, migration, commit or push occurred.
