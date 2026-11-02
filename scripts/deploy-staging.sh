#!/bin/sh
set -eu

: "${REGISTRY_URL:?Set REGISTRY_URL}"
: "${REGISTRY_USER:?Set REGISTRY_USER}"
: "${REGISTRY_TOKEN:?Bind the registry credential}"
: "${REGISTRY_KAMPAN_IMAGE:?Set the exact image tag built by Jenkins}"
: "${CFG_FILE:?Bind INVENTORY_ENV_DEVELOPMENT}"

# Config must survive Jenkins workspace cleanup and container restarts.
config_dir="${KAMPAN_STAGING_CONFIG_DIR:-$HOME/.config/kampan/staging}"
mkdir -p "$config_dir"
chmod 700 "$config_dir"
export KAMPAN_CFG_FILE="$config_dir/kampan-development.cfg"
install -m 600 "$CFG_FILE" "$KAMPAN_CFG_FILE"
# Flask loads this Python config after environment variables. Apply internal
# service addresses here so web, worker and controller all use this stack.
printf '\nMONGODB_HOST = "mongodb"\nREDIS_URL = "redis://redis:6379/0"\n' >> "$KAMPAN_CFG_FILE"

DOCKER_CONFIG=$(mktemp -d)
export DOCKER_CONFIG
trap 'rm -rf "$DOCKER_CONFIG"' EXIT HUP INT TERM
printf '%s' "$REGISTRY_TOKEN" | docker login -u "$REGISTRY_USER" --password-stdin "$REGISTRY_URL"
docker pull "$REGISTRY_KAMPAN_IMAGE"

compose() {
    docker compose -p kampan-staging -f docker-compose.staging.yml "$@"
}

compose config --quiet
# Pull public services separately; the exact private app image is already local.
compose pull mongodb redis
# Preserve databases and queues between builds; do not stop the whole stack.
if ! compose up -d --no-build --pull never --remove-orphans --wait --wait-timeout 180; then
    compose ps -a
    exit 1
fi
compose ps
