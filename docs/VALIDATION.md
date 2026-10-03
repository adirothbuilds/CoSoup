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
