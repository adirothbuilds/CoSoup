# Validation appendix: end-of-day acquisition scheduling on Mac

Validated on 2026-10-09 in the existing private local development deployment.

## Diagnosed failure

The October 8 scheduled scan was enqueued at 20:30:05 UTC and began at 20:30:14 UTC, after the NYSE 20:00 UTC core close and the configured 30-minute settlement buffer. Massive rejected the October 8 grouped endpoint with HTTP 403 and the exact same-day/end-of-day entitlement error. This was provider availability after exchange close, rather than a pre-close scan. The original failed job and blocked report remain saved.

## Delivered correction

Server scan planning and market-close scheduling now share a next-calendar-day New York availability gate. The default `market_data_ready_time` is `01:00`; a verified different entitlement can explicitly configure another time or `null`. The gate is an operator policy, not an asserted publication SLA. Exact source errors still stop the scan without automatic retries.

The calendar chooses the first session whose readiness boundary is still in the future, including yesterday's session before next-day release. Holidays, early closes, weekends, DST, settlement and weekly-session selection remain exchange-calendar based. The market-context API distinguishes completed exchange sessions from provider-ready sessions. Report provenance includes separate exchange-close and provider-readiness timestamps. The web header labels the eligible date and explains the next acquisition window in a compact tooltip.

The existing enabled daily schedule was recalculated through its owner-scoped API. Its next occurrence at validation is October 10 at 05:00 UTC, October 10 at 08:00 Asia/Jerusalem, for October 9's session. Future scheduled completion requires the local deployment to remain running and is not asserted here.

## Verification

- The required scanner command passed 92 synthetic tests: `.venv/bin/python -m unittest discover -s tests -v`.
- The required server command passed 91 synthetic tests: `.venv/bin/python -m unittest discover -s apps/server/tests -v`.
- Suites used the existing offline ARM64 Docker test runtime without private data or credential mounts. Fixtures cover availability boundaries, pre-release next-run selection, early-close/weekend behavior, DST offsets, invalid configuration, legacy no-delay configuration and rejection of an explicitly unavailable scan session.
- Web/client typechecks and the production web build passed.
- Vitest passed 10 tests. Eight targeted appearance/chat browser fixtures passed with installed Chrome; their chat/portfolio mutations were intercepted. No full live workflow-suite success is claimed.
- Real Chrome inspection at 1440px and 390px confirmed the provider-ready date, localized next-window tooltip, no horizontal overflow and no runtime errors. Browser checks made no model/provider/journal writes.

## Current real data and preservation

A new authorized missing-only scan after the availability boundary completed for October 8. It acquired the one missing grouped session, used 260 cached sessions, evaluated 5,551 equities and verified 4,546 histories. Coverage remains partial: 561 insufficient histories and 444 data errors. There were no source errors, no original-rule candidates and 53 near-breakouts. This describes the verified subset under the existing rules, not an absence of opportunities.

The corrected API, scanner, scheduler and web were built from hash-identified frozen existing image bases and updated locally. PostgreSQL, the dedicated Codex worker/login and unrelated Docker workloads were not recreated. Private env/config/secret/auth files matched their preservation references; all 288 pre-existing raw cache files retained their size and modification time. The original blocked report remains accessible. The deployment validation required no migration or paid upgrade; source publication is separate from this validation.

The separate paper-portfolio document is a proposed design only. No experiment or recurring analyst task was activated by this correction.
