"""Tests for the max-lint command line entry point."""

import os
import subprocess
import sys
from importlib.metadata import version
from pathlib import Path

import pytest

from max_lint.cli import main


def test_main_without_arguments_needs_a_max_lint_table(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """
    Running with no arguments runs the lint and test steps, which need ``[tool.max-lint]``.

    :param tmp_path: Project directory the fixture files are written to.
    :param monkeypatch: Used to run max-lint from the project directory.
    :param capsys: Captures what max-lint prints.
    """
    (tmp_path / "pyproject.toml").write_text("")
    monkeypatch.chdir(tmp_path)

    assert main([]) == 2
    assert "no [tool.max-lint] table" in capsys.readouterr().err


def test_version_flag_prints_installed_version(capsys: pytest.CaptureFixture[str]) -> None:
    """
    ``--version`` prints the name and the installed package version, then exits 0.

    :param capsys: Captures what max-lint prints.
    """
    with pytest.raises(SystemExit) as exc_info:
        main(["--version"])

    assert exc_info.value.code == 0
    assert capsys.readouterr().out == f"max-lint {version('max-lint')}\n"


def test_help_flag_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    """
    ``--help`` prints usage and exits 0.

    :param capsys: Captures what max-lint prints.
    """
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
        (
            {"pyproject.toml": '[tool.max-lint]\npaths = ["docs"]\n', "docs/index.md": "# Docs\n"},
            "max-lint: no Python files found under 'paths' and 'test-paths' in [tool.max-lint]; point them at Python sources.\n",
        ),
        (
            {
                "pyproject.toml": '[tool.max-lint]\npaths = ["src"]\ntest-paths = ["my tests"]\n'
                '\n[tool.max-lint.per-file-ignores]\n"my tests/*" = ["D103"]\n',
                "src/a.py": "",
                "my tests/test_a.py": "",
            },
            "max-lint: 'my tests/test_a.py' needs ignored codes from [tool.max-lint] but flake8 cannot name a path with whitespace, "
            "':', ',' or a name that is not UTF-8; rename it or add it to 'exclude'.\n",
        ),
        (
            {"pyproject.toml": '[tool.max-lint]\npaths = ["src"]\n', "src/x\ny/__init__.py": ""},
            "max-lint: 'src/x\\ny/__init__.py' needs ignored codes from [tool.max-lint] but flake8 cannot name a path with whitespace, "
            "':', ',' or a name that is not UTF-8; rename it or add it to 'exclude'.\n",
        ),
    ],
    ids=["no-python-files", "test-path-with-space", "file-name-with-newline"],
)
def test_lint_configuration_error_exits_two_with_one_line(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    files: dict[str, str],
    message: str,
) -> None:
    """
    The message goes to stderr as one line.

    :param tmp_path: Project directory the fixture files are written to.
    :param monkeypatch: Used to run max-lint from the project directory.
    :param capsys: Captures what max-lint prints.
    :param files: File contents by relative path.
    :param message: Expected stderr output.
    """
    for name, text in files.items():
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text(text)

    monkeypatch.chdir(tmp_path)

    exit_code = main(["lint"])

    assert exit_code == 2
    assert capsys.readouterr().err == message


def test_lint_rejects_unknown_option(capsys: pytest.CaptureFixture[str]) -> None:
    """
    An unrecognised option is a usage error with exit status 2.

    :param capsys: Captures what max-lint prints.
    """
    with pytest.raises(SystemExit) as exc_info:
        main(["lint", "--fix"])

    assert exc_info.value.code == 2
    assert "unrecognized arguments: --fix" in capsys.readouterr().err


def test_lint_rejects_file_name_that_is_not_utf8(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """
    An ``__init__.py`` in a directory whose name is not UTF-8 is a one-line configuration error.

    :param tmp_path: Project directory the fixture files are written to.
    :param monkeypatch: Used to run max-lint from the project directory.
    :param capsys: Captures what max-lint prints.
    """
    (tmp_path / "src").mkdir()
    (tmp_path / "pyproject.toml").write_text('[tool.max-lint]\npaths = ["src"]\n')

    try:
        package = os.path.join(os.fsencode(tmp_path), b"src", b"bad\xff")
        os.mkdir(package)
        open(os.path.join(package, b"__init__.py"), "w").close()
    except OSError:
        pytest.skip("the file system accepts only UTF-8 file names")

    monkeypatch.chdir(tmp_path)

    exit_code = main(["lint"])

    assert exit_code == 2
    assert capsys.readouterr().err == (
        "max-lint: 'src/bad\\udcff/__init__.py' needs ignored codes from [tool.max-lint] but flake8 cannot name a path with whitespace, "
        "':', ',' or a name that is not UTF-8; rename it or add it to 'exclude'.\n"
    )
