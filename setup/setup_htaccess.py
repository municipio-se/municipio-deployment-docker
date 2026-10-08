#!/usr/bin/env python3
"""Select the .htaccess template matching the site type and copy it to the
document root as ".htaccess", which is where OpenLiteSpeed's
autoLoadHtaccess/RewriteFile config actually reads it from (not the
"htaccess/" source folder itself).

We have 3 htaccess files
1. htaccess/.htaccess
2. htaccess/.htaccess-multisite-subdomain
3. htaccess/.htaccess-multisite-subfolder

So if WP_ALLOW_MULTISITE is true and SUBDOMAIN_INSTALL is true use .htaccess-multisite-subdomain
If WP_ALLOW_MULTISITE is true and SUBDOMAIN_INSTALL is false use .htaccess-multisite-subfolder
Otherwise use .htaccess
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent

LSCACHE_RULES = r"""# BEGIN LSCACHE
## LITESPEED WP CACHE PLUGIN - Do not edit the contents of this block! ##
<IfModule mod_rewrite.c>
RewriteEngine on
RewriteRule litespeed/debug/.*\.log$ - [F,L]
RewriteRule \.litespeed_conf\.dat - [F,L]
</IfModule>
<IfModule LiteSpeed>
CacheLookup on
RewriteRule .* - [E=Cache-Control:no-autoflush]

### marker ASYNC start ###
RewriteCond %{REQUEST_URI} /wp-admin/admin-ajax\.php
RewriteCond %{QUERY_STRING} action=async_litespeed
RewriteRule .* - [E=noabort:1]
### marker ASYNC end ###

### marker DROPQS start ###
CacheKeyModify -qs:fbclid
CacheKeyModify -qs:gclid
CacheKeyModify -qs:utm*
CacheKeyModify -qs:_ga
### marker DROPQS end ###

</IfModule>
## LITESPEED WP CACHE PLUGIN - Do not edit the contents of this block! ##
# END LSCACHE
# BEGIN NON_LSCACHE
## LITESPEED WP CACHE PLUGIN - Do not edit the contents of this block! ##
## LITESPEED WP CACHE PLUGIN - Do not edit the contents of this block! ##
# END NON_LSCACHE
"""


def env(name: str, default: str = "") -> str:
    """Read WP_CONF_<name>, falling back to <name>, then to default.

    Empty values count as unset, like bash's ${VAR:-default}.
    """
    return os.environ.get("WP_CONF_" + name) or os.environ.get(name) or default


def main() -> None:
    allow_multisite = env("WP_ALLOW_MULTISITE", "false")
    subdomain = env("SUBDOMAIN_INSTALL", "false")
    enable_ls_cache = env("ENABLE_LS_CACHE", "false")

    if allow_multisite == "true":
        if subdomain == "true":
            selected = "htaccess/.htaccess-multisite-subdomain"
        else:
            selected = "htaccess/.htaccess-multisite-subfolder"
    else:
        selected = "htaccess/.htaccess"

    content = (ROOT_DIR / selected).read_bytes()
    if enable_ls_cache == "true":
        content = LSCACHE_RULES.encode() + content

    (ROOT_DIR / ".htaccess").write_bytes(content)


if __name__ == "__main__":
    main()
