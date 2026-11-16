"""Command line entry point for max-lint."""

import argparse
import subprocess
import sys
import tempfile
from importlib.metadata import version
from pathlib import Path

from max_lint.config import ConfigError, load_config
from max_lint.lint import lint_commands


def run_commands(commands: list[list[str]]) -> int:
    """
    Run each command in order, stopping at the first one that fails.

    :param commands: argument lists to run from the current directory.
    :return: 0 when every command succeeds, otherwise 1.
    """
    for command in commands:
        if subprocess.run(command, check=False).returncode != 0:
            return 1

    return 0


def main(argv: list[str] | None = None) -> int:
    """
    Run the ``max-lint`` command.

    :param argv: arguments to parse; defaults to ``sys.argv[1:]``.
    :return: the process exit code: 0 on success, 1 when a tool fails, 2 on a configuration error.
    """
    parser = argparse.ArgumentParser(
        prog="max-lint",
        description="Run black, isort, flake8, mypy and pytest with a single shared configuration.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {version('max-lint')}")
    subcommands = parser.add_subparsers(dest="command")
    lint_parser = subcommands.add_parser("lint", help="format with black and isort, then check with flake8")
    lint_parser.add_argument("--check", action="store_true", help="check formatting with black and isort without rewriting files")
    arguments = parser.parse_args(argv)

    if arguments.command is None:
        return 0

    with tempfile.TemporaryDirectory() as scratch:
        try:
            commands = lint_commands(load_config(Path("pyproject.toml")), check=arguments.check, scratch=Path(scratch))
        except ConfigError as error:
            print(f"max-lint: {error}", file=sys.stderr)
            return 2

        return run_commands(commands)
