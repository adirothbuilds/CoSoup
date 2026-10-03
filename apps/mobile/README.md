# Expo iOS client

Native React Native views use the same private server and shared API/domain packages as the web application. The app implements connection, daily/historical scan preview/submission, report review, candidate/near-breakout/portfolio movement, daily OHLC candles, journal entries/corrections, reviewed document imports, persistent job activity, schedule/retention controls and natural-language analyst context/vision requests.

## Development and native builds

From the repository root, use Node 24 LTS and the committed npm lockfile:

```sh
make install
make typecheck
make ios-export
make ios-start
```

`ios-export` produces a local iOS JavaScript/Hermes asset bundle under `apps/mobile/dist`; it is not an IPA, signed application or simulator test. `ios-start` runs the Expo development server on the local network. The Debian host runs the API and durable workers; it does not require Expo to remain active in production.

On a Mac with Xcode and the intended signing identity:

```sh
make ios-build
```

Review/change the example `ios.bundleIdentifier` in `app.json` before signing. Native generated `ios/` and `android/` folders are ignored; Expo config and plugins reproduce them. No EAS build, paid service, App Store upload, signing identity or distribution credentials are provisioned. Install on a real iPhone and test photo/document picking, camera permission, keyboard, safe areas, rotation, network loss and app suspension before treating the native app as deployment-ready. Expo Go, when compatible with the pinned SDK, is a development option rather than the distributed app.

## Connect and protect private data

Enter the actual trusted HTTPS origin of your private web/API reverse proxy and the private owner token. Origin input rejects HTTP, embedded credentials, paths, query strings and fragments. The device must have LAN/VPN connectivity and trust its TLS certificate. Local-network permissions explain access to your private server. Native requests use Bearer authentication; browser cookies/CSRF are not used.

Credentials are stored only with Expo SecureStore using the iOS Keychain's when-unlocked, device-only policy. No token is a build variable, source constant, deep-link query or AsyncStorage value. Disconnect removes the credential and clears query state. Authentication failures clear the session. iOS Keychain can persist through reinstall; remove/rotate credentials explicitly when retiring a device. A server URL is configured per installation, not committed as a personal endpoint.

API/report/portfolio state is held in memory, with no persistent offline report cache or automatic offline mutation replay. App visibility restoration refreshes server state. Scan/jobs/scheduling continue on the server after suspension. Uploaded files are handled by platform pickers; image/model export requires explicit consent, and import confirmation remains a separate owner action.

## Shared contracts and platform views

| Package | Shared behavior |
| --- | --- |
| `packages/client` | Typed requests/responses, validated chart/movement contracts, errors, exact decimal transport, period/chart semantics, safe source/origin parsing and React Query hooks |
| `packages/design` | Colors, spacing, radii, touch targets and navigation vocabulary |

Native controls and SVG candles are platform-specific components. The web uses DOM, WebGL and Lightweight Charts. The initial native overview is a 2D movement list; the web 3D scene is not embedded in a WebView. Native 3D is a separate future renderer. Each native candle represents one completed session, with gaps for missing expected sessions, volume and available SMA overlays.

Operational/review editors currently use structured JSON where complex row/trigger editors would add scope. Reports/journal/jobs show bounded pages and label their limits; full pagination, original document preview and a dedicated signal-history screen can use future UI adapters without changing accounting. Agent packets preserve facts/hypotheses/source gaps from reports and never turn observed signals into trading returns.
