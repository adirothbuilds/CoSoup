# Validation appendix: local Mac handoff for connecting Steve

Snapshot: 2026-10-06. This is an operational handoff, not proof that Steve is active.

## Objective and authorization

Finish connecting **Steve**, CoSoup's optional Codex analyst, on the user's Apple Silicon Mac with Docker Desktop. Use the user's **ChatGPT account through Codex CLI**, not an OpenAI API key. Restore the interrupted deployment, build the native worker, verify its actual sandbox and model access, and complete one authorized review visible in the web app.

The user requested local Mac testing before Debian deployment, one editable private `.env`, convenient setup, and README updates. Earlier in this conversation the user explicitly authorized committing and pushing relevant fixes ("תדחוף לגיט"). Work within that scope, read `AGENTS.md`, preserve local changes, and use only the user's Git identity. Do not add Codex attribution. Current work is on `main`; do not deploy to Debian or change Tailscale as part of this recovery.

The previous agent had a failed cloud execution environment and could not run commands on this Mac. Local results below were supplied by the user; CI results were obtained directly from GitHub Actions. You now have the local access needed to finish the work. Inspect current state before acting.

## Repository and verified application baseline

- Repository: https://github.com/adirothbuilds/CoSoup
- Application baseline before this handoff document: `1649a697f36f391c50d2636b556aa78a55db337b`.
- Native Steve fix: `2c290b999e7e45a8cf7aef6a7ada7747d6b66c31`.
- CI runtime follow-up: `1649a697f36f391c50d2636b556aa78a55db337b`.
- Passing validation: https://github.com/adirothbuilds/CoSoup/actions/runs/37469719577

That CI run passed **66 scanner/deployment tests and 65 server tests**, Bash syntax, and native Codex-image builds on both ARM64 and AMD64, including architecture checks and execution of `pg_dump`, `pg_restore`, `bwrap --version` and `codex --version`. CI did **not** establish ChatGPT model access or runtime sandbox isolation on this Mac.

The initial CI run built both architectures successfully but failed one OCR test. The follow-up supplied system Python 3.12, Tesseract, Poppler and fonts to the CI test runtime; the full run then passed. Do not weaken or skip the OCR test to recover deployment.

## Local deployment

| Item | Expected value |
| --- | --- |
| Mac architecture | `arm64` |
| Docker daemon architecture | `arm64` |
| Mode / project | `dev` / `cosoup-dev` |
| Web | `http://127.0.0.1:8081` |
| API host port | `127.0.0.1:8080` |
| Private root | `$HOME/.local/share/cosoup-dev` |
| Editable configuration | `PRIVATE_ROOT/.env` |
| Dedicated Codex profile | `PRIVATE_ROOT/data/codex-profile` |
| Profile mount in worker | `/var/lib/codex-profile` |
| Downloaded source checkouts | `$HOME/.local/share/cosoup/source.*` |

On this Mac the default private root resolves to `/Users/adiroth/.local/share/cosoup-dev`. Verify the active containers' private-root labels rather than assuming a custom root was not selected.

`compose.env`, `config/server.json`, secret files and deployment metadata are generated outputs. Edit the master `.env` and rerender using setup; do not source the env as shell code or edit generated outputs to create a temporary working configuration.

Core server and PostgreSQL services remain AMD64 in the setup overlay. Web and the optional Steve worker are native ARM64. This fix does not migrate PostgreSQL to a different architecture.

## What happened, and what is established

1. The user logged in using the dedicated worker profile. `codex login status` returned:
   ```text
   Logged in using ChatGPT
   ```
   Reuse that profile. Check its current status before requesting another login. Do not copy or mount the host's normal `~/.codex` profile.

2. Bubblewrap in the original AMD64 worker failed with:
   ```text
   bwrap: Creating new namespace failed, likely because the kernel does not support user namespaces.
   bwrap must be installed setuid on such systems.
   ```
   A temporary, isolated AMD64 probe also failed after removing its seccomp filter.

3. A native ARM64 Python probe called `libc.unshare(0x10020000)` (`CLONE_NEWUSER | CLONE_NEWNS`). It returned:
   ```text
   Architecture: aarch64
   USERNS_OK
   ```
   It succeeded with normal Docker security settings and with the diagnostic seccomp override. This establishes native user/mount namespace creation for that probe. It does **not** establish all Bubblewrap namespaces, nested Codex sandboxing, authentication secrecy, or model access.

4. The repository fix made the dedicated worker native. Changes:
   - `apps/server/deploy/Dockerfile`: normalize the PostgreSQL client library from the architecture-specific source into `/pgtools/libpq.so.5.18`; install it under `/usr/local/lib` and run `ldconfig`. Remove the AMD64-only library destination.
   - `apps/server/deploy/setup.py`: generate `COSOUP_CODEX_PLATFORM` using the host architecture.
   - `apps/server/deploy/compose.setup.yaml`: use that platform for `codex-worker`.
   - `setup.sh`: clear an inherited platform override before invoking Compose.
   - Tests check architecture selection, disabled defaults and preservation of the dedicated login cache.
   - README/setup guides document login and validation.
   - `.github/workflows/server-images.yml` provides the validation described above.

5. During the user's subsequent setup update, PostgreSQL was running and migration returned:
   ```json
   {"schema_version": 1, "roles_configured": true}
   ```
   API/web were reported recreated; the other workers were still being recreated. Docker then reported:
   ```text
   Error response from daemon: cannot stop container:
   tried to kill container, but did not receive an exit event
   ```
   The update did not finish. Do not claim all application services are ready. The failed container's service has not been identified.

6. Restarting Docker Desktop through **Troubleshoot → Restart Docker Desktop**, then rerunning setup, was recommended. The user has not confirmed that recovery succeeded. Native worker build/runtime checks have not been confirmed on the Mac.

## First: recover the interrupted deployment

Inspect Docker readiness and the project without printing secrets:

```sh
docker info
docker ps -a \
  --filter label=com.docker.compose.project=cosoup-dev \
  --format 'table {{.Names}}\t{{.Status}}'
```

Identify the stuck service using targeted container metadata. Inspect its name/state and relevant project labels, not a dump of all private configuration. A daemon failure to receive an exit event is not evidence of a schema-migration failure.

If the engine is still stuck, restart Docker Desktop and wait for readiness. A Desktop restart interrupts other local containers as well. Use **Restart**, never **Clean / Purge data**, **Factory reset**, destructive pruning, or deletion of the private root. Do not start with forced removal of PostgreSQL or deletion of its storage.

Once Docker is healthy, reconcile the same mode/root. From outside an old checkout, this fetches current source and preserves the existing private deployment:

```sh
cd "$HOME"
curl -fsSL https://raw.githubusercontent.com/adirothbuilds/CoSoup/main/setup.sh \
  | bash -s -- --mode dev --no-open
```

Include the original `--root` if inspection shows a custom root. For a developer checkout, first inspect `git status` and the remote/branch; update without overwriting the user's changes. A streamed installer launched from an existing checkout can reuse that checkout, so do not assume it downloaded newer source.

Setup uses a lock directory `PRIVATE_ROOT/.setup-lock`. Investigate a stale lock only if reported, and remove it only after confirming no setup process is still running.

Require the installer to finish successfully and verify service readiness, including the web-to-API route. Rerunning migration is part of normal setup; preserve schema and role credentials.

## Then: build and inspect the native Steve worker

Find the updated checkout printed by setup. Container labels can recover the source path:

```sh
docker inspect cosoup-dev-api-1 \
  --format '{{index .Config.Labels "com.docker.compose.project.config_files"}}'
```

If the API container is absent, inspect the corresponding web container. The label contains the Compose file paths. Do not reuse a shell function that still refers to an older downloaded checkout.

From the updated repository root, define a fresh Compose helper:

```sh
cosoup_root="$HOME/.local/share/cosoup-dev"
cosoup_compose() {
  env -u SERVER_ROOT -u SCANNER_UID -u SCANNER_GID -u MODE \
    -u COMPOSE_PROJECT_NAME -u COMPOSE_PROFILES \
    -u COSOUP_WEB_PLATFORM -u COSOUP_CODEX_PLATFORM \
    docker compose --env-file "$cosoup_root/compose.env" \
      -f apps/server/deploy/compose.yaml \
      -f apps/web/deploy/compose.yaml \
      -f apps/server/deploy/compose.setup.yaml \
      --profile codex "$@"
}
cosoup_compose build codex-worker
```

Use the inspected private root if customized. The default image tag is `cosoup-dev-codex:local`. Rebuild it; an existing AMD64 image does not become ARM64 because a run flag changes.

Check current authentication without exposing credential contents:

```sh
cosoup_compose run --rm -T --no-deps \
  -e CODEX_HOME=/var/lib/codex-profile \
  --entrypoint codex codex-worker login status
```

If genuinely needed, login uses the same command prefix followed by `login --device-auth`. The user completes the browser/device-code flow privately. Do not collect or publish the one-time code.

Check native architecture and Bubblewrap using the service's actual security settings:

```sh
cosoup_compose run --rm -T --no-deps \
  --entrypoint sh codex-worker -ec \
  'uname -m
   bwrap --unshare-all --share-net --ro-bind / / /usr/bin/true
   printf "NAMESPACE_OK\n"'
```

Expected: `aarch64`, then `NAMESPACE_OK`. The read-only root bind above is solely a smoke probe running `true`, not the production analyst's mount policy.

## Required before enabling analysis

Read `apps/server/adapters/codex.py`, `apps/server/workers/codex/handler.py`, `apps/server/config.py`, and the optional-worker section of `apps/server/README.md`.

The pinned CLI is `@openai/codex@0.160.0`. The adapter uses outer Bubblewrap namespaces plus the official CLI's inner sandbox. It passes `--sandbox workspace-write`, `--ephemeral`, `--ignore-user-config`, `--ignore-rules`, JSON output/schema flags and a per-task workspace. Parent-process environment is limited to PATH/LANG; inside Bubblewrap HOME becomes `/home/agent`. The dedicated profile is mounted read-only at `/home/agent/.codex`. Model input is copied from authorized reports/documents; provider secrets and database credentials must not enter tool processes.

**Read-only is not read-denied. Do not assume workspace-write protects authentication.** Check the actual pinned CLI's filesystem permissions and test tool access. Changes to a user config file may be ignored by the adapter's flags.

Under the exact production wrapper and inner tool sandbox, prove:

- Authorized task files can be read and intended task outputs can be written.
- Tools cannot read `/run/secrets`, host/private deployment files, other task workspaces, or the dedicated auth file.
- Tools cannot write outside the task workspace.
- CLI authentication and an actual bounded model request succeed.
- Scratch is cleaned up, output is validated, and failure/cancellation remains visible.

Use synthetic canaries for private-file isolation tests where possible. For authentication access checks, test whether a tool can open the file without reading, printing or persisting its contents. Report only whether access was allowed or denied. A successful namespace probe alone is not grounds to set `CODEX_SANDBOX_VERIFIED=true`.

If any denial check fails, fix the actual permission policy or runtime adapter and retest. Do not use privileged containers, broad SYS_ADMIN capabilities, Docker-socket mounts, setuid changes suggested by a generic error, permanent seccomp disabling, or `--dangerously-bypass-approvals-and-sandbox` to enable Steve.

If runtime restrictions cannot be enforced, leave the feature disabled and report the concrete blocker. Do not claim an alternative runtime has been deployed unless it actually has.

## Activate and complete one review

Only after the above checks pass, edit the single private `.env`:

```dotenv
CODEX_ENABLED=true
CODEX_SANDBOX_VERIFIED=true
```

Preserve all other credentials/settings. Apply configuration through setup, use its resulting checkout, rebuild the worker if its code changed, and explicitly start the optional service:

```sh
cosoup_compose up -d --no-build --no-deps codex-worker
```

Default setup does not start this optional worker. Do not assume login or env flags start it.

In the web app, open **Settings → Steve** and complete one `daily_review` or equivalent authorized market-report review. Use an existing report; do not launch another full-year scan merely to test Steve. A scan previously succeeded for 2026-10-02 with partial coverage; inspect what is currently available instead of assuming it is still the latest report.

Verify the real task progresses to completion in **Activity**, produces validated analysis with source references/coverage gaps, and is readable in the UI. Use only market-report data for this initial review. Personal portfolio/document export requires separate explicit consent flags and must not be enabled automatically.

Company-source research during a scan is a different feature from Steve. Choosing `research=current` does not connect Codex. Offline scans cannot retrieve current company sources.

## Constraints and completion evidence

- Never print, commit, upload or paste `.env`, secret files, auth cache contents, tokens or provider keys.
- Keep private data outside the public repository; preserve the database, market cache, reports and dedicated login.
- No broker connections, trades or paid-plan upgrades.
- Respect the shared provider limit of five requests per minute; stop on exact provider errors, without retry loops or TLS/access bypasses.
- Keep repository code/docs/UI in English. The user can receive progress/final messages in Hebrew.
- For code changes, run `.venv/bin/python -m unittest discover -s tests -v` and the server suite with `-s apps/server/tests` when relevant. Use CI/native container checks appropriate to changes.
- Preserve this distinction: synthetic tests, native image builds, local namespace checks, enforced tool isolation, and a completed authenticated review are different evidence.

Finish with the actual local service state, architecture, auth method/status, sandbox-check results, completed review/job identifier, relevant commit/test results, and remaining blockers. Connecting Steve is complete only when an authenticated, isolated review succeeds in the deployed app. Do not stop at proposing commands when you can execute and verify them locally.
