"""Shared fixture and runner helpers for the max-lint test suite."""

import re
from pathlib import Path

import pytest

from max_lint.cli import main

PLAIN_PYPROJECT = '[tool.max-lint]\npaths = ["src"]\n'


def write_files(root: Path, files: dict[str, str]) -> None:
    """
    Write each relative path in ``files`` under ``root``, creating parent directories.

    :param root: directory the files are written under.
    :param files: file contents by relative path.
    """
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)


def lint(root: Path, monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str], *arguments: str) -> tuple[int, str]:
    r"""
    Run ``max-lint lint`` from ``root`` and return the exit code and the combined output, with ``root`` replaced.

    :param root: project directory the command runs in.
    :param monkeypatch: changes the working directory to ``root``.
    :param capfd: captures the output of the tools the run starts.
    :param \*arguments: arguments given to max-lint.
    :return: exit code and combined output.
    """
    monkeypatch.chdir(root)
    exit_code = main(["lint", *arguments])
    captured = capfd.readouterr()

    return exit_code, (captured.out + captured.err).replace(str(Path.cwd()), "<root>")


def flake8_codes(output: str) -> list[str]:
    """
    Return each flake8 violation in ``output`` as ``path:row:col: CODE``.

    :param output: combined output of the tools.
    :return: each violation as ``path:row:col: CODE``.
    """
    return re.findall(r"^(\S(?:.*?\S)?\.py:\d+:\d+: [A-Z]+[0-9]+)", output, flags=re.MULTILINE)
