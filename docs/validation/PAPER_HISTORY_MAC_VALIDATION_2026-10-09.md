# Validation appendix: retained history and prospective paper experiment

Date: 2026-10-09. Target: the existing private Apple Silicon Mac development deployment. This appendix records local results; it does not establish Linux runtime compatibility or real trading returns.

## Authorization and preservation

The owner requested the provider-entitled two-calendar-year archive, continued accumulation, and an active hypothetical Codex portfolio starting today. Existing authorization covered committing and pushing the application work. No broker, production identity, paid upgrade, database migration, new authentication profile or unrelated Docker restart was introduced.

The existing private env, generated configuration, dedicated Codex account login and secrets were reused. A private checksum audit verified all 17 original configuration/authentication/secret files unchanged, and stat checks verified all 288 original raw artifacts unchanged. Additional data, experiment ledgers, reports and native session state remain outside the public repository. Public-file auditing compared credential/contact references privately and found no matches.

## Real history acquisition

The frozen acquisition window is 2024-10-09 through 2026-10-08: 501 exchange sessions. There were 264 already cached grouped sessions and 237 missing at creation. Acquisition reused valid cached originals, processed missing sessions newest first, registered private artifacts and shared the existing persistent five-request-per-minute limiter. It does not retry or bypass exact provider failures.

The actual acquisition job succeeded with all 501 grouped sessions and its full dated split reference retained; no source errors were recorded. The archive now contains 501 grouped sessions, with no missing sessions in the frozen acquisition window.

Real `lookback_years=2` SPY and ARW requests each returned 501 validated bars from 2024-10-09 through 2026-10-08. Both explicitly disclosed one earlier missing session (2024-10-08): a two-year chart measured from its last market session asks for that date, while the provider-entitled acquisition is measured from today. The earlier date was not fetched outside the target. Cold requests took about 9.2–9.4 seconds to read the larger cache; repeated requests took 0.07–0.08 seconds. Ordinary charts keep their shorter initial range. A real browser click on **2Y** in the preserved ARW research report dated 2026-10-02 returned 497 bars and explicitly disclosed five earlier missing sessions; the page rendered without errors.

The enabled daily schedule next runs at 2026-10-10 05:00 UTC (01:00 New York, 08:00 Israel), when the 2026-10-09 end-of-day session is provider-ready. The original blocked report and successful replacement remain accessible.

Storage policy keeps at least 520 hot sessions with archive eviction disabled. Previously retained originals remain present as daily scans append new dates. This is an active home scheduler while Docker/the host run, not a guarantee of execution during host sleep.

## Real account-authenticated experiment

An owner-scoped experiment was activated on 2026-10-09 with USD 100,000 hypothetical cash, long-only exposure, ten-position maximum, 20% maximum target weight, zero primary fees and an additional 10-basis-point cost sensitivity. Its ledger is separate from the personal transaction journal. The existing native `gpt-6.1-sol` connection uses medium effort and a dedicated experiment session; no API-key fallback was configured.

Before the manager invocation, twelve sandbox checks passed: authentication, profile canary, secrets, private data, host env, other-task storage and `/proc` were denied; task reads/writes were allowed; writes to home, outside temporary storage and the runtime were denied. The probe opened the dedicated auth path without reading its contents. Scratch was cleaned.

The initial real manager job completed and produced an immutable, validated **hold** decision with explicit incomplete-market/company-research gaps. The hypothetical agent book remains entirely cash: no holdings and no fills. SPY and the original-rule scanner baseline are separate books. Their earliest possible future-open execution session is 2026-10-12. No future price was fabricated and no first full real valuation/fill cycle can yet be claimed.

A separate real read-only conversation inspected the experiment without selected reports, personal portfolio permission or document permission. It completed and requested one approved hypothetical equity chart. Host-rendered points contained only the actual opening balance of 100,000 on the start date. This is a starting-balance chart, not evidence of performance. Desktop and 390-pixel Chromium inspections confirmed the actual hold/cash card, visible chart and restored conversation after reload, with no page errors or horizontal overflow.

Future decisions depend on actually succeeded current live reports. Independent deterministic marks use acquired daily bars. Decisions/fills are keyed to prevent duplication; a published decision can reconcile after interruption without another model call or a retrospective fill. Failed/rejected jobs remain visible and are not automatically repeated.

## Synthetic checks

- Required scanner command: `.venv/bin/python -m unittest discover -s tests -v` — 92 passed in the existing isolated offline Docker test runtime. Scanner code did not change after that run.
- Required server command: `.venv/bin/python -m unittest discover -s apps/server/tests -v` — 103 passed against the final server source in the same offline runtime.
- Existing client Vitest suite — 10 passed.
- Web/client TypeScript checks and production web bundling passed using installed lockfile dependencies.
- Ten Playwright appearance, chat and paper fixture checks passed across desktop and iPhone-sized Chromium. Paper chart/pause fixtures intercepted requests and did not write the real experiment ledger; chat import fixtures did not write the real journal.

Server fixtures cover future-only execution, fractional-share/cash accounting, splits, missing-price refusal, unavailable valuations, constraints, rejected decision preservation, once-per-session scheduling, paper-only chat, absent-source rejection, interrupted publication reconciliation, growing-cache backfill replay, and continuous/conflicting split-reference handling. Synthetic fixture equity changes are not observed investment returns.

Installed Chrome was used because a matching managed Playwright browser binary was unavailable. Safari/WebKit, physical devices and native mobile export were not tested in this change. Linux/AMD64 runtime validation remains a subsequent acceptance task.
