# syntax=docker/dockerfile:1.7
FROM webbutvecklinghelsingborg/gitops:openlitespeed-0.0.3 AS builder

USER root

# Git
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

# WP-CLI
RUN curl -fsSL -o /usr/local/bin/wp \
    https://raw.githubusercontent.com/wp-cli/builds/gh-pages/phar/wp-cli.phar \
    && chmod 755 /usr/local/bin/wp \
    && wp --version --allow-root

# PHP Composer
COPY --from=composer/composer:latest-bin /composer /usr/bin/composer

# Node 24.*
RUN curl -fsSL https://deb.nodesource.com/setup_24.x | bash - && \
    apt-get install -y nodejs && \
    rm -rf /var/lib/apt/lists/*

# Set the working directory for the application to the location where the Municipio deployment will be cloned and served
WORKDIR /var/www/vhosts/localhost/html

# Fetch the Municipio deployment repository. The ref may be a branch, a tag or
# a full commit SHA (release PRs are built from their exact head commit).
# The base image does not give WORKDIR to root, so git refuses to use a repo
# initialised in place ("dubious ownership") unless it is marked safe.
ARG MUNICIPIO_DEPLOYMENT_REPOSITORY=https://github.com/municipio-se/municipio-deployment.git
ARG MUNICIPIO_DEPLOYMENT_REF=master
RUN git config --global --add safe.directory "$PWD" && \
    git init -q . && \
    git remote add origin "$MUNICIPIO_DEPLOYMENT_REPOSITORY" && \
    git fetch -q --depth 1 origin "${MUNICIPIO_DEPLOYMENT_REF:-HEAD}" && \
    git checkout -q FETCH_HEAD

# Build the project with Composer and the Municipio build script
RUN --mount=type=secret,id=acf_pro_key,required=true \
    ACF_PRO_KEY="$(cat /run/secrets/acf_pro_key)" && \
    export COMPOSER_AUTH='{"http-basic": {"connect.advancedcustomfields.com": {"username": "'"$ACF_PRO_KEY"'", "password": "http://localhost"}}}' && \
    composer install --prefer-dist --no-progress --no-suggest --optimize-autoloader --classmap-authoritative && \
    php ./build.php --cleanup --no-composer-in-child-packages --install-npm && \
    rm -rf .git && \
    chown -R 1000:1000 . && \
    chmod -R 755 .

# Start from a clean copy of the runtime image so build tools and package
# manager caches do not become part of the deployed image.
FROM webbutvecklinghelsingborg/gitops:openlitespeed-0.0.3 AS runtime

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

ENTRYPOINT ["./setup/setup.sh"]
