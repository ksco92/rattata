"""Command line entry point for max-lint."""

import argparse
import os
import subprocess
import sys
import tempfile
from importlib.metadata import version
from pathlib import Path

from max_lint.config import ConfigError, load_config
from max_lint.lint import TOOL_ENVIRONMENT, lint_commands
from max_lint.pytest_step import FAIL_UNDER, pytest_command, run_tests


def run_commands(commands: list[list[str]]) -> int:
    """
    Run each command in order, stopping at the first one that fails.

    :param commands: argument lists to run from the current directory.
    :return: 0 when every command succeeds, otherwise 1.
    """
    for command in commands:
        if subprocess.run(command, check=False, env={**os.environ, **TOOL_ENVIRONMENT}).returncode != 0:
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
    parser.add_argument("--check", action="store_true", help="check formatting with black and isort without rewriting files")
    subcommands = parser.add_subparsers(dest="command")
    lint_parser = subcommands.add_parser("lint", help="format and add trailing commas, then check with flake8 and mypy")
    lint_parser.add_argument(
        "--check",
        action="store_true",
        default=argparse.SUPPRESS,
        help="check formatting with black and isort without rewriting files",
    )
    subcommands.add_parser("test", help=f"run pytest with branch coverage and a {FAIL_UNDER}%% floor")
    arguments = parser.parse_args(argv)

    with tempfile.TemporaryDirectory() as scratch_directory:
        scratch = Path(scratch_directory)
        lint = arguments.command != "test"
        test = arguments.command != "lint"

        try:
            config = load_config(Path("pyproject.toml"))
            commands = lint_commands(config, check=arguments.check, scratch=scratch) if lint else []
            test_command = pytest_command(config, scratch) if test else []
        except ConfigError as error:
            print(f"max-lint: {error}", file=sys.stderr)
            return 2

        if run_commands(commands) != 0:
            return 1

        return run_tests(test_command, scratch) if test else 0
