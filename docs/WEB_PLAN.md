# Client architecture and design scope

The React web application and Expo/React Native iOS application share the private FastAPI server, domain contracts, query behavior and design tokens. Their platform views remain separate. See the [web guide](../apps/web/README.md), [iOS guide](../apps/mobile/README.md) and [agent contract](AGENT_API.md) for installation and operational details.

## Product direction

Use an English, dark graphite workspace with teal/coral movement colors, readable numbers and restrained motion. Home, Research, Portfolio, Activity and More form the primary navigation. Desktop uses a sidebar; small screens and iOS use bottom navigation, stacked cards and focused stock details. Keep technical diagnostics under disclosure controls while preserving visible data dates, coverage and signal origin.

The software serves one owner through LAN/VPN with private trusted HTTPS, while retaining owner boundaries for future separation. Server jobs and schedules continue independently of open clients. No broker connection, order execution, fabricated market prices or paid upgrade workflow is included.

## Linked movement and daily candles

Research links Portfolio, Candidates and Near breakouts to a stock overview, selected-stock daily chart and source-backed report details. Missing inputs, partially covered reports and an empty shortlist remain separate states. Screening strength and observed signal changes are never presented as account/trading returns.

The web overview is a static isometric WebGL scene with an accessible selection list and fallback. Signed column height means close-to-close percentage price change; all footprints currently have equal size. A visible zero plane, color and numeric labels explain direction. The camera frames the rendered bounds for the viewport. There is no ambient rotation, particle animation or hover-only control. Rendering is on demand, pixel ratio is bounded and the renderer loads only when used.

Periods use one, five and 21 trading-session intervals for 1D, 1W and 1M. The API supplies actual starting/ending sessions, a split-adjusted basis and per-symbol quality. Unknown movement is unavailable, never zero. The scene shows at most 12 symbols and the list at most 100, with total/subset labels. Heights above 10% are capped visually while exact values remain visible. Selecting a list entry or tile selects the same daily candle chart.

Each candle represents one completed exchange session. Volume uses a separate aligned panel; SMA50/SMA200 and the selected report's breakout level provide technical context. Visible windows cover 21/63/252 sessions inside the cached 260-session window, with available warmup explicitly bounded. Holidays have no candles; missing expected sessions stay gaps. Candle color compares close with open, while overview color compares period closes. The chart includes dated OHLC/volume and a readable daily-price table.

Price and volume share a documented split-consistent basis with a session cutoff. Later split events are not applied to an earlier historical chart. References retrieved/revised later remain labeled rather than certified as information known at that historical time. Price movement excludes dividends. Raw journal execution prices and deterministic FIFO accounting remain separate from technical chart prices.

The native application uses React Native controls, SVG daily candles and a 2D movement list. The web scene is not embedded in a WebView. Native 3D remains a separate future renderer.

## Application boundaries

```text
apps/web/
  src/app/                    # Session lifecycle, page navigation, layout
  src/components/             # Web controls and disclosure/action helpers
  src/features/overview/      # Reports and scan preview/submission
  src/features/research/      # Linked scope, stock selection and evidence
  src/features/market-scene/   # Web-only 3D renderer
  src/features/charts/        # Lightweight Charts adapter
  src/features/portfolio/     # Journal, corrections and import review
  src/features/activity/      # Persisted jobs/events
  src/features/operations/    # Schedules, storage, rules and analyst
  deploy/                     # Static image, same-origin nginx proxy
  tests/                      # Real private-server browser workflows
apps/mobile/
  src/                        # Native connection, screens and query integration
  src/components/             # Native controls and SVG candles
packages/client/
  src/                        # Transport, contracts, metric helpers and query hooks
packages/design/
  src/                        # Shared colors, spacing, touch targets and navigation
```

React Query shares query/refresh semantics. Platform credential adapters implement HttpOnly browser sessions versus native Keychain-backed Bearer authentication. Financial decimal values remain exact strings at the transport boundary; the server is authoritative for accounting. Web uses Vite, Three.js/React Three Fiber and TradingView Lightweight Charts. Native uses Expo, SecureStore, document/image pickers and React Native SVG.

The static web container has no provider, model or R2 credentials and no private data mounts. It proxies `/api/v1` to the existing API on the same origin, preserving streaming and upload limits. Private origin, ports, TLS and host firewall settings are deployment configuration. PostgreSQL and workers retain their isolated existing mounts and resource limits. Root Makefile commands build, migrate and start the persistent Docker services sequentially.

## Authentication and persistent work

The web exchanges an entered owner token for an expiring/revocable Secure, HttpOnly, SameSite cookie. Mutations require exact Origin and session CSRF checks. The form clears the token, and credentials/private API content are not stored in browser localStorage or an offline service-worker cache. Insecure cookies are supported only for explicitly configured loopback development.

Native credentials live in the iOS Keychain using a device-only when-unlocked policy. Requests use trusted HTTPS and Bearer authentication. Report/journal/query state is held in memory. Disconnect clears credentials/query state, and app visibility restoration refreshes authoritative state. There is no silent offline mutation replay.

Scan submission follows a date-coverage preview and stable idempotency key. Activity shows persisted jobs, errors and bounded events; cancellation is cooperative and stopped jobs resume only explicitly. Web uses cookie-authenticated SSE with bounded polling fallback. Browser/native suspension never owns the scheduler.

## API mapping

All paths use `/api/v1`.

| Capability | Routes |
| --- | --- |
| Browser connection | `POST/GET/DELETE /auth/session`, `/me` |
| Scan preview/submission | `/scan-plans`, `/scans`, `/market/coverage` |
| Reports and weekly review | `/reports`, `/reports/{id}/content`, `/weekly-summaries` |
| Dated visual data | `/market/context`, `/market/tickers/{symbol}/bars`, `/market/movement-snapshots` |
| Journal and corrections | `/portfolios`, `/portfolios/{id}/positions`, `/portfolios/{id}/transactions`, `/transactions/{id}/corrections` |
| Reviewed uploads | `/uploads`, `/imports`, `/imports/{id}/confirm`, `/imports/{id}/reject` |
| Durable activity | `/jobs`, `/jobs/{id}/events`, `/jobs/{id}/events/stream`, cancellation/resume routes |
| Schedules | `/schedules`, run-now and occurrence routes |
| Storage | `/storage/status`, `/storage/policy`, `/storage/artifacts`, `/storage/archives`, archive/restore jobs |
| Agent research/vision | `/agent/profiles`, `/agent/context`, `/agent/tasks` |
| Rules and capabilities | `/rules`, `/me`, `/system/status` |

Cached visual routes do not call the provider. Cold artifacts and missing split/reference data require restore or ingestion through the existing server workflows. Browser gestures never generate provider requests. Capability flags distinguish disabled, configured and operator-verified states; they do not prove model connectivity, archive delivery or host quota enforcement.

Agent context is a bounded versioned packet with dated reports, source IDs, signal modes, metric semantics, optional authorized ledger and image metadata. Context preview does not invoke a model. Separate export consent governs portfolio-derived data and vision images. The worker normalizes bounded JPEG/PNG attachments, cites authorized source IDs and removes task scratch. PDF/CSV use reviewed OCR/import; no model-proposed journal entry is applied automatically.

## Remaining product and deployment work

Original document preview, richer transaction/trigger editors, full native pagination, a dedicated signal-history screen, position-sized map tiles, native 3D, a light theme, resizable desktop panes and static app-shell installation remain extensions. Imports currently use editable structured JSON. Web lists paginate; native lists label their bounded pages. Research exposes aggregate filtering reasons, with a complete rejected-security drilldown left to a future bounded endpoint.

Native signing and execution require a Mac/Xcode and the intended signing identity. Linux iOS export only bundles JS/assets. Real iPhone Safari/native permission, accessibility, suspension and graphics tests remain necessary. No App Store distribution, push notification service or native background scheduler is provisioned.

Operator setup must establish private HTTPS, dedicated Codex authentication/namespace isolation, live R2 verification and durable home-host limits/scheduling. Mail requires the server's missing delivery adapter. Passing client tests does not establish those connections. Reproducible checks and actual validation provenance are documented in [Validation](VALIDATION.md).
