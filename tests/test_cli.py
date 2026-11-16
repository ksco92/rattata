"""Tests for the max-lint command line entry point."""

import subprocess
import sys
from importlib.metadata import version
from pathlib import Path

import pytest

from max_lint.cli import main


def test_main_without_arguments_returns_zero() -> None:
    """Running with no arguments succeeds."""
    assert main([]) == 0


def test_version_flag_prints_installed_version(capsys: pytest.CaptureFixture[str]) -> None:
    """``--version`` prints the name and the installed package version, then exits 0."""
    with pytest.raises(SystemExit) as exc_info:
        main(["--version"])

    assert exc_info.value.code == 0
    assert capsys.readouterr().out == f"max-lint {version('max-lint')}\n"


def test_help_flag_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    """``--help`` prints usage and exits 0."""
    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])

    assert exc_info.value.code == 0
    assert "usage: max-lint" in capsys.readouterr().out


def test_console_script_prints_version() -> None:
    """The installed ``max-lint`` script prints the version through a real process."""
    script = Path(sys.executable).parent / "max-lint"

    result = subprocess.run([str(script), "--version"], capture_output=True, text=True, check=False)

    assert result.returncode == 0
    assert result.stdout == f"max-lint {version('max-lint')}\n"


@pytest.mark.parametrize(
    ("files", "message"),
    [
        ({}, "max-lint: pyproject.toml not found; run max-lint from the directory that holds pyproject.toml.\n"),
        (
            {"pyproject.toml": '[tool.max-lint]\npaths = ["docs"]\n', "docs/index.md": "# Docs\n"},
            "max-lint: no Python files found under 'paths' and 'test-paths' in [tool.max-lint]; point them at Python sources.\n",
        ),
    ],
    ids=["missing-pyproject", "no-python-files"],
)
def test_lint_configuration_error_exits_two_with_one_line(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    files: dict[str, str],
    message: str,
) -> None:
    """The message goes to stderr as one line."""
    for name, text in files.items():
        (tmp_path / name).parent.mkdir(exist_ok=True)
        (tmp_path / name).write_text(text)

    monkeypatch.chdir(tmp_path)

    exit_code = main(["lint"])

    assert exit_code == 2
    assert capsys.readouterr().err == message


def test_lint_rejects_unknown_option(capsys: pytest.CaptureFixture[str]) -> None:
    """An unknown option is a usage error."""
    with pytest.raises(SystemExit) as exc_info:
        main(["lint", "--fix"])

    assert exc_info.value.code == 2
    assert "unrecognized arguments: --fix" in capsys.readouterr().err
