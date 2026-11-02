#!/bin/sh
set -eu

: "${REGISTRY_URL:?Set REGISTRY_URL}"
: "${REGISTRY_USER:?Set REGISTRY_USER}"
: "${REGISTRY_TOKEN:?Bind the registry credential}"
: "${REGISTRY_KAMPAN_IMAGE:?Set the exact image tag built by Jenkins}"
: "${CFG_FILE:?Bind INVENTORY_ENV_DEVELOPMENT}"

# Adopt only the existing Kampan application services. Its MongoDB, Redis and
# network are managed separately and must keep their data and running process.
for service in mongodb redis; do
    container="kampan-$service-development"
    test "$(docker inspect --format '{{.State.Running}}' "$container")" = true
    test "$(docker inspect --format '{{index .Config.Labels "com.docker.compose.project"}}' "$container")" = kampan
done
docker exec kampan-mongodb-development mongosh --quiet --eval 'quit(db.adminCommand("ping").ok ? 0 : 1)'
test "$(docker exec kampan-redis-development redis-cli ping)" = PONG

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
    docker compose -p kampan -f docker-compose.staging.yml "$@"
}

compose config --quiet
# Infrastructure intentionally lives outside this application-only Compose file.
export COMPOSE_IGNORE_ORPHANS=true
if ! compose up -d --no-build --pull never --wait --wait-timeout 180; then
    compose ps -a
    exit 1
fi
compose ps
