# Validation appendix: SEC contact identification on Mac

Validated on 2026-10-08 in the existing local development deployment. This follows the earlier SEC/chat validation; its HTTP 403 observation describes the earlier configuration rather than the final access state recorded here.

## Diagnosis and authorized change

The original SEC ticker mapping request and a single diagnostic from the scanner worker returned HTTP 403 with an Akamai HTML page containing “Request Rate Threshold Exceeded.” This wording alone did not prove that CoSoup exceeded a request limit. The app's shared persistent budget remained at most five provider requests per minute.

Both exact diagnostic URLs subsequently returned HTTP 200 and valid JSON in installed visible Chrome on the Mac, using its normal identity and an isolated profile. Browser cookies, user profiles, impersonation and retries were not used. The phone screenshot supplied by the user showed the data.sec.gov landing page over cellular access; it did not establish the JSON endpoint behavior on the Mac.

The user explicitly approved the existing Git contact for SEC identification. Both SEC clients now read a validated application/contact header from the same private configuration. Setup renders SEC_USER_AGENT from the master private env into a readonly sec_user_agent file mounted only into the scanner worker. The address is absent from public source, reports, Compose environment and model context. Missing, unreadable or invalid configuration stops before a source request or rate-budget reservation. Header validation rejects control characters, excessive length and no-reply identification; errors never echo the supplied contact. Manual initialization creates an empty mount file and preserves any already configured identity.

A live request from the updated worker then returned HTTP 200 and JSON. This sequence supports the identification correction; it does not establish that identification was the only possible cause of the earlier denial. Neither the VPN nor Docker Desktop network configuration was changed.

## Network investigation limits

A read-only macOS check found a connected VPN service. Static routes to the resolved SEC endpoints used physical interfaces, and host/worker DNS results overlapped. These checks do not prove identical public egress, IPv6 paths or Docker Desktop forwarding behavior.

Automatic approval review rejected an IP comparison via ipify because it would send network metadata to a third-party destination without explicit authorization for that disclosure. That operation was not performed or retried. The investigation continued with local routing/DNS checks and authorized SEC access validation. No complete public-address comparison is claimed.

## Validation and preservation

The required scanner suite passed 80 tests and the server suite passed 78 tests on final source (158 total). Tests used an isolated ARM64 container with synthetic fixtures, no network, and no deployment data or credentials.

Both clients were tested for consistent identity, private-file precedence over ambient values, invalid-header rejection without disclosure, and stopping without a source request when configuration is unavailable. Setup tests verify readonly-private configuration separation, preservation of other credentials and compatibility with manual initialization.

Every pre-existing master env value and credential file, the generated server configuration and dedicated Codex authentication file matched their preservation hashes after the change. Only SEC_USER_AGENT and its private contact file were added. All 278 checked pre-existing market files and all original reports remained intact; expected request-ledger updates and new SEC cache files were excluded from this preservation comparison. The scanner worker was the only service recreated. PostgreSQL, API, web, Codex worker and unrelated workloads stayed running. No commit or push was performed.

## Filing selection correction

Real coverage review found that ARW's annual filing existed in the cached recent-history metadata but fell outside the 40 displayed filing links. Annual and quarterly document selection now occurs before truncating that display list. A crowded synthetic history verifies that both filing types are selected while the displayed links stay bounded. This is a discovery correction; no broader historical crawl was added.

## Completed real-data sync and UI

The first account-free SEC sync completed with 17 source requests, financial facts for AVT and ARW, three filing documents and two comparable snapshots for each selected institutional manager. Coverage inspection exposed the crowded-list annual-document issue described above. After the tested discovery correction, the final sync reused the authorized daily cache and fetched one additional annual filing.

Final saved coverage:

- Two requested companies, both with financial facts: 80 metric/period observations for AVT and 72 for ARW.
- Four cached filing documents: annual 10-K and quarterly 10-Q for each company.
- Two requested managers, both with holdings: two quarter-end snapshots each, with 30 reported share-count changes for Berkshire Hathaway and 12 for Pershing Square.
- No source errors. The job succeeded; report quality remains partial_coverage because custom accounting tags/notes and broader company/manager coverage are outside this bounded sync. Snapshot differences are not verified trades or returns.

Read-only real-data browser inspection passed on desktop and mobile layouts. It selected ARW, verified that the erroneous annual-document gap disappeared, rendered financial and institutional charts, and found no horizontal overflow or runtime errors. No synthetic data, portfolio writes, model calls or extra source requests were used for this UI check. Personal contact and private task/report identifiers remain outside this appendix.

## References

SEC access identification follows [Accessing EDGAR Data](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data). Public data APIs require no login or API key, as described in [EDGAR APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces). Selected institutional snapshots retain the timing and coverage limits of [Form 13F](https://www.sec.gov/rules-regulations/staff-guidance/frequently-asked-questions-about-form-13f).
