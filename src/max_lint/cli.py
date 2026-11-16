"""Command line entry point for max-lint."""

import argparse
from importlib.metadata import version


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the ``max-lint`` command.

    :return: the configured parser.
    """
    parser = argparse.ArgumentParser(
        prog="max-lint",
        description="Run black, isort, flake8, mypy and pytest with a single shared configuration.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {version('max-lint')}")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the ``max-lint`` command.

    :param argv: arguments to parse; defaults to ``sys.argv[1:]``.
    :return: the process exit code.
    """
    build_parser().parse_args(argv)
    return 0
