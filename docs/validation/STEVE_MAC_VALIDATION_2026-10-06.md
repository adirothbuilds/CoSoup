# Validation appendix: Steve on Apple Silicon, 2026-10-06

This records local development evidence and remaining work. Steve has **not** completed an authenticated analysis. Both enablement flags remain false.

## Provenance and preservation

The workspace was initially an empty checkout. Source was recovered from the official repository archive pinned to `73f99c27e48225e7ec807f11362b3dafee2de66f`, whose application baseline is `1649a697f36f391c50d2636b556aa78a55db337b`. Existing deployed source and execution files were compared before changes.

The active project is `cosoup-dev`, with web on `127.0.0.1:8081` and API on `127.0.0.1:8080`. The interrupted setup completed, schema migration reported version 1, and web/API/PostgreSQL health checks passed. A separate browser session successfully connected to the API and displayed Steve's settings.

All 27 original master-env assignments matched their preservation hashes. The dedicated Codex authentication file also matched its preservation hash. No credential values are included in this record. Existing reports and data remain in the private deployment root. The operator's normal Codex profile was not mounted or changed. No new market-data scan, commit, or push was performed.

## Runtime correction

The native worker runs Codex CLI `0.160.0`. Under normal Compose security settings, a fresh procfs mount failed even though native user-namespace creation succeeded. The corrected outer wrapper inherits Docker's masked procfs and creates user, IPC, UTS and cgroup namespaces. It exposes runtime files, the task directory and a read-only dedicated `auth.json` in an ephemeral CLI home.

The CLI needs its own writable ephemeral home to create sandbox helper aliases. Its task tools use a separate trusted `steve` permissions profile: task files are writable, authentication and procfs are denied, and writes outside the task are denied. Tool networking, web search, apps, plugins, delegation and approval escalation are disabled. The legacy `workspace-write` preset allowed reads of the synthetic credential file and writes to temporary directories, so it was replaced.

The corrected native image built successfully as `cosoup-dev-codex:local`, image ID `sha256:6c6d16e677ed420f5e9fb6bfb00526143cb4ff42ca7aac06cb0e6da4f36f1540`. Building an image does not establish authentication or runtime isolation.

## Completed checks and limits

- Native CLI execution and dedicated login status succeeded before Docker's later startup stall. Login status reported ChatGPT authentication; no login contents were displayed.
- A synthetic runtime probe on the earlier native image, with the proposed wrapper/profile supplied explicitly, denied access to its authentication canary, other profile files, wrapper secrets, private data, host env and another task. Task reads/writes succeeded; home, temporary-directory and runtime writes were denied. Scratch was removed. This is evidence for the proposed policy, **not** verification of the rebuilt adapter with real authentication.
- All **67 server tests passed** using the changed source, Python 3.12 and the installed image dependencies. This includes real image OCR on a generated fixture, source authorization, cancellation and scratch cleanup. These are synthetic application tests, not current market-data validation or model access.
- The full **66-test scanner/deployment suite** ran in the corrected container test environment: **65 passed**, with one environment error because the runtime image does not contain `make`. The same installation test passed in the separate Mac command suite below. This is not a passing full scanner-suite run in one environment.
- The separate Mac command suite passed **7 tests** with the installed system `make` and a canonical temporary-directory path.
- Changed Python files parsed successfully, and `bash -n setup.sh` passed.

Tests in the API's 256 MB, nonexecutable temporary filesystem were unsuitable for executable fixtures and default storage reservations. Initial attempts also omitted normal home metadata or placed private fixtures inside the extracted checkout. These attempts failed and are not counted as passing validation. The final server run used a unique temporary directory in CoSoup's writable volume, with source and private test fixtures in separate sibling directories, a cleared credential environment, and automatic cleanup.

## Current blocker

Existing Docker containers remain operational. Newly created containers stalled in `Created` with no recorded start error, including a mount-free native `uname` probe and a mount-free `/bin/true` probe using the exact existing PostgreSQL image. The latter did not mount or access database data. Retrying startup did not resolve this.

Docker Desktop was not restarted because other user work depends on it. Only this task's temporary diagnostic containers were removed and its stalled Docker clients cancelled. Existing application containers, other projects and volumes were preserved.

## Remaining validation before enablement

1. Establish that a new native container can start under normal security settings, without disrupting unrelated workloads.
2. Run `tools/validate_steve_sandbox.py` inside the rebuilt worker under its actual Compose settings, first with synthetic authentication and then with `--real-auth`. The credential check only opens/closes the file; it never reads contents. Require every denied read/write check, including procfs, and successful task access.
3. Complete one bounded authenticated model request through the deployed adapter, asking its normal shell tool to execute the same synthetic probe. Verify the checks independently of model prose and verify scratch cleanup. Reuse the dedicated login; request an official device URL/code only if login status actually requires it.
4. Only after those checks, change the two master-env Steve flags, rerender configuration through setup and start the optional worker. Preserve every other setting and credential.
5. Queue one daily review of an existing authorized market report through the web app, with explicit dates and portfolio/upload permissions false. Verify the actual job succeeds, its report is readable in the app, and its task scratch is removed. Preserve reported coverage gaps.

No successful real-auth probe, authenticated model request, queued analyst job or completed Steve report is established by this snapshot.
