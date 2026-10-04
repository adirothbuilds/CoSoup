# One-command CoSoup setup

`setup.sh` deploys the complete Docker stack from one private `.env` file. It detects the OS, defaults to `dev` on macOS and `prod` on Linux, and keeps each mode's database, credentials and data separate.

## Prerequisites

- macOS: Docker Desktop installed, running and selected as the local Docker context. Intel and Apple Silicon are supported; the current server image uses amd64 emulation on Apple Silicon, while the web image is native.
- Linux: an amd64 host with Docker Engine and Compose v2 installed and running, and a non-root account authorized to use Docker.
- Deployment needs Bash and the OS's basic command-line tools. The streamed bootstrap additionally needs curl and tar. Host Python packages, Node, npm, Make, Xcode and a Python virtual environment are not needed to deploy.

Docker/Desktop installation itself can require OS permissions and interactive setup, so the script checks those prerequisites instead of attempting to replace your Docker installation. ARM Linux is not supported by the current server Dockerfile. Docker Desktop sleep/shutdown pauses local scheduling.

## Start a Mac development deployment

From this checkout:

```sh
./setup.sh --mode dev --copy-token
```

The script builds its initializer image, generates private credentials, configures loopback browser access, builds the server/web images, starts PostgreSQL, migrates the database, starts the API/scheduler/workers/web, waits for health and probes the web-to-API route. On macOS it opens `http://127.0.0.1:8081`. `--copy-token` privately copies the owner token to the Mac clipboard: paste it into Connect, then clear the clipboard. Omit the flag if you prefer another private credential-transfer method. `--no-open` suppresses opening the browser.

The default private root is `~/.local/share/cosoup-dev`. The only file you edit is:

```text
~/.local/share/cosoup-dev/.env
```

Repeated setup applies that env, rebuilds changed images and recreates application services while preserving data and generated credentials. It stops on exact errors; failed migration does not start the application workers. No scan or enabled schedule is submitted automatically.

## Configure the one env file

After the first deployment:

```sh
open -e "$HOME/.local/share/cosoup-dev/.env"
./setup.sh --mode dev
```

Put your actual authorized provider key in `MASSIVE_API_KEY` inside that editor for online market acquisition. It starts empty; setup never imports an ambient cloud/network-proxy key. Leave it empty for journal/import/configuration tests. Do not put the value in a CLI argument, Git or chat.

| Env fields | Purpose |
| --- | --- |
| `MODE`, `COMPOSE_PROJECT_NAME` | Stable deployment identity. Dev and prod use different roots and projects. |
| `TIMEZONE` | Host-intended IANA scheduling zone; default `Asia/Jerusalem`. |
| `SERVER_PORT`, `WEB_PORT`, bind addresses | Host listeners; defaults 8080/8081 on loopback. |
| `BROWSER_ORIGIN`, `BROWSER_SECURE_COOKIE` | Exact browser origin and session security. Dev requires its matching loopback HTTP origin; prod requires trusted HTTPS. |
| `MASSIVE_API_KEY` | Privately configured provider key for online scans. |
| `API_TOKEN`, role `*_DATABASE_PASSWORD` values | Generated on first setup. Preserve them on later runs. |
| `ARCHIVE_KEY_BASE64` | Generated 32-byte archive encryption key encoded as base64. Preserve a separate recovery copy. |
| `R2_ENDPOINT`, `R2_BUCKET`, `R2_ACCESS_KEY`, `R2_SECRET_KEY` | Optional private object-store credentials and settings. |
| Resource values such as `SCANNER_MEMORY`, `SCANNER_CPUS` | Optional Compose container limits. |
| `LIMIT_*` values | Optional validated application admission/retention limits, such as `LIMIT_CAPACITY_BYTES`. |

The [env example](../deploy/setup.env.example) documents common fields with empty credential placeholders. Setup also accepts unprotected server settings using their uppercase JSON field names, and `LIMIT_` plus the uppercase limit name. Container-internal data/credential paths are fixed. Quote values containing spaces. Env contents are parsed as data, with no shell execution or variable expansion.

The app's private `server.json`, `compose.env`, secret files and metadata are **generated outputs** of the one env. Do not edit those outputs for setup-managed deployments. Only the initializer sees all credentials; each service receives its existing limited secret mounts. The master env and derived files are private and outside Git. Normal reruns do not rotate credentials. Editing the PostgreSQL admin password is rejected because its existing database password would not change automatically; archive-key changes are rejected to preserve recovery. API token rotation requires updating its env value and rerunning setup, which recreates the API and invalidates previous sessions.

If changing the local web port, update `WEB_PORT` and its matching `BROWSER_ORIGIN` together. To run dev and prod on the same machine at the same time, choose distinct host ports as well as separate roots/projects. The 200 GB default storage admission budget does not allocate that space or enforce a filesystem quota; available disk space is checked and OS/images/logs need their own space.

## Prepare the Debian production deployment

Use a separate production root and the actual trusted HTTPS hostname that your reverse proxy will serve:

```sh
./setup.sh --mode prod --origin https://YOUR-NODE.YOUR-TAILNET.ts.net
```

The default root is `~/.local/share/cosoup-prod`, with its own `.env` and project. If prod is started without an origin, setup creates the env and stops with an instruction to set `BROWSER_ORIGIN`; fill it and rerun. `--origin` seeds a new env and does not replace an existing configured origin.

Keep the listeners on loopback when using Tailscale Serve. After checking that no existing Serve service occupies HTTPS 443:

```sh
tailscale serve status
sudo tailscale serve --bg http://127.0.0.1:8081
```

MagicDNS, tailnet HTTPS and access to the chosen HTTPS port must be enabled. From Mac/iPhone on the tailnet, open the same full HTTPS origin and connect with the production owner token. The native client also uses that origin. See [Debian and Tailscale](DEBIAN_TAILSCALE.md).

Prod setup does not install a reverse proxy, configure a certificate issuer or activate a public endpoint. Its health checks establish the local container route, not remote HTTPS reachability. R2 still needs the actual bucket configuration, and optional Codex analysis requires dedicated login and verified sandbox isolation; it is excluded from the default service start. SMTP delivery is not implemented by the server. A dev success does not establish production provider, model, storage or device access.

## Curl bootstrap

The same setup can download its own source and run without a prior clone:

```sh
curl -fsSL https://raw.githubusercontent.com/adirothbuilds/CoSoup/main/setup.sh \
  | bash -s -- --mode dev --copy-token
```

For Debian:

```sh
curl -fsSL https://raw.githubusercontent.com/adirothbuilds/CoSoup/main/setup.sh \
  | bash -s -- --mode prod --origin https://YOUR-NODE.YOUR-TAILNET.ts.net
```

Use the same immutable commit in the raw URL and `--ref COMMIT_SHA` to select a fixed version. The bootstrap downloads source over verified HTTPS into a new private checkout under `~/.local/share/cosoup`, preserves earlier checkouts and deployment data, and delegates to that version's setup script. It prints the downloaded checkout path. It does not reset an existing developer checkout. When selecting a different ref, ensure it includes `setup.sh`.

If an older installer stopped after starting PostgreSQL with `the input device is not a TTY`, rerun the curl command above to use the corrected installer. Database migration now explicitly disables TTY allocation, so it works through a pipe. Reuse the same mode and private root: setup preserves the existing database, env and credentials and continues with migration and application startup. For a custom root, include the same `--root` argument when rerunning.

## Manage the deployed stack

From the checkout printed by setup, use:

```sh
./setup.sh --mode dev --action status
./setup.sh --mode dev --action logs
./setup.sh --mode dev --action down
./setup.sh --mode dev
```

Use `--mode prod` on the server. `down` retains private data. A custom root is selected consistently with `--root /absolute/private/path`. A new root must not be pointed at the same project as another existing database; setup checks existing container root labels before replacing services. An older manual deployment without a setup env is preserved and requires a new root for this installer.

If Python 3 and the CoSoup command are installed, these equivalents are available:

```sh
cosoup setup --mode dev
cosoup deploy-mac
cosoup status
cosoup logs
cosoup down
cosoup deploy
```

After setup, the launcher discovers the default OS/mode root and uses its recorded project and setup overlay. `cosoup deploy` reruns env rendering for a managed installation. Custom roots require `cosoup --private-root /absolute/path ...`. Legacy manual deployments retain their existing command behavior. Installing the optional command uses `make install-command`; deploying with `setup.sh` needs neither that installation nor host Python.

See [Mac acceptance checks](MACOS_LOCAL.md) and [validation provenance](VALIDATION.md) for what has actually been tested.
