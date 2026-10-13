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
from setup_htaccess import env

ROOT_DIR = Path(__file__).resolve().parent.parent
OLS_CONF = Path("/usr/local/lsws/conf/httpd_config.conf")
OLS_ENTRYPOINT = "/entrypoint.sh"

WP_CONF_NAME = re.compile(r"WP_CONF_[A-Za-z0-9_]+")


def install_php_tidy() -> None:
    if env("ENABLE_PHP_TIDY", "false") != "true":
        return

    php = Path("/usr/local/lsws/fcgi-bin/lsphp").resolve().parent / "php"
    version = subprocess.check_output(
        [str(php), "-r", "echo PHP_MAJOR_VERSION, '.', PHP_MINOR_VERSION;"], text=True
    ).strip()
    major, minor = version.split(".")
    if not (major.isdigit() and minor.isdigit()):
        raise ValueError(f"Unexpected LiteSpeed PHP version: {version}")

    if subprocess.run(
        [str(php), "-r", 'exit(extension_loaded("tidy") ? 0 : 1);'], check=False
    ).returncode == 0:
        return

    subprocess.run(["apt-get", "update"], check=True)
    subprocess.run(
        ["apt-get", "install", "-y", "--no-install-recommends", f"lsphp{major}{minor}-tidy"],
        check=True,
        env={**os.environ, "DEBIAN_FRONTEND": "noninteractive"},
    )
    subprocess.run(["rm", "-rf", "/var/lib/apt/lists"], check=True)


def inject_ols_env() -> None:
    """Inject only WP_CONF_* environment variables into the OpenLiteSpeed
    lsphp extProcessor, as "env NAME=VALUE" lines right after its opening line."""
    if not OLS_CONF.is_file():
        return

    env_lines = [
        # A config line can't span lines, so only the first line of a value is kept.
        f"    env {name}={value.splitlines()[0] if value else ''}\n"
        for name, value in os.environ.items()
        if WP_CONF_NAME.fullmatch(name)
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

    install_php_tidy()
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
