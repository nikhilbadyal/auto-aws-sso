from __future__ import annotations

import hashlib
import http.client as httplib
import json
import logging
import re
import subprocess
import sys
import threading
from configparser import ConfigParser, NoOptionError, NoSectionError
from datetime import datetime
from pathlib import Path
from threading import Thread
from typing import TYPE_CHECKING, Any

import click
from dateutil.parser import parse
from dateutil.tz import UTC, tzlocal

from auto_aws_sso.authorize_sso import authorize_sso
from auto_aws_sso.constant import default_profile
from auto_aws_sso.exception import AWSConfigNotFoundError, SectionNotFoundError

if TYPE_CHECKING:
    from collections.abc import Callable

    from mypy_extensions import NamedArg

AWS_CONFIG_PATH = f"{Path.home()}/.aws/config"
AWS_SSO_CACHE_PATH = f"{Path.home()}/.aws/sso/cache"
logger = logging.getLogger(__name__)


def _load_json(path: str) -> dict[str, Any]:
    try:
        with Path(path).open() as f:
            return dict(json.load(f))
    except (OSError, json.JSONDecodeError):
        msg = f"Failed to load JSON from {path}"
        logger.exception(msg)
        return {}


def _read_config(path: str) -> ConfigParser:
    config = ConfigParser()
    config.read(path)
    return config


def _add_prefix(name: str) -> str:
    return f"profile {name}" if name != "default" else "default"


def _get_aws_profile(profile_name: str, session: str) -> dict[str, str]:
    if not Path(AWS_CONFIG_PATH).exists():
        raise AWSConfigNotFoundError
    config = _read_config(AWS_CONFIG_PATH)
    profile_to_refresh = _add_prefix(profile_name)
    try:
        sso_start_url = config.get(profile_to_refresh, "sso_start_url")
    except (NoSectionError, NoOptionError):
        try:
            sso_start_url = config.get(f"sso-session {session}", "sso_start_url")
        except NoSectionError as e:
            msg = f"Session `{session}` not found to extract sso_start_url in `{AWS_CONFIG_PATH}`."
            raise SectionNotFoundError(msg) from e

    try:
        config.set(profile_to_refresh, "sso_start_url", sso_start_url)
        profile_opts = config.items(profile_to_refresh)
    except NoSectionError as e:
        msg = f"Profile `{profile_to_refresh}` not found in `{AWS_CONFIG_PATH}`."
        raise SectionNotFoundError(msg) from e
    return dict(profile_opts)


def is_sso_expired(profile: dict[str, str]) -> bool:
    try:
        cache = hashlib.sha1(profile["sso_session"].encode("utf-8")).hexdigest()  # noqa: S324
    except KeyError:
        cache = hashlib.sha1(profile["sso_start_url"].encode("utf-8")).hexdigest()  # noqa: S324

    sso_cache_file = f"{AWS_SSO_CACHE_PATH}/{cache}.json"
    expired = True
    try:

        if not Path(sso_cache_file).is_file():
            print("Current cached SSO login is invalid/missing.")
        else:
            data = _load_json(sso_cache_file)
            now = datetime.now().astimezone(UTC)
            expires_at = parse(data["expiresAt"]).astimezone(UTC)

            if now < expires_at:
                expired = False

            print(
                f"Found credentials valid till {expires_at.astimezone(tzlocal()).strftime('%Y-%m-%d %I:%M:%S %p %Z')}",
            )
    except Exception:
        return expired
    else:
        return expired


def have_internet() -> bool:
    conn = httplib.HTTPSConnection("8.8.8.8", timeout=5)
    try:
        conn.request("HEAD", "/")

    except Exception:
        return False
    else:
        return True
    finally:
        conn.close()


def run_aws_sso_login(
    callback: Callable[[str, NamedArg(bool, "headless")], None],
    profile_to_refresh: str,
    *,
    headless: bool,
) -> Thread:
    # Regex patterns to match the URL and the code
    url_pattern = r"https://[^\s]+"

    # Initialize variables to store the URL and code
    url = None
    code = None

    def sso_login() -> None:
        nonlocal url, code  # Access the outer scope variables
        print(f"Refreshing {profile_to_refresh}")
        with subprocess.Popen(  # noqa: S603
            ["aws", "sso", "login", "--no-browser", "--profile", profile_to_refresh],  # noqa: S607
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        ) as process:
            while True:
                if process.stdout is None:
                    msg = "No stdout available."
                    raise ValueError(msg)
                output = process.stdout.readline().strip()
                if output == "" and process.poll() is not None:
                    break

                if output and len(output) > 0:
                    # Match URL and code in the output
                    url_match = re.search(url_pattern, output)

                    # Update url and code if matches are found
                    if url_match:
                        url = url_match.group(0)
                    print(f"URL: {url}")

                    # If both URL and code are found, invoke the callback and exit the loop
                    if url:
                        # noinspection PyArgumentList
                        callback(url, headless=headless)
                        break

            # Check for errors in stderr
            if process.stderr is not None:
                stderr_output = process.stderr.read().strip()
                if stderr_output:
                    print(f"Error: {stderr_output}")

    thread = threading.Thread(target=sso_login, name=f"SSOLogin-{profile_to_refresh}")
    thread.start()
    return thread


@click.command(context_settings={"show_default": True})
@click.option(
    "--no-headless",
    "-nh",
    is_flag=True,
    default=False,
    help="Run in non-headless mode.",
)
@click.option(
    "--profile",
    "-p",
    default=default_profile,
    help="Profile to use.",
)
@click.option(
    "--force",
    "-f",
    is_flag=True,
    default=False,
    help="Force refresh even if credentials are valid.",
)
@click.option(
    "--session",
    "-s",
    required=True,
    help="Session to use.",
)
def cli(no_headless: bool, profile: str, force: bool, session: str) -> None:  # noqa: FBT001
    """A tool to automate AWS SSO login."""
    try:
        profile_opts = _get_aws_profile(profile, session)
        if have_internet():
            if force or is_sso_expired(profile_opts):
                if force:
                    print("Forcing Refresh.")
                else:
                    print("SSO Expired.")
                # noinspection PyTypeChecker
                login_thread = run_aws_sso_login(authorize_sso, headless=(not no_headless), profile_to_refresh=profile)
                login_thread.join()
                print("SSO login completed.")
            else:
                print("SSO not expired.")
        else:
            print("Internet not available.")
    except AWSConfigNotFoundError:
        print(f"AWS Config file not found in `{AWS_CONFIG_PATH}`.")
        sys.exit(-1)
    except SectionNotFoundError as e:
        print(e)
        sys.exit(-1)
    except BrokenPipeError:
        logger.warning("Broken pipe error encountered; exiting gracefully.")
        sys.exit(0)


if __name__ == "__main__":
    cli()
