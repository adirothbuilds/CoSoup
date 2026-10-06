# CoSoup web research workspace

The responsive React application connects to the private FastAPI server. It provides daily report review, a movement list with an optional interactive 3D map, daily OHLC candles, historical scans, portfolio journaling and reviewed imports, persistent job activity, schedules, retention controls and an optional natural-language analyst.

## Run and deploy

Use Node 24 LTS and the root lockfile. Install with `make install`, check with `make test`, and build with `make build`. `make web-dev` starts Vite with a same-origin `/api` proxy to the API; set `SCANNER_DEV_API` when its address differs.

For Docker, first follow the [server provisioning guide](../server/README.md). Root commands combine the server and web Compose files:

```sh
make init PRIVATE_ROOT=/srv/stock-scanner TIMEZONE=Asia/Jerusalem
# Privately provision provider/R2 settings, host quota and HTTPS before enabling them.
make config COMPOSE_ENV=/srv/stock-scanner/compose.env
make deploy COMPOSE_ENV=/srv/stock-scanner/compose.env
make status COMPOSE_ENV=/srv/stock-scanner/compose.env
make logs COMPOSE_ENV=/srv/stock-scanner/compose.env SERVICE=scheduler
make down COMPOSE_ENV=/srv/stock-scanner/compose.env
```

Run initialization as the dedicated non-root service user with ownership of the private root. `make deploy` builds images, starts PostgreSQL, applies explicit role grants and starts services. `make down` retains data and volumes. Configure `WEB_BIND_ADDRESS`, `WEB_PORT` (default 8081), `WEB_MEMORY` and `WEB_CPUS` in private `compose.env`; the API's independent automation port defaults to 8080. Only bind a LAN/VPN interface after configuring the host firewall. The web container has no data mounts or provider/model credentials.

Terminate trusted HTTPS at your private home reverse proxy and forward its private origin to the web port. That origin serves both static UI and `/api/v1`. Set these fields in private `config/server.json`, then recreate the API:

```json
{
  "browser_origin": "https://scanner.home.example",
  "browser_secure_cookie": true,
  "browser_session_hours": 12
}
```

Use your actual private hostname, not the example. Certificates must be trusted by iPhone and desktop clients. Configure the external proxy's upload ceiling consistently with the API and nginx. The packaged proxy permits a 20 MB upload plus multipart overhead; raising the server upload limit also requires raising nginx `client_max_body_size` and rebuilding the web image. Preserve streaming and disable caching for API responses. No public tunnel, DNS provisioning or certificate issuer is activated by deployment.

Enter the private owner token in Connect. The API exchanges it for a revocable HttpOnly, Secure, SameSite cookie; the form clears the token and stores no credentials in localStorage. Mutations require the session CSRF token and exact configured Origin. Native/automation Bearer authentication remains available. Rotating the owner token and restarting the API invalidates previous sessions. At most 16 owner sessions are retained. Cookie sessions require no new schema version: their digests/expiry live in the existing owner-scoped policy table.

For loopback-only development, explicitly configure `browser_origin` to the exact HTTP origin (for example `http://127.0.0.1:5173`) and `browser_secure_cookie:false`. This exception rejects non-loopback origins. It is unsuitable for iPhone/LAN deployment. There is no private API response caching or offline write replay; installation/service-worker support is deferred.

## Read the visualizations

- Choose Portfolio, Candidates or Near breakouts. Reports retain their original session, signal mode and data quality. The portfolio scope uses the latest completed session and symbols from its supplied journal at that session's close.
- Map height means signed percentage price change: 1D compares the preceding session's close, 1W five intervals, 1M 21. All tiles currently have equal footprints. Position-sized tiles are deferred until complete dated valuation/reconciliation supports trustworthy weights. Values above 10% retain exact labels but have capped rendered heights. The scene shows at most 12 symbols; the bounded list shows at most 100 and discloses the total.
- Select a stock to inspect daily OHLC candles and volume. SMA50/SMA200 use available warmup. The breakout line uses the selected report's level. Missing expected sessions are gaps. Candle color compares open to close; map color compares the selected period's starting and ending closes.
- Chart windows span 21/63/252 sessions within the server's 260-session cache. Indicators earlier in the window may lack sufficient warmup. Split-adjusted price movement excludes dividends and is not a portfolio or trading return. Relative strength remains a separate screening-window metric in percentage points versus SPY.

Research defaults to the latest usable daily report, with a visible notice if a newer scan is blocked. Explicit report links still open their selected report, including blocked reports. Run time in UTC (or a stable run identifier for older reports) distinguishes same-date reports. Changing report/scope clears the previous symbol until that scope loads. Research opens in List mode; select **3D** to open the movement map. The 3D renderer loads on demand, uses a fixed camera and has a complete list fallback when WebGL is unavailable. Mobile uses touch controls and a focused stock detail area. An accessible daily-price table accompanies the canvas chart. Technical charts and research never substitute demo prices for unavailable market inputs.

## Research and operations

Home puts the current daily report first. Open **Make a fresh serving** for date-coverage preview and scan submission, and **Saved servings** for report history, JSON/Markdown downloads and weekly summaries. Company research remains an explicit choice. Selecting **Current sources** or **Dated sources** turns offline off; switching offline on selects technical screening only. The API rejects offline requests that also request company research. Online runs fetch only missing days under the shared provider rate limiter. Reports record whether research was disabled, prevented offline, blocked, completed or completed with source gaps. Older reports without this field retain their original warning and are labeled without inventing a cause. Historical/live signals remain labeled separately in report content. Full rejected-security detail remains a server extension; aggregate filtering reasons and research gaps are available now.

If a scan fails with `scan_blocked`, open its Activity entry and inspect **Scan diagnostics** for the saved report's status and exact errors. This also works for existing failed jobs whose progress does not contain a report ID. Resolve the reported source/cache/quality issue before resuming; a blocked report does not establish an absence of opportunities.

Portfolio supports actual entries, unknown opening basis, fees, splits and auditable corrections. Imports accept CSV, JPEG/PNG and PDF, display source evidence/proposals, and require explicit confirmation of edited rows. The review editor is currently structured JSON, including unresolved fields; a richer row editor is a future UX improvement. No extracted or model-proposed record is automatically applied.

Activity shows failure reasons in its list and opens failed-job details and event history. It follows persisted jobs/events, cancels cooperatively and resumes stopped work explicitly after its cause is resolved. SSE refreshes job state, with bounded polling fallback and refresh on visibility restoration. Lists paginate in batches of 100; event responses show their bounded first page and expose the API cursor for later history.

Settings (the existing `#more` URL remains supported) provides schedules/occurrences, retention policy, archive/restore jobs, immutable rule versions, preferences and analyst tasks. Scheduler execution belongs to the home server, not the browser. Secret files, host kernel settings, SMTP and Codex runtime verification remain operator configuration. The server still requires a mail delivery adapter before it can send scheduled reports.

## Appearance and the kitchen

The header offers light/dark mode and a global animation pause. The initial theme follows the device; explicit choices persist using only `cosoup.theme` and `cosoup.motion` in localStorage. Device reduced-motion settings always take priority. Theme colors also apply to candles and the optional 3D map.

Steve tosses illustrative stock symbols while scan, summary or analysis jobs run. A newly published report triggers the serving pose. **Let him cook** plays a decorative animation without submitting work. The kitchen does not supply market prices, candidate counts or completion estimates; those come from dated reports and persisted jobs. Errors and coverage gaps retain their exact diagnostics.

The bowl mark uses a small Blender-rendered WebP loop; Steve uses local cel artwork with a Canvas animation. Animations pause offscreen or while the page is hidden, and the global pause replaces the bowl loop with a still image. Assets are self-hosted and require no external media service. See the [editable animation source and Blender commands](../../tools/mascots/README.md).

## Natural-language analysis and vision

The analyst can preview a versioned context packet even when Codex is disabled. Packets expose dated reports, typed source IDs, signal modes, metric definitions and explicit gaps. Portfolio-derived reports/ledger require separate export consent. Up to four authorized JPEG/PNG images can be attached for vision; explicit image-export consent is required before the model service receives them. PDF/CSV use the reviewed OCR/import path. Camera/photo workflows also exist in the [Expo client](../mobile/README.md).

When the analyst is unavailable, **How to connect Steve** explains private server setup; structured context preview remains available. Queued model tasks require the dedicated Codex runtime to be enabled and operator-verified. This flag is not a live connectivity check. The wrapper validates/re-encodes images into bounded private task files, removes metadata, attaches them with the official CLI image option, validates cited source IDs and deletes scratch. Vision output remains research evidence, not verified journal entries. See the [agent contract](../../docs/AGENT_API.md).

## Request timing

Client requests have a 30-second deadline covering headers and body parsing; connecting uses 15 seconds and multipart uploads allow 120 seconds. A timeout aborts the client wait and explains that durable server jobs can continue. Cached movement/report/chart errors expose **Try again**. Mutations are never resubmitted automatically; an unchanged manually repeated action retains its idempotency key. Check Activity before resubmitting work whose acceptance is uncertain. This browser deadline does not cancel a server job.

Provider connection/read timeout is 15 seconds. The persistent maximum of five requests per minute and 13-second spacing remain unchanged. Exact failures stop acquisition without automatic retries; resolve the cause and resume explicitly.

## Browser verification

Against a disposable private server with cached daily reports:

```sh
SCANNER_TEST_ORIGIN=https://scanner.test.example \
SCANNER_TEST_TOKEN_FILE=/private/test-secrets/api_token \
make test-e2e
```

Provision Playwright browsers separately. `SCANNER_CHROMIUM_PATH` selects an installed Chromium; `SCANNER_TEST_WEBKIT=1` additionally enables WebKit. The suite exercises real API workflows and creates fixture portfolios/jobs in that server. It disables traces/video/screenshots to avoid recording credentials or private source content. Chromium's iPhone viewport checks responsive layout; WebKit and a real iPhone Safari pass remain distinct validation steps.

TradingView Lightweight Charts is used under Apache-2.0. Retain its copyright/license and visible TradingView attribution link/logo. Three.js and React Three Fiber retain their dependency licenses. Source MIT licensing does not authorize distribution of market data.
