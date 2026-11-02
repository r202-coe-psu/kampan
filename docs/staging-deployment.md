# Jenkins staging

The `Inventory/develop` multibranch job builds on `built-in` and deploys on
`staging-agent`, following the DIIS Tracker agent/registry workflow.

Required Jenkins configuration:

- `REGISTRY_URL`: the existing registry hostname, without a URL scheme.
- `CI_REGISTRY_TOKEN`: Secret text for registry user `ci-bot`, with push/pull
  access to `r202-coe-psu/kampan`.
- `INVENTORY_ENV_DEVELOPMENT`: the existing Inventory Secret file containing a
  Python `kampan-development.cfg`, including staging OAuth/SMTP settings and
  `SECRET_KEY`. This is Python config, not dotenv format.
- Docker CLI and Compose v2 supporting `up --wait` on `staging-agent`.

Each build publishes a `develop-<build number>-<commit>` image tag. Staging pulls
that exact image; production does not share a mutable `latest` tag with staging.
Only `develop` runs the staging stages. The existing `main` production stage is
retained.

The staging stack uses `docker-compose.staging.yml`, project `kampan`,
and port `10060` (override with `KAMPAN_STAGING_PORT` on the agent). It adopts
`kampan-web-development`, `kampan-worker-development` and
`kampan-controller-development` on the existing external network
`kampan_kampan-network`.

MongoDB and Redis are managed separately. The script requires the existing
`kampan-mongodb-development` and `kampan-redis-development` containers to be
running under project `kampan` and checks their connectivity before deployment.
It never recreates them. MongoDB keeps `kampan_mongodb-development`; Redis keeps
its current in-memory queue. Uploaded files retain the existing host bind path
`/home/bomzyx/actions-runner/_work/kampan/deployment` (override with
`KAMPAN_STAGING_FILES_DIR`). Missing host directories fail rather than creating
an empty storage directory. Disable any previous deployment workflow before
running Jenkins so two pipelines do not manage these containers concurrently.

The deployment script stores the credential file with mode 600 at
`$HOME/.config/kampan/staging/kampan-development.cfg` on the staging agent.
Override its directory with `KAMPAN_STAGING_CONFIG_DIR` if needed. The directory
must be visible to the agent's Docker daemon for bind mounts. It persists beyond
workspace cleanup, so container restarts can still read the config. The script
sets `MONGODB_HOST` and `REDIS_URL` in this copy to the internal Compose services;
the staging MongoDB has no application username/password configured.

Use staging OAuth redirect URLs and a test SMTP destination in the credential
file. The web, worker and controller use the same config. Python config files
and dotenv files are excluded from the image build context by `.dockerignore`.

Deployment checks MongoDB/Redis, waits for HTTP health checks and for the worker
and controller to be running. Failure prints container status and fails the
build. It never prunes shared Docker resources or deletes data volumes. Registry
login uses a temporary Docker config removed when the command exits.

To inspect the stack on the staging agent, export the exact image and config
paths from the build, then run:

```sh
docker compose -p kampan -f docker-compose.staging.yml ps -a
docker compose -p kampan -f docker-compose.staging.yml logs --tail 100
```

To roll back, deploy a previous successful build's image tag with the same
Compose project and config path. Database compatibility must be checked before
rolling back application versions.
