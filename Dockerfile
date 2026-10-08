# syntax=docker/dockerfile:1.7
# Node.js is copied from the official image instead of installed from
# NodeSource, so it matches the Debian release of the PHP image below.
FROM node:24-bookworm-slim AS node

# The build stage only needs PHP CLI, Composer, Node.js and Git. It uses the
# slim official PHP image rather than the OpenLiteSpeed runtime image.
FROM php:8.3-cli-bookworm AS builder

# Git fetches the deployment repo and source packages; unzip lets Composer
# extract dist archives (the PHP image ships neither unzip nor ext-zip).
RUN apt-get update && \
    apt-get install -y --no-install-recommends git unzip && \
    rm -rf /var/lib/apt/lists/*

# WP-CLI (copied into the runtime image, which the startup scripts use)
ADD --chmod=755 https://raw.githubusercontent.com/wp-cli/builds/gh-pages/phar/wp-cli.phar /usr/local/bin/wp

# PHP Composer
COPY --from=composer/composer:latest-bin /composer /usr/bin/composer

# Node 24.*
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm && \
    ln -s ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx && \
    node --version && npm --version && wp --version --allow-root

# Set the working directory for the application to the location where the Municipio deployment will be cloned and served
WORKDIR /var/www/vhosts/localhost/html

# Fetch the Municipio deployment repository. The ref may be a branch, a tag or
# a full commit SHA (release PRs are built from their exact head commit).
ARG MUNICIPIO_DEPLOYMENT_REPOSITORY=https://github.com/municipio-se/municipio-deployment.git
ARG MUNICIPIO_DEPLOYMENT_REF=master
RUN git init -q . && \
    git remote add origin "$MUNICIPIO_DEPLOYMENT_REPOSITORY" && \
    git fetch -q --depth 1 origin "${MUNICIPIO_DEPLOYMENT_REF:-HEAD}" && \
    git checkout -q FETCH_HEAD

# Build the project with Composer and the Municipio build script.
# ext-imagick is only needed at runtime (the runtime image provides it), so it
# is not installed here just to satisfy Composer's platform check.
RUN --mount=type=secret,id=acf_pro_key,required=true \
    ACF_PRO_KEY="$(cat /run/secrets/acf_pro_key)" && \
    export COMPOSER_AUTH='{"http-basic": {"connect.advancedcustomfields.com": {"username": "'"$ACF_PRO_KEY"'", "password": "http://localhost"}}}' && \
    composer install --prefer-dist --no-progress --optimize-autoloader --classmap-authoritative --ignore-platform-req=ext-imagick && \
    php ./build.php --cleanup --no-composer-in-child-packages --install-npm && \
    rm -rf .git && \
    chmod -R 755 .

# Start from a clean copy of the runtime image so build tools and package
# manager caches do not become part of the deployed image.
FROM ghcr.io/helsingborg-stad/ols-docker-hbg:0.1.0-php8.3 AS runtime

USER root

WORKDIR /var/www/vhosts/localhost/html

# WP-CLI is needed by the startup scripts, but Composer, Node.js, npm, and Git
# are build-only dependencies and stay in the builder stage.
COPY --from=builder /usr/local/bin/wp /usr/local/bin/wp
COPY --from=builder --chown=1000:1000 /var/www/vhosts/localhost/html/ ./

COPY --chown=1000:1000 --chmod=755 htaccess ./htaccess
COPY --chown=1000:1000 --chmod=755 config ./config
COPY --chown=1000:1000 --chmod=755 setup ./setup

RUN mkdir -p wp-content/uploads/cache/blade-cache && \
    chown 1000:1000 wp-content/uploads/cache/blade-cache

EXPOSE 80

# Define a health check for the web server
HEALTHCHECK CMD test "$(curl -s -o /dev/null -w '%{http_code}' http://localhost/)" = "200"

ENTRYPOINT ["./setup/setup.py"]
