# Municipio Docker image

This repository builds a ready-to-run [Municipio](https://github.com/municipio-se/municipio-deployment) WordPress image. The image contains OpenLiteSpeed, PHP, WordPress, WP-CLI, and a selected Municipio deployment. Composer, Node.js, npm, and Git are used only while building the image and are not included in the runtime image.

On its first start, the container connects to the database, installs WordPress, and activates ACF Pro automatically. Later starts reuse the existing database and ensure that ACF Pro remains active.

## Before you start

You need:

- Docker with Docker Compose
- An ACF Pro license key used to download ACF Pro while building the image
- A Municipio deployment repository and branch or tag (the defaults use the public Municipio deployment repository and its `master` branch)

Set the ACF Pro key in your shell. Docker passes it to the build as a temporary BuildKit secret, so it does not need to be written into the Compose file or stored in the image:

```sh
export ACF_PRO_KEY="your-license-key"
```

## Building the image directly

You can also build the image without Compose:

```sh
docker build \
  --secret id=acf_pro_key,env=ACF_PRO_KEY \
  --build-arg MUNICIPIO_DEPLOYMENT_REF=master \
  -t municipio:local .
```

The `acf_pro_key` secret is required for the build. It is mounted only while Composer installs the dependencies and is not retained in the resulting image.

The available build arguments are:

| Argument | Default | Purpose |
| --- | --- | --- |
| `MUNICIPIO_DEPLOYMENT_REPOSITORY` | Municipio's public deployment repository | Repository containing `composer.json` and `build.php`. |
| `MUNICIPIO_DEPLOYMENT_REF` | `master` | Branch, tag or full commit SHA to include in the image. |

The deployment source is copied into the image when it is built. Rebuild the image when you want to use a different version or include new source changes.

## Common settings

Runtime settings use the `WP_CONF_` prefix. The most useful ones are:

| Setting | Purpose |
| --- | --- |
| `WP_CONF_DB_NAME` | Database name. |
| `WP_CONF_DB_USER` | Database user. |
| `WP_CONF_DB_PASSWORD` | Database password. |
| `WP_CONF_DB_HOST` | Database service name or host. |
| `WP_CONF_WP_HOME` | Public address of the site. |
| `WP_CONF_WP_SITEURL` | Address of WordPress core, normally the site address followed by `/wp`. |
| `WP_CONF_WP_ADMIN_USER` | Admin username created on the first start. |
| `WP_CONF_WP_ADMIN_PASSWORD` | Admin password created on the first start. |
| `WP_CONF_WP_ADMIN_EMAIL` | Admin email created on the first start. |
| `WP_CONF_WP_DEBUG` | Set to `true` to enable WordPress debugging. |
| `WP_CONF_WP_REDIS_DISABLED` | Set to `true` when no Redis or Valkey service is used. |
| `ENABLE_LS_CACHE` | Set to `true` to enable LiteSpeed Cache plugin and add LiteSpeed rewrite rules to `.htaccess` on startup. |

The database and admin values are only used to perform the initial installation. If a database volume already contains WordPress, changing the initial admin values will not update the existing account.

Any additional WordPress constant can be defined with `WP_CONF_EXTRA_`. For example, `WP_CONF_EXTRA_MY_SETTING: enabled` defines the `MY_SETTING` constant.

## Multisite

Multisite is optional. Add these settings to the `municipio` service to enable a subdomain network:

```yaml
environment:
  WP_CONF_WP_ALLOW_MULTISITE: true
  WP_CONF_SUBDOMAIN_INSTALL: true
  WP_CONF_DOMAIN_CURRENT_SITE: localhost:9090
```

For a real domain, make sure its DNS and local development setup route subdomains to the Docker host. Subdomain multisite on `localhost` may behave differently between browsers and operating systems.

## Examples

The [`examples/`](examples/) directory contains ready-to-run Compose files that build on the base setup above. They use a relative build context (`..`), so run them from the repository root with `-f`, e.g.:

```sh
export ACF_PRO_KEY="your-license-key"
docker-compose -f examples/docker-compose-base.yml up -d --build
```

Tear an example down, including its volumes, before switching to a different one:

```sh
docker-compose -f examples/docker-compose-base.yml down -v
```

| File | Description |
| --- | --- |
| `docker-compose-base.yml` | Minimal single-site setup: `municipio` plus a MariaDB `db` service, no cache. |
| `docker-compose-using-lscache.yml` | Enables the `litespeed-cache` plugin and applies LiteSpeed Cache `.htaccess` rewrite rules. |
| `docker-compose-using-redis.yml` | Adds a Valkey (Redis-compatible) service and activates the `redis-cache` plugin for object caching. |
| `docker-compose-using-s3.yml` | Adds a MinIO service for S3-compatible media offloading and activates the `s3-uploads`/`s3-local-index` plugins. See the file's comments for the required `S3_UPLOADS_*` constants. |
| `docker-compose-multisite-subfolder.yml` | Enables WordPress multisite (subfolder mode) and creates a `subsite` site on first start. |
| `common-services.yml` | Shared `database` and `redis` service definitions, extended by the other examples via `extends`. Not meant to be run on its own. |

## Useful commands

Follow startup logs:

```sh
docker compose logs -f municipio
```

Run WP-CLI:

```sh
docker compose exec municipio wp option get siteurl --allow-root
```

Stop the containers while keeping the database and uploaded files:

```sh
docker compose down
```

Remove the containers, database, and uploaded files, allowing a completely fresh installation next time:

```sh
docker compose down --volumes
```

## Releases

Published images are built from release pull requests in `municipio-se/municipio-deployment`. A pull request counts as a release PR when its title is a plain version such as `6.2.6`, it targets `master` and it comes from a branch in that repository (not a fork).

1. **Stage.** Opening, pushing to, reopening or retitling a release PR builds the PR's head commit and pushes `ghcr.io/municipio-se/municipio-deployment-docker:v6.2.6-rc.N` (plus `src-<sha>`, used by promotion). Staging's Image Updater follows the newest rc.
2. **Promote.** Merging the PR retags the rc built from the PR's final head commit as `v6.2.6`, and moves `v6.2`, `v6` and `latest` when this is the newest version on that line. Nothing is rebuilt, so production runs exactly the image that was tested in staging. Promotion then tags `6.2.6` and creates a GitHub release in this repository, and tags the merge commit as `6.2.6` in `municipio-deployment` if that tag does not already exist.

The source repository has no workflow of its own for this. Its webhook sends pull request events to the `tag-relay` in the cluster (`helsingborg-stad/elx-k8s-apps`), which forwards them here as `repository_dispatch` events:

| `event_type` | Sent when | `client_payload` |
| --- | --- | --- |
| `release-pr-stage` | `opened`, `synchronize`, `reopened`, or `edited` with a changed title | `version`, `head_sha`, `pr`, `delivery` |
| `release-pr-merged` | `closed` with `merged: true` | `version`, `head_sha`, `merge_sha`, `pr`, `delivery` |

`version` is the PR title (`X.Y.Z`, no `v`), `head_sha` is the PR's head commit, and `merge_sha` is the commit the merge created on `master`. Both workflows can also be run by hand from the Actions tab with the same values.

Required secrets: `ACF_PRO_KEY`, and `SOURCE_REPO_TOKEN` (a token that can create tags in `municipio-se/municipio-deployment`, i.e. `contents: write`).

## Notes for deployed environments

The example is deliberately simple and uses local development credentials. For a shared or public environment:

- Use strong, unique passwords and provide secrets through your deployment platform.
- Put the site behind HTTPS and set `WP_CONF_WP_HOME` and `WP_CONF_WP_SITEURL` to the public HTTPS addresses.
- Pin the MariaDB image and Municipio deployment to versions that you have tested.
- Back up the database and uploads volumes.
- Do not publish the OpenLiteSpeed administration port unless it is specifically needed and protected.
