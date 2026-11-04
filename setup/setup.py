#!/usr/bin/env python3
"""Container entrypoint: prepares the configuration, installs WordPress if
needed, then hands over to the OpenLiteSpeed entrypoint."""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import setup_htaccess
import setup_install

ROOT_DIR = Path(__file__).resolve().parent.parent
OLS_CONF = Path("/usr/local/lsws/conf/httpd_config.conf")
OLS_ENTRYPOINT = "/entrypoint.sh"
PHP_INI_DIR = Path("/usr/local/lsws/conf/php-ini.d")
PHP_INI_FILE = "zz-municipio-settings.ini"

WP_CONF_NAME = re.compile(r"WP_CONF_[A-Za-z0-9_]+")
ENV_VAR_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
PHP_INI_DIRECTIVE = re.compile(r"[A-Za-z][A-Za-z0-9_.-]*\s*=.*")


def configure_php_ini() -> None:
    """Write optional PHP_INI_SETTINGS directives and expose them to PHP."""
    settings = os.environ.get("PHP_INI_SETTINGS", "")
    directives = [line.strip() for line in settings.splitlines() if line.strip()]
    if not directives:
        return

    for directive in directives:
        if not PHP_INI_DIRECTIVE.fullmatch(directive):
            raise ValueError(f"Invalid PHP ini directive: {directive!r}")

    PHP_INI_DIR.mkdir(parents=True, exist_ok=True)
    (PHP_INI_DIR / PHP_INI_FILE).write_text("\n".join(directives) + "\n")

    scan_dirs = os.environ.get("PHP_INI_SCAN_DIR", "").split(os.pathsep)
    ini_dir = str(PHP_INI_DIR)
    if ini_dir not in scan_dirs:
        scan_dirs.append(ini_dir)
    os.environ["PHP_INI_SCAN_DIR"] = os.pathsep.join(scan_dirs)


def inject_ols_env() -> None:
    """Inject allowed environment variables into the OpenLiteSpeed
    lsphp extProcessor, as "env NAME=VALUE" lines right after its opening line."""
    configure_php_ini()

    if not OLS_CONF.is_file():
        return

    explicit_names = set()
    if configured_names := os.environ.get("OLS_PHP_ENV_VARS"):
        for requested_name in configured_names.split(","):
            name = requested_name.strip()
            if not ENV_VAR_NAME.fullmatch(name):
                raise ValueError(f"Invalid name in OLS_PHP_ENV_VARS: {name!r}")
            if name not in os.environ:
                raise ValueError(f"OLS_PHP_ENV_VARS references an unset variable: {name}")
            explicit_names.add(name)

    env_values = [
        (name, value)
        for name, value in os.environ.items()
        if WP_CONF_NAME.fullmatch(name) or name in explicit_names
    ]
    if os.environ.get("PHP_INI_SETTINGS", "").strip():
        env_values = [(name, value) for name, value in env_values if name != "PHP_INI_SCAN_DIR"]
        env_values.append(("PHP_INI_SCAN_DIR", os.environ["PHP_INI_SCAN_DIR"]))

    env_lines = [
        # A config line can't span lines, so only the first line of a value is kept.
        f"    env {name}={value.splitlines()[0] if value else ''}\n"
        for name, value in env_values
    ]
    if not env_lines:
        return

    lines = OLS_CONF.read_text().splitlines(keepends=True)
    output = []
    for line in lines:
        output.append(line)
        if "extProcessor lsphp{" in line:
            output.extend(env_lines)
    OLS_CONF.write_text("".join(output))


def main() -> None:
    # Ensure no stale .env file exists in webroot
    (ROOT_DIR / ".env").unlink(missing_ok=True)

    inject_ols_env()

    # Configure .htaccess rules
    setup_htaccess.main()

    # Bootstrap the WordPress installation
    setup_install.main()

    print("Configuration setup completed.")
    print("Starting litespeed.")

    # Flush before exec, or buffered output is lost when stdout isn't a tty.
    sys.stdout.flush()
    sys.stderr.flush()
    os.execv(OLS_ENTRYPOINT, [OLS_ENTRYPOINT, *sys.argv[1:]])


if __name__ == "__main__":
    main()
