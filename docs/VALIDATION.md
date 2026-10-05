# Validation

## Reproducible checks

Run the scanner regression suite independently of optional server dependencies:

```sh
.venv/bin/python -m unittest discover -s tests -v
```

Install `apps/server/requirements.txt`, then run:

```sh
.venv/bin/python -m unittest discover -s apps/server/tests -v
```

Server tests cover API ownership/authentication, range planning, durable job leases/idempotency, scheduler holidays/DST, portfolio arithmetic and corrections, reviewed imports, reservations and encrypted archive verification/restore. Fake object stores and analysts exercise adapters without claiming live R2 or model access.

For the web/native workspaces, install the committed lockfile with Node 24 LTS and run:

```sh
make typecheck test-client build ios-export
```

`ios-export` validates bundling, not native execution or signing. Use a Mac with Xcode for `make ios-build`, then exercise trusted HTTPS, Keychain, image/document pickers, permissions, suspension and recovery on an iPhone.

Functional browser tests require a disposable private server with cached daily reports and active scanner/import workers:

```sh
SCANNER_TEST_ORIGIN=https://scanner.test.example \
SCANNER_TEST_TOKEN_FILE=/private/test-secrets/api_token \
make test-e2e
```

The suite creates fixture journals/jobs. Provision Playwright browsers separately or select installed Chromium with `SCANNER_CHROMIUM_PATH`; enable additional WebKit tests with `SCANNER_TEST_WEBKIT=1`. Traces, video and screenshots are disabled in the suite to avoid recording private inputs. A Chromium iPhone viewport is not native iOS or Safari validation.

Validate Docker configuration and build the service image. On a private test deployment, execute migrations, authenticate through HTTP, submit a scan and inspect its persisted report/coverage. Restart a worker to check checkpoint recovery. Validate actual R2 upload/read/hash/restore and dedicated Codex isolation/authentication before enabling their production workflows. Test consistent database backup restoration on an empty instance before enabling eviction.

Actual source checks should compare SPY and IWM against independent histories across the entire configured window. Grouped and ticker-history endpoint volumes can differ; use a consistent volume source and preserve differences as evidence. Check forward/reverse splits with real corporate actions and synthetic price-times-volume invariance.

A passing unit suite cannot establish provider entitlements, historical depth, licensing, durable host operation or mail receipt. Classify passed, failed, blocked and unrun checks separately. Validation provenance belongs in the appendix rather than installation/product documentation.

## Appendix: validation records

The initial scanner validation used Python 3.12 on an x86_64 Linux cloud runner. Its 49 regression tests passed. A real 260-session window, 2025-09-22 through 2026-10-02, was cached and scanned. The scan evaluated 5,559 equities with 4,553 valid histories, 599 insufficient histories and 407 data errors; its quality was `partial_coverage`.

SPY/IWM OHLC matched independent histories over all 260 sessions. Maximum volume differences were approximately 1.8242% and 1.6899%, across 53 and 55 sessions. A real NFLX 10-for-1 split was checked; prices matched within approximately 4.44e-7 relative error in a 135-session subwindow. These are bounded checks, not certification of every provider record.

During that validation, the supported financial and earnings endpoints returned HTTP 403 entitlement denials. The free primary-source and terms-site checks were blocked by proxy policy. They did not establish current debt, cash flow, earnings or distribution rights. No paid upgrade was performed.

Server implementation validation on 2026-10-03 used Python 3.12, Docker Engine 28.4, Compose 2.40.3 and PostgreSQL 17 on the same x86_64 Linux runner. The 49 scanner regression tests and 34 server tests passed (83 total). Server tests included actual Tesseract image extraction, FIFO/corrections/atomic oversell rejection, market-close valuation, invalid bars, missing split reconciliation, independent archive recovery, cancellation of a database-dump child, encrypted round trips and failure retention. Object-store/model tests used fixtures, not external credentials.

The base and optional Codex Docker targets built with TLS/signature verification intact. The build runner required its existing outbound proxy, an explicit DNS mapping and a mounted public CA certificate; these were build-only inputs, not repository credentials or disabled verification. Compose syntax passed. A later rebuild exhausted the runner's 32 GB overlay with Docker VFS snapshots: npm emitted `ENOSPC` while exiting successfully. The affected image was discarded; known superseded images and unused reproducible build cache were removed without touching volumes or private source data. The exact Codex stage was then rebuilt against the verified server image, and its newly required build-time `codex --version` check passed. Real PostgreSQL migrations/service-role grants, authenticated host HTTP requests and eight simultaneous distinct queue claims passed. A private Compose deployment ran the API, scheduler and scanner/import/storage workers. A one-shot schedule executed through its worker and remained a single persisted occurrence after scheduler restart; the completed scan also survived service recreation. Adding a separate API ingress bridge fixed host port publication when the API was otherwise attached only to an internal bridge.

Through HTTP and the scanner worker, an exact-cache historical snapshot for 2026-10-02 used all 260 real market sessions. It persisted JSON/Markdown with `partial_coverage`, 5,559 selected equities and AVT/ARW as two candidates. It registered two reconstructed signals and zero live signals. Historical weekly generation declared the four absent daily reports. CSV upload/extraction left the fixture journal unchanged pending review; repeated explicit confirmation returned the same transaction IDs and FIFO positions. Portfolio valuation used cached same-date SPY bars. Those journal inputs were synthetic integration fixtures, not the owner's actual account.

A consistent PostgreSQL custom dump was generated by the storage worker, encrypted into an archive and verified through a local fixture object store. Independent recovery without the catalog also unpacked the encrypted real dump and passed `pg_restore --list`. The dump restored successfully into a new PostgreSQL database, preserving the expected report, transaction, signal and schema counts. This validates logical backup/restore and the packaging path; it does not establish an actual R2 transfer, disaster recovery of post-backup records, or home-host quota enforcement.

The dedicated image reported `codex-cli 0.160.0` and supported the configured terminal flags. Its namespace probe failed with: `bwrap: No permissions to create new namespace, likely because the kernel does not allow non-privileged user namespaces.` Codex remained disabled; no authenticated model task ran and no isolation bypass was used. Its real tool sandbox, dedicated-auth protection and host kernel compatibility remain unverified.

No real R2 credentials/bucket, SMTP delivery or 200 GB filesystem quota were connected. A durable home-host deployment, live R2 upload/read/hash/restore, licensing review and authorized Codex sandbox/authentication are outstanding deployment checks. Temporary test processes do not establish continuous scheduling.

### Web, iOS and agent integration, 2026-10-03

Checks used Python 3.12, Node 24, PostgreSQL 17 and system Chromium 151 on the x86_64 Linux runner. All 49 scanner, 47 server and six shared-client tests passed (102 unit/contract tests). Server checks include cookie expiry/revocation/CSRF/token rotation, exact decimal transport, split-adjusted OHLCV/indicators, missing-session quality, historical split cutoffs, report-artifact candidate scope, reusable multi-symbol chart history, cold split-reference identifiers and completed-week context dates. Image tests decode real PNG fixtures with Pillow, normalize authorized vision attachments, validate CLI image paths and confirm task scratch removal; the analyst adapter is a fixture, not a live model.

All web/native/shared TypeScript checks passed. The production web build passed. Expo SDK 57 exported an iOS Hermes JavaScript/assets bundle successfully (857 modules, approximately 2.5 MB). No macOS simulator, real iPhone, native permission flow, signing, IPA, App Store or EAS build was tested.

Eight Playwright workflows passed against the actual private Compose API/PostgreSQL/scanner/import services, using desktop and iPhone-sized Chromium viewports. Checks exercised cached research movement/candles, responsive overflow, date-coverage preview, durable offline scan submission/reload, exact journal quantities, audited correction, CSV extraction/explicit confirmation and structured agent context while Codex remained disabled. Private visual inspection additionally exercised the real WebGL scene and responsive camera framing. Browser installation from `cdn.playwright.dev` was blocked with HTTP 403 (`Domain forbidden`); the installed Chromium was used without changing network policy. WebKit and real Safari remain untested.

The web/server Dockerfiles built successfully with TLS verification intact, and private Compose migrations, health checks and root Makefile start/status/config commands passed. Final runtime source/static changes were applied to those built images through private cached refresh layers. Docker VFS exhausted the runner's 32 GB storage during earlier builds; only superseded task containers/images and unused reproducible build cache were removed. Private volumes and source data were retained. Home-host deployment/resource limits still require their own verification.

Real cached 260-session data was read through the visual API and scanned through the worker: the latest report remained `partial_coverage`, dated 2026-10-02, with 5,559 selected equities, 4,553 valid histories, 599 insufficient histories, 407 data errors and two candidates (AVT/ARW). The AVT chart returned 260 validated bars. Market context returned 2026-10-02 and the next eligible close run on 2026-10-05 at 20:30 UTC (16:30 New York). This integration reused the previously fetched real cache; it did not repeat provider entitlement or licensing checks. Journal/import fixtures were synthetic.

`codex exec --help` confirmed the configured image/structured-output/ephemeral flags without an authenticated model call. The existing namespace restriction still prevents proving the dedicated analyst runtime on this runner. Structured context and normalized vision input preparation passed; natural-language model answers, actual image understanding and home-host sandbox compatibility remain unverified. Live R2, SMTP/mail delivery, home HTTPS and durable home scheduling were not connected by these client changes.

### Mac and Debian/Tailscale setup guides, 2026-10-04

Fetched `origin/main` and synchronized the checkout to `6c6f6c208054e7dd4e46e48baaa5987e740256ff` before preparing the local Mac and Debian/Tailscale guides. On the managed x86_64 Linux runner, Python 3.12.14 and Node 24.19.0 passed 49 scanner tests, 47 server tests and six client tests, all TypeScript workspace checks, production web bundling and iOS Hermes/assets export (857 modules). Python dependency consistency passed. The initial npm install could not write the inherited home cache; installation succeeded with a separate writable task cache, preserving package integrity checks and the lockfile.

Every shell block in both guides passed Bash syntax validation. Both combined Compose configurations passed `config --quiet` using newly initialized disposable private files; the Mac override selected amd64 for configured server/database services. Settings validation accepted the documented secure HTTPS origin and loopback HTTP development origin. The pinned PostgreSQL image index includes amd64 and arm64, but the server Dockerfile's explicit x86_64 library-copy path still requires the documented amd64 server build.

No new Docker runtime deployment, provider acquisition, Playwright run, macOS build/simulator, physical iPhone run or Tailscale Serve connection was performed for these documentation changes. The selected cloud executor had no configured VPN; the user's Debian host, tailnet HTTPS/DNS/access policy and device reachability remain operator acceptance checks. R2, model execution and mail were not activated.

### CoSoup command and application naming, 2026-10-04

Added a real checkout-aware `cosoup` executable and user-bin symlink installation, replacing the setup guides' shell-only helper. Six command regression tests passed: installed invocation outside the checkout, override forwarding to Compose and Make, missing-override rejection, child exit-code propagation, dependency-free help, and repeatable installation that preserves an existing user command. The full Python suites passed 55 scanner/command tests and 47 server tests; six client tests also passed (108 total). All workspace TypeScript checks, the web production build and iOS assets export passed after the CoSoup display-name changes.

Both real launcher paths (`config` and `compose config --quiet`) validated the disposable private Mac configuration from outside the checkout. A dry run of the recursive Make deployment preserved the Mac override in all four Compose operations. Updated guide shell blocks passed syntax validation. These checks did not build/start Docker services or verify the user's VPN/device runtime; existing application identities, database/storage paths and default deployment selection were retained for compatibility.

### OS-aware one-env setup and bootstrap, 2026-10-04

The final Python suites passed 64 scanner/launcher/bootstrap tests and 58 server tests (122 total). Setup coverage includes initial private env creation, literal/non-executed env parsing, repeated deployment credential/data retention, generated secret mount scoping, prod HTTPS requirements, separate mode/project identities, missing-credential rejection, protected PostgreSQL admin/archive keys, and preservation of existing manual deployments. Shell orchestration used fixture Docker/curl commands to simulate Intel/Linux and Apple Silicon/Desktop paths, migration failure, project/root collision, remote-context rejection, status-only operation, optional clipboard/browser opening, and downloading/delegating to the selected source ref.

Real Docker Compose validation passed for both generated dev/arm64-Mac and prod/amd64-Linux configurations, with the intended project names, image/platform selection and private-root labels. Final launcher regressions passed after filtering stale exported Compose variables for managed deployments. Bash syntax, updated README/guide command blocks, the non-secret env example and whitespace checks passed.

No real setup image build or stack deployment was performed for this installer change. Fixture orchestration does not establish actual Docker Desktop emulation, macOS Bash execution, source URL publication, trusted HTTPS, the user's Debian host, VPN/device reachability or provider/model/R2 access. The remote curl installer becomes available only after its source is committed and published to the selected GitHub ref. No provider request, enabled schedule, paid/model integration, commit or push was performed during these checks.

## Streamed-installer migration correction, 2026-10-04

An operator's macOS Docker Desktop run built the server/web images and started PostgreSQL, then stopped before migration with `the input device is not a TTY`. Setup now passes `-T` to `docker compose run --rm migrate`. The streamed-bootstrap regression models Docker rejecting TTY allocation with non-terminal stdin and verifies that successful migration is followed by application startup. All 64 scanner/launcher/bootstrap and 58 server tests passed (122 total); Bash syntax and whitespace checks also passed.

An isolated amd64 Linux Docker integration used real PostgreSQL 17, the setup Compose overlay, private generated credentials and non-terminal stdin. The runner's Compose 2.40.3 automatically adapts default TTY allocation, so the reported error was reproduced using an explicit `--tty` request. Migration with `-T` succeeded, as did a repeated migration. PostgreSQL, API, web, scheduler and the scanner/import/storage workers all ran; API/web reported healthy and the web-to-API readiness probe passed. The integration reused cached server/web images with current server source overlaid, rather than rebuilding the full dependency toolchain. Fixture containers were removed afterward. This checks the corrected Compose operation on Linux, not execution on the operator's Mac or native ARM support. No market scan, enabled schedule or external provider/model/R2 request was submitted.

## Failed scan report diagnostics, 2026-10-04

A failed scan previously persisted a blocked report without checkpointing its report ID, and Activity showed only `scan_blocked`. The worker now retains the report reference before failing and removes replaced blocked references during resume. The owner-scoped report list accepts a job filter; Activity uses it to show the blocked report's status and exact saved errors, including for existing jobs without report IDs in progress.

All 64 scanner/launcher/bootstrap tests, 59 server tests and six shared-client tests passed (129 total). Regression coverage checks that blocked source diagnostics remain available, resumed scans retain valid report references without resubmitting completed dates, and job-filtered reports preserve owner isolation. All workspace TypeScript checks and the production web build passed. These are synthetic source failures against the local test database, not validation of the operator's Massive entitlement, credential or failed scan. No external provider request was made.

## Cached movement loading and latest-report refresh, 2026-10-05

Movement snapshots now read only the required 2, 6 or 22 trading sessions for 1D, 1W or 1M. Candlestick history retains its separate 260-session indicator window; a short movement cache cannot replace it. Valid full-chart columns can serve a shorter movement request, while an error confined to an older bar triggers a fresh short-window read. Report lists order same-date reports by artifact publication time with a stable ID tie-breaker. Shared workspace queries refresh reports after terminal job changes, and Home uses the recorded candidate count while displaying blocked counts as unavailable.

All 64 scanner/launcher/bootstrap tests, 63 server tests and six shared-client tests passed (133 total). Regression checks cover equal-date ordering and pagination, period-bounded reads with split adjustments, complete candle history after a short movement request, full-history cache reuse, missing-symbol quality and exclusion of old out-of-range bar errors. All workspace TypeScript checks and the production web build passed.

Two Chromium workflows passed against the current web source and an actual disposable FastAPI/SQLite server, at desktop and iPhone-sized viewports. An explicitly completed synthetic job published an existing cached daily report; Home refreshed from an older blocked report to its partial-coverage report and recorded two-candidate count without a page reload. Research loaded all three movement periods and daily candles, retained correct report selection, avoided horizontal overflow and stored no browser credentials in localStorage. The fixture reused private copies of previously acquired real market inputs; it did not acquire new data or run a new provider-backed scan. Browser traces, videos and screenshots were disabled.

On this native x86_64 Linux runner, cold matrix reads for the same two cached symbols took 5.377 seconds for 260 sessions, 0.054 seconds for 2, 0.128 seconds for 6 and 0.457 seconds for 22. These measurements explain the reduced work but do not establish latency on the operator's Mac/Docker Desktop amd64 emulation or directly reproduce its nginx 504. No actual Mac, physical iPhone/Safari, provider, R2, SMTP or model connection was tested by this change.

## Warm web appearance and animated kitchen, 2026-10-05

All 64 scanner/launcher/bootstrap tests and six shared-client tests passed. All TypeScript workspace checks and production web bundling passed. Six Playwright checks passed against a disposable actual FastAPI/SQLite server: desktop and iPhone-sized Chromium exercised theme persistence, global pause, device reduced motion, credential-free localStorage preferences, cached research movement and daily candles.

Two additional browser workflows exercised the production bundle with the packaged nginx Content Security Policy, loaded local assets, changed themes, persisted pause through reload, played the decorative cooking loop, and loaded all movement periods, candles, optional WebGL and analyst context preview. A synthetic job completed by publishing an existing cached report; the Home kitchen changed from cooking to serving and the recorded candidate count refreshed. Browser inspection checked desktop and phone layout, responsive overflow and unavailable candidate counts for blocked reports. Private screenshots contain only the disposable fixture and were kept outside the public repository. No new provider scan or model request was submitted.

Blender 4.3.2 rendered all 48 transparent bowl frames on CPU; FFmpeg exported the two-second animated WebP and its static poster. Steve's existing original generated cel artwork was optimized into local WebP assets. The kitchen's total image payload is approximately 580 KB, with no remote media dependencies. The early theme script remains external to preserve the existing script-src self policy.

These checks used Linux Chromium, including an iPhone-sized viewport, rather than a physical Mac, iPhone or Safari. The optional analyst remains subject to its existing configured and verified runtime requirements. Bowl rendering was verified in Blender; continuous home scheduling and external model/provider/R2/mail integrations were not exercised by the appearance change.
