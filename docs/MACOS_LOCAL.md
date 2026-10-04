# Run and test CoSoup on a Mac

Install and start Docker Desktop, then deploy from the checkout with one command:

```sh
./setup.sh --mode dev --copy-token
```

The web app opens at `http://127.0.0.1:8081`; paste the owner token from the clipboard into Connect and clear the clipboard. Intel and Apple Silicon Macs are supported by the setup configuration. The server uses amd64 emulation on Apple Silicon and the web image is native. No host Python/Node development dependencies are needed for this Docker deployment.

Edit only `~/.local/share/cosoup-dev/.env`, then rerun that command. It generates the internal configuration/secret mounts and retains the database, reports and credentials. Add your actual `MASSIVE_API_KEY` there only when testing online acquisition. See the [complete setup guide](SETUP.md) for env fields, dev/prod selection, curl bootstrap and management commands.

## Acceptance checks before using the Debian server

1. Connect, create a disposable test portfolio and record an actual-style fixture journal entry.
2. Upload a small CSV, follow its import in Activity and explicitly review/confirm proposed rows. They must not enter the journal before confirmation.
3. Preview market date coverage. A new installation has no report/candle cache. Select online acquisition for its initial scan; the UI's offline default requires existing dated inputs.
4. Follow durable job progress. Initial 260-session ingestion can take over an hour under the shared five-request-per-minute limit. Stop on errors and correct the cause before an explicit resume.
5. Read report dates, quality and declared gaps separately from job completion. Missing data is not proof of an empty opportunity set.
6. Close/reopen the browser and verify retained journal/job state. Stop/start with `setup.sh --mode dev --action down` and a normal setup rerun to check retained data.

The local HTTP exception is loopback-only. Physical iPhone/native testing requires trusted HTTPS, such as the [Debian/Tailscale origin](DEBIAN_TAILSCALE.md); a phone cannot reach the Mac's `127.0.0.1`. Safari over the tailnet is the quickest device check and needs no app build.

## Development tools and native builds

For source editing, TypeScript/unit checks, Vite or native Expo builds, install the separate development tools:

```sh
brew install python@3.12 node@24 tesseract poppler
export PATH="$(brew --prefix node@24)/bin:$(brew --prefix python@3.12)/bin:$PATH"
make install-command
export PATH="$HOME/.local/bin:$PATH"
cosoup install
cosoup test
cosoup build
cosoup ios-export
```

A full Xcode installation and selected iOS Simulator runtime are needed for `cosoup ios-build`. iOS export is only a JS/assets bundle. Physical-device builds require your intended signing identity and a reachable Metro server during development. The native app connects to the same trusted HTTPS origin and stores its owner token in Keychain.

For Vite live editing, set `BROWSER_ORIGIN=http://127.0.0.1:5173` in the dev env and keep `BROWSER_SECURE_COOKIE=false`. The one-command dev deployment requires the origin to match its packaged web port, so use the documented [manual development configuration](../apps/web/README.md) in a separate private root for Vite rather than changing the setup-managed packaged origin. Keep credentials out of frontend build variables.

For automated browser acceptance checks, use a disposable setup with cached reports and exact dated market inputs:

```sh
npx playwright install chromium
SCANNER_TEST_ORIGIN=http://127.0.0.1:8081 \
SCANNER_TEST_TOKEN_FILE="$HOME/.local/share/cosoup-dev/secrets/api_token" \
cosoup test-e2e
```

The suite creates fixture journals/jobs. Chromium's iPhone viewport is a layout check; WebKit and real Safari/native devices need separate validation. R2, Codex authentication/isolation and scheduled mail are not established by these local checks. See [validation records](VALIDATION.md).
