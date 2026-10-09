#!/usr/bin/env bash
# Works from a checkout or as an HTTPS curl bootstrap. Never sources private env.
set -euo pipefail
umask 077

usage() {
  cat <<'HELP'
CoSoup setup — Docker Desktop on macOS, Docker Engine on Linux
Usage: ./setup.sh [--mode dev|prod] [--root PRIVATE_DIRECTORY]
                  [--origin HTTPS_ORIGIN] [--ref GIT_REF]
                  [--action deploy|status|logs|down] [--no-open] [--copy-token]

Defaults: dev on macOS, prod on Linux; ~/.local/share/cosoup-MODE.
Edit only PRIVATE_DIRECTORY/.env and rerun to apply configuration.
Docker/Compose must already be installed and running. No host Node, Python
packages, Xcode, Make or sudo are required for deployment.
HELP
}
fail() { printf 'CoSoup setup: %s\n' "$*" >&2; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || fail "Required command '$1' is not installed"; }

mode=""; private_root=""; origin=""; ref=main; action=deploy; open_browser=1; copy_token=0
while [ "$#" -gt 0 ]; do
  case "$1" in
    --help|-h) usage; exit 0 ;;
    --mode|--root|--origin|--ref|--action)
      [ "$#" -ge 2 ] || fail "Missing value for $1"
      case "$1" in
        --mode) mode="$2" ;; --root) private_root="$2" ;; --origin) origin="$2" ;;
        --ref) ref="$2" ;; --action) action="$2" ;;
      esac
      shift 2 ;;
    --no-open) open_browser=0; shift ;;
    --copy-token) copy_token=1; shift ;;
    *) fail "Unknown option $1; use --help" ;;
  esac
done
case "$(uname -s)" in
  Darwin) os=mac; mode="${mode:-dev}" ;;
  Linux) os=linux; mode="${mode:-prod}" ;;
  *) fail "Supported operating systems are macOS and Linux" ;;
esac
case "$mode" in dev|prod) ;; *) fail "Mode must be dev or prod" ;; esac
case "$action" in deploy|status|logs|down) ;; *) fail "Unknown action" ;; esac
[ "$(id -u)" -ne 0 ] || fail "Run as your non-root deployment account, with Docker access"
architecture="$(uname -m)"
case "$architecture" in
  x86_64|amd64) ;;
  arm64|aarch64) [ "$os" = mac ] || fail "The current server image requires amd64; ARM Macs use Docker Desktop emulation" ;;
  *) fail "Unsupported architecture $architecture" ;;
esac

need docker
endpoint="${DOCKER_HOST:-$(docker context inspect --format '{{.Endpoints.docker.Host}}')}"
case "$endpoint" in unix://*) ;; *) fail "Select a local Docker socket, not a remote Docker context" ;; esac
docker_os="$(docker info --format '{{.OperatingSystem}}')" || fail "Start Docker Desktop/Engine and check Docker access"
if [ "$os" = mac ]; then
  case "$docker_os" in *Docker\ Desktop*) ;; *) fail "Select your local Docker Desktop context" ;; esac
fi
docker compose version >/dev/null

# Resolve a checkout. A streamed installer downloads source to a new directory,
# preserving any earlier checkout and all private deployment data.
script_source="${BASH_SOURCE[0]:-}"
if [ -n "$script_source" ] && [ -f "$script_source" ]; then
  checkout="$(cd "$(dirname "$script_source")" && pwd -P)"
elif [ -f ./setup.sh ] && [ -f ./apps/server/deploy/setup.py ]; then
  checkout="$(pwd -P)"
else
  need curl; need tar
  [[ "$ref" =~ ^[A-Za-z0-9][A-Za-z0-9._/-]*$ ]] || fail "Invalid source ref"
  source_parent="${COSOUP_SOURCE_PARENT:-$HOME/.local/share/cosoup}"
  mkdir -p "$source_parent"
  checkout="$(mktemp -d "$source_parent/source.XXXXXX")"
  archive="$(mktemp "$source_parent/archive.XXXXXX")"
  trap 'rm -f "$archive"' EXIT
  printf 'Downloading CoSoup source (%s)…\n' "$ref"
  curl --fail --show-error --location --proto '=https' --tlsv1.2 \
    "https://codeload.github.com/adirothbuilds/CoSoup/tar.gz/$ref" -o "$archive"
  tar -xzf "$archive" --strip-components=1 -C "$checkout"
  rm -f "$archive"
  trap - EXIT
  # Use the checkout's script for the selected ref, rather than mixing versions.
  forwarded=(--mode "$mode" --action "$action")
  [ -z "$private_root" ] || forwarded+=(--root "$private_root")
  [ -z "$origin" ] || forwarded+=(--origin "$origin")
  [ "$open_browser" -eq 1 ] || forwarded+=(--no-open)
  [ "$copy_token" -eq 0 ] || forwarded+=(--copy-token)
  exec bash "$checkout/setup.sh" "${forwarded[@]}"
fi
[ -f "$checkout/apps/server/deploy/setup.py" ] || fail "This checkout has no setup implementation"
cd "$checkout"

private_root="${private_root:-$HOME/.local/share/cosoup-$mode}"
case "$private_root" in /*) ;; *) private_root="$PWD/$private_root" ;; esac
case "$private_root" in *","*|*"'"*|*$'\n'*) fail "The private path cannot contain commas, single quotes or newlines" ;; esac
if [ "$action" != deploy ]; then
  [ -d "$private_root" ] || fail "No deployment exists at $private_root"
fi
mkdir -p "$private_root"
private_root="$(cd "$private_root" && pwd -P)"
case "$private_root" in /|/tmp|/workspace|"$HOME") fail "Choose a dedicated private root outside the checkout" ;; esac
case "$private_root/" in "$checkout/"*) fail "Choose a dedicated private root outside the checkout" ;; esac

# Canonical env controls Compose; stale exported settings must not override it.
compose_environment=(env)
for key in SERVER_ROOT SCANNER_UID SCANNER_GID MODE COMPOSE_PROJECT_NAME COMPOSE_PROFILES COSOUP_WEB_PLATFORM COSOUP_CODEX_PLATFORM COSOUP_SERVER_PLATFORM \
  BIND_ADDRESS SERVER_PORT WEB_BIND_ADDRESS WEB_PORT API_WORKERS \
  POSTGRES_MEMORY POSTGRES_CPUS API_MEMORY API_CPUS SCANNER_MEMORY SCANNER_CPUS \
  SCHEDULER_MEMORY SCHEDULER_CPUS IMPORT_MEMORY IMPORT_CPUS STORAGE_MEMORY STORAGE_CPUS \
  WEB_MEMORY WEB_CPUS CODEX_MEMORY CODEX_CPUS; do
  compose_environment+=(-u "$key")
done
compose() {
  "${compose_environment[@]}" docker compose --env-file "$private_root/compose.env" \
    -f "$checkout/apps/server/deploy/compose.yaml" \
    -f "$checkout/apps/web/deploy/compose.yaml" \
    -f "$checkout/apps/server/deploy/compose.setup.yaml" "$@"
}
if [ "$action" != deploy ]; then
  [ -f "$private_root/compose.env" ] || fail "Run deployment first"
  case "$action" in
    status) compose ps ;; logs) compose logs --tail 100 --follow ;; down) compose down ;;
  esac
  exit 0
fi

lock="$private_root/.setup-lock"
mkdir "$lock" 2>/dev/null || fail "Another setup holds $lock; investigate a stale lock before removing it"
trap 'rmdir "$lock" 2>/dev/null || true' EXIT
printf 'Preparing CoSoup %s on %s. Private configuration: %s/.env\n' "$mode" "$os" "$private_root"
docker build --platform linux/amd64 --target base \
  -f apps/server/deploy/Dockerfile -t cosoup-setup:local .
prepare_options=(--host-root "$private_root" --mode "$mode" --uid "$(id -u)" --gid "$(id -g)" --architecture "$architecture")
[ -z "$origin" ] || prepare_options+=(--origin "$origin")
docker run --rm --platform linux/amd64 --user "$(id -u):$(id -g)" \
  --mount "type=bind,src=$private_root,dst=/private" --entrypoint python \
  cosoup-setup:local -m apps.server.deploy.setup "${prepare_options[@]}"

compose config --quiet
# Refuse to redirect an existing project to a different database/data directory.
container_ids="$(compose ps -aq)"
if [ -n "$container_ids" ]; then
  for container_id in $container_ids; do
    mounted_root="$(docker inspect --format '{{index .Config.Labels "com.cosoup.private-root"}}' "$container_id")"
    [ "$mounted_root" = "$private_root" ] || fail "The selected Compose project already uses another private root"
  done
fi
compose build api web
compose up -d --wait --wait-timeout 180 postgres
compose run --rm -T migrate
compose up -d --no-build --no-deps --force-recreate --wait --wait-timeout 180 \
  api scheduler scanner-worker import-worker storage-worker web
compose ps

# Probe the actual web -> API route from inside Docker, without a host dependency.
compose exec -T web wget -Y off -q -O /dev/null http://127.0.0.1:8080/api/v1/health/ready
url="$(cat "$private_root/.browser-origin")"
printf '\nCoSoup containers are ready. Browser origin: %s\n' "$url"
printf 'Edit only %s/.env, then rerun this setup to apply changes.\n' "$private_root"
printf 'Checkout: %s\nOwner token file: %s/secrets/api_token\n' "$checkout" "$private_root"
printf 'Online scans require your actual MASSIVE_API_KEY in that env file.\n'
if [ "$mode" = prod ]; then
  printf 'Production browser access also requires your trusted HTTPS reverse proxy (for example Tailscale Serve).\n'
fi
if [ "$os" = mac ]; then
  if [ "$copy_token" -eq 1 ]; then
    pbcopy < "$private_root/secrets/api_token"
    printf 'Owner token copied to clipboard. Paste into Connect, then clear your clipboard.\n'
  else
    printf 'To copy the owner token: pbcopy < "%s/secrets/api_token"\n' "$private_root"
  fi
  if [ "$open_browser" -eq 1 ] && [ "$mode" = dev ]; then
    open "$url"
  fi
fi
