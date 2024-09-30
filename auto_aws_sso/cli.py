from __future__ import annotations

import hashlib
import http.client as httplib
import json
import logging
import re
import subprocess
import sys
import threading
from configparser import ConfigParser, NoSectionError
from datetime import datetime
from pathlib import Path
from threading import Thread
from typing import TYPE_CHECKING, Any

import click
from dateutil.parser import parse
from dateutil.tz import UTC, tzlocal

from auto_aws_sso.authorize_sso import authorize_sso
from auto_aws_sso.exception import AWSConfigNotFoundError, SectionNotFoundError

if TYPE_CHECKING:
    from collections.abc import Callable

    from mypy_extensions import NamedArg

AWS_CONFIG_PATH = f"{Path.home()}/.aws/config"
AWS_SSO_CACHE_PATH = f"{Path.home()}/.aws/sso/cache"


def _load_json(path: str) -> dict[str, Any]:
    with Path(path).open() as context:
        return dict(json.load(context))


def _read_config(path: str) -> ConfigParser:
    config = ConfigParser()
    config.read(path)
    return config


def _add_prefix(name: str) -> str:
    return f"profile {name}" if name != "default" else "default"


def _get_aws_profile(profile_name: str) -> dict[str, str]:
    if not Path(AWS_CONFIG_PATH).exists():
        raise AWSConfigNotFoundError
    config = _read_config(AWS_CONFIG_PATH)
    profile_to_refresh = _add_prefix(profile_name)
    try:
        profile_opts = config.items(profile_to_refresh)
    except NoSectionError as e:
        msg = f"{profile_to_refresh} profile not found."
        raise SectionNotFoundError(msg) from e
    return dict(profile_opts)


def is_sso_expired(profile: dict[str, str]) -> bool:

    cache = hashlib.sha1(profile["sso_session"].encode("utf-8")).hexdigest()  # noqa: S324
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

            print(f"Found credentials. Valid until {expires_at.astimezone(tzlocal())}")
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


def run_aws_sso_login(  # noqa: C901
    callback: Callable[[str, str, NamedArg(bool, "headless")], None],
    *,
    headless: bool,
) -> Thread:
    # Regex patterns to match the URL and the code
    url_pattern = r"https://device\.sso\.[\w\-\.]+"
    code_pattern = r"[A-Z0-9]{4}-[A-Z0-9]{4}"

    # Initialize variables to store the URL and code
    url = None
    code = None

    def sso_login() -> None:
        nonlocal url, code  # Access the outer scope variables
        with subprocess.Popen(  # noqa: S602
            ["/opt/homebrew/bin/aws sso login --no-browser"],
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,  # Automatically decode output to string
        ) as process:
            while True:
                if process.stdout is None:
                    msg = "No stdout available."
                    raise ValueError(msg)
                output = process.stdout.readline()
                if output == "" and process.poll() is not None:
                    break

                if output:
                    # Match URL and code in the output
                    url_match = re.search(url_pattern, output)
                    code_match = re.search(code_pattern, output)

                    # Update url and code if matches are found
                    if url_match:
                        url = url_match.group(0)
                    if code_match:
                        code = code_match.group(0)

                    # If both URL and code are found, invoke the callback and exit the loop
                    if url and code:
                        # noinspection PyArgumentList
                        callback(url, code, headless=headless)
                        break

            # Check for errors in stderr
            if process.stderr is not None:
                stderr_output = process.stderr.read().strip()
                if stderr_output:
                    print(f"Error: {stderr_output}")

    thread = threading.Thread(target=sso_login)
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
    "--debug",
    "-d",
    is_flag=True,
    default=False,
    help="Debug mode on.",
)
@click.option(
    "--profile",
    "-p",
    default="default",
    help="Profile to use.",
)
@click.option(
    "--force",
    "-f",
    is_flag=True,
    default=False,
    help="Profile to use.",
)
def cli(no_headless: bool, debug: bool, profile: str, force: bool) -> None:  # noqa: FBT001
    """A tool to automate AWS SSO login."""
    try:
        profile_opts = _get_aws_profile(profile)
        if have_internet():
            if force or is_sso_expired(profile_opts):
                if force:
                    print("Forcing Refresh.")
                else:
                    print("SSO Expired.")
                if debug:
                    logging.basicConfig(level=logging.DEBUG)
                # noinspection PyTypeChecker
                login_thread = run_aws_sso_login(authorize_sso, headless=(not no_headless))
                login_thread.join()
            else:
                print("SSO not expired.")
        else:
            print("Internet not available.")
    except AWSConfigNotFoundError:
        print(f"AWS Config file not found in `{AWS_CONFIG_PATH}`.")
        sys.exit(-1)
    except SectionNotFoundError:
        print(f"Profile `{profile}` not found in {AWS_CONFIG_PATH}.")
        sys.exit(-1)
    except BrokenPipeError:
        logging.warning("Broken pipe error encountered; exiting gracefully.")
        sys.exit(0)


if __name__ == "__main__":
    cli()
