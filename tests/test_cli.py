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
    """Running with no arguments runs the lint and test steps, which need ``[tool.max-lint]``."""
    (tmp_path / "pyproject.toml").write_text("")
    monkeypatch.chdir(tmp_path)

    assert main([]) == 2
    assert "no [tool.max-lint] table" in capsys.readouterr().err


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
        (
            {"pyproject.toml": '[tool.max-lint]\npaths = ["docs"]\n', "docs/index.md": "# Docs\n"},
            "max-lint: no Python files found under 'paths' and 'test-paths' in [tool.max-lint]; point them at Python sources.\n",
        ),
        (
            {
                "pyproject.toml": '[tool.max-lint]\npaths = ["src"]\ntest-paths = ["my tests"]\n',
                "src/a.py": "",
                "my tests/test_a.py": "",
            },
            "max-lint: 'my tests/test_a.py' needs ignored codes from [tool.max-lint] but flake8 cannot name a path with whitespace, "
            "':', ',' or a name that is not UTF-8; rename it or add it to 'exclude'.\n",
        ),
        (
            {"pyproject.toml": '[tool.max-lint]\npaths = ["src"]\ntest-paths = ["tests"]\n', "src/a.py": "", "tests/x\ny.py": ""},
            "max-lint: 'tests/x\\ny.py' needs ignored codes from [tool.max-lint] but flake8 cannot name a path with whitespace, "
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
    """The message goes to stderr as one line."""
    for name, text in files.items():
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text(text)

    monkeypatch.chdir(tmp_path)

    exit_code = main(["lint"])

    assert exit_code == 2
    assert capsys.readouterr().err == message


def test_lint_rejects_unknown_option(capsys: pytest.CaptureFixture[str]) -> None:
    """An unrecognised option is a usage error with exit status 2."""
    with pytest.raises(SystemExit) as exc_info:
        main(["lint", "--fix"])

    assert exc_info.value.code == 2
    assert "unrecognized arguments: --fix" in capsys.readouterr().err


def test_lint_rejects_file_name_that_is_not_utf8(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A file under a test path whose name is not UTF-8 is a one-line configuration error."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src/a.py").write_text("")
    (tmp_path / "tests").mkdir()
    (tmp_path / "pyproject.toml").write_text('[tool.max-lint]\npaths = ["src"]\ntest-paths = ["tests"]\n')

    try:
        open(os.path.join(os.fsencode(tmp_path), b"tests", b"bad\xff.py"), "w").close()
    except OSError:
        pytest.skip("the file system accepts only UTF-8 file names")

    monkeypatch.chdir(tmp_path)

    exit_code = main(["lint"])

    assert exit_code == 2
    assert capsys.readouterr().err == (
        "max-lint: 'tests/bad\\udcff.py' needs ignored codes from [tool.max-lint] but flake8 cannot name a path with whitespace, "
        "':', ',' or a name that is not UTF-8; rename it or add it to 'exclude'.\n"
    )
