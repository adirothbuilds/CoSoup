# CoSoup on Debian with Mac/iPhone access over Tailscale

Run the complete Docker stack on Debian and publish its loopback web/API port through **Tailscale Serve**. Mac browsers, iPhone Safari and the native iOS app use one trusted HTTPS origin. SSH is for administration; application access continues after SSH closes.

```text
Mac / iPhone -> HTTPS over Tailscale -> Tailscale Serve on Debian
             -> 127.0.0.1:8081 -> web -> /api/v1 -> API and workers
```

## Prepare the server

Use an amd64 Debian host with Docker Engine/Compose v2 and a non-root deployment account with Docker access. Install/configure Tailscale on the server and both clients. See the official [Docker Debian guide](https://docs.docker.com/engine/install/debian/) and [Tailscale Linux guide](https://tailscale.com/kb/1031/install-linux).

Check:

```sh
uname -m
docker compose version
tailscale status
tailscale serve status
timedatectl status
```

Enable MagicDNS and HTTPS certificates in tailnet settings. Allow the Mac/iPhone identities to reach this Debian node on TCP 443, or the alternate HTTPS port you choose. SSH permission alone does not grant HTTPS permission. Use the node's full DNS name from Tailscale, for example `https://YOUR-NODE.YOUR-TAILNET.ts.net`, and keep the VPN connected. Tailscale's public certificate hostname can appear in certificate transparency while service access remains private to the tailnet.

## Deploy with one env

From this checkout on Debian:

```sh
./setup.sh --mode prod --origin https://YOUR-NODE.YOUR-TAILNET.ts.net
```

Setup initializes `~/.local/share/cosoup-prod/.env`, credentials and private data, builds images, migrates PostgreSQL and waits for the container web/API route. To use another private directory, add `--root /absolute/path` consistently. Existing manual deployments are preserved; choose a separate new root for this installer.

Privately edit **only that `.env`** for the Massive key, optional R2 values, resource/storage limits or other server settings, then rerun setup. The JSON configuration and secret files are generated outputs. See [one-command setup](SETUP.md) for all fields and the curl bootstrap. Dev tests on the Mac use a separate `cosoup-dev` root; personal production journal data are not copied into that test deployment.

Keep default listeners on loopback. The installer does not provision HTTPS itself. Inspect existing Serve configuration, then, if port 443 is available for this service:

```sh
tailscale serve status
sudo tailscale serve --bg http://127.0.0.1:8081
tailscale serve status
```

If the CLI supplies an HTTPS enablement URL, complete that tailnet configuration and rerun. `--bg` persists background Serve configuration independently of SSH. Ensure Docker and `tailscaled` start on boot. If your env uses a different `WEB_PORT`, point Serve at that loopback port.

If another app occupies 443, preserve it and choose a supported unused HTTPS port, for example:

```sh
sudo tailscale serve --bg --https=8443 http://127.0.0.1:8081
```

Set `BROWSER_ORIGIN=https://YOUR-NODE.YOUR-TAILNET.ts.net:8443` in the production env, rerun setup and allow that port in tailnet policy. Keep `BROWSER_SECURE_COOKIE=true`. No router port forwarding, public Funnel or public application endpoint is needed. PostgreSQL is not published.

## Connect from Mac and iPhone

With Tailscale enabled on the Mac:

```sh
curl --fail https://YOUR-NODE.YOUR-TAILNET.ts.net/api/v1/health/ready
open https://YOUR-NODE.YOUR-TAILNET.ts.net
```

Use the exact hostname and port you configured. Copy the generated owner token privately through your existing verified SSH connection, without displaying it. Replace the SSH target and private root as appropriate:

```sh
ssh DEPLOY_USER@DEBIAN_NODE 'cat ~/.local/share/cosoup-prod/secrets/api_token' | pbcopy
```

Paste into Owner token, connect and clear the clipboard. Close SSH and verify that the web app still works. Tailscale network access and the full-owner application token are separate requirements.

On the iPhone, enable Tailscale and open the same HTTPS URL in Safari. Use your private credential-transfer method for the same production owner token. A normal publicly trusted Tailscale HTTPS certificate should not require a custom CA profile. Safari needs no Xcode/Expo build.

For the native app, use the [Mac build guide](MACOS_LOCAL.md), then enter the same trusted HTTPS origin and token. Credentials are stored in Keychain. A physical device also needs access to the Mac's Metro server while developing; that is separate from the Debian API connection. A phone cannot reach a Mac loopback IP.

## Check the system and manage it

Create a disposable fixture portfolio and confirm that both devices see its journal. Try a CSV upload, follow Activity and explicitly confirm reviewed proposals. Preview market coverage and run an initial online scan if the provider key is configured; an empty deployment has no cache, and initial ingestion can take over an hour under the shared rate limit. Check dated report quality/gaps separately from job success. Finally close SSH and the Mac browser, then reopen on the iPhone to verify independent server operation.

From the deployed checkout:

```sh
./setup.sh --mode prod --action status
./setup.sh --mode prod --action logs
./setup.sh --mode prod --action down
./setup.sh --mode prod
```

Use the same `--root` for a custom location. Stopping retains private data. An installed CoSoup command can manage the recorded deployment with `cosoup status`, `cosoup logs`, `cosoup down` and `cosoup deploy`. Keep automatic schedules disabled until manual runs and dependencies work. R2 needs real bucket access; Steve needs dedicated Codex login and verified isolation; the server does not implement scheduled report mail.

If loopback works but HTTPS fails, check Serve, DNS/HTTPS enablement and tailnet access to the selected port. If only the iPhone fails, check its VPN/account and exact URL. If the UI loads but Connect fails, check the exact env origin, secure cookies and owner token, then rerun setup after changes. Follow exact import/scan job errors rather than resubmitting blindly.

This is a deployment procedure, not evidence of a completed test on your own Debian host, VPN or iPhone. See [validation provenance](VALIDATION.md).
