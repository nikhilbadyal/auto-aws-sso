#!/usr/bin/env python3

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

EXPECTED_ARG_COUNT = 2


def run_command(command: list[str]) -> None:
    """Run a shell command and raise if it fails."""
    print(f"> Running: {' '.join(command)}")
    result = subprocess.run(command, check=False, shell=False)  # noqa: S603
    if result.returncode != 0:
        print("❌ Command failed:", " ".join(command), file=sys.stderr)
        sys.exit(result.returncode)


def get_env_token(env_var: str) -> str:
    """Get token from environment, or fail fast."""
    token = os.getenv(env_var)
    if not token:
        print(f"❌ Missing required environment variable: {env_var}", file=sys.stderr)
        sys.exit(1)
    return token


def publish(target: str) -> None:
    """Build and publish the package using hatch."""
    token_env_var = "PYPI_TOKEN" if target == "pypi" else "TEST_PYPI_TOKEN"
    token = get_env_token(token_env_var)

    dist_path = Path("dist")
    if dist_path.exists():
        print("🧹 Cleaning old builds...")
        for file in dist_path.iterdir():
            file.unlink()
    else:
        dist_path.mkdir()

    # Build
    print("📦 Building package...")
    run_command(["hatch", "build"])

    # Publish
    print(f"🚀 Publishing to {target}...")
    repo_flag = [] if target == "pypi" else ["-r", "test"]
    run_command(["hatch", "publish", "-u", "__token__", "-a", token, *repo_flag])

    print("✅ Publish complete.")


def main() -> None:
    """Main entrypoint."""
    if len(sys.argv) != EXPECTED_ARG_COUNT or sys.argv[1] not in {"pypi", "testpypi"}:
        print("Usage: publish.py [pypi|testpypi]", file=sys.stderr)
        sys.exit(1)

    publish(sys.argv[1])


if __name__ == "__main__":
    main()
