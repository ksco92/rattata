"""Tests for ``max-lint test`` and the bare ``max-lint`` run against the real pytest and coverage."""

import re
from pathlib import Path

import pytest
from coverage import Coverage

from max_lint.cli import main
from max_lint.config import Config
from max_lint.pytest_step import pytest_command

BASE_PYPROJECT = """[tool.max-lint]
paths = ["src"]
test-paths = ["tests"]
coverage-source = ["src/pkg"]

[tool.pytest.ini_options]
pythonpath = ["src"]
"""
SIGN_MODULE = '''"""Sign of a number."""


def sign(value: int) -> str:
    """
    Return the sign of the value.

    :param value: Number whose sign is returned.
    :return: ``positive`` or ``other``.
    """
    if value > 0:
        return "positive"

    return "other"
'''
SIGN_TEST = '''"""Tests for the sign."""

from pkg import sign


def test_sign() -> None:
    """Both branches are taken."""
    assert sign(1) == "positive"
    assert sign(0) == "other"
'''
POSITIVE_ONLY_TEST = SIGN_TEST.replace('    assert sign(0) == "other"\n', "")
BASE_FILES = {"pyproject.toml": BASE_PYPROJECT, "src/pkg/__init__.py": SIGN_MODULE, "tests/test_sign.py": SIGN_TEST}
ROOT_MODULE_FILES = {
    "pyproject.toml": '[tool.max-lint]\npaths = ["rootmod.py"]\ntest-paths = ["tests"]\ncoverage-source = ["rootmod"]\n',
    "rootmod.py": SIGN_MODULE,
    "tests/test_sign.py": SIGN_TEST.replace("from pkg", "from rootmod"),
}
MARKER_TEST = (
    '"""Tests that leave a marker."""\n\nfrom pathlib import Path\n\n\n'
    'def test_marker() -> None:\n    """Leave a file in the working directory."""\n    Path("ran").write_text("")\n'
)
UNDOCUMENTED_MODULE = "VALUE = 1\n"
UNFORMATTED_MODULE = '"""Data."""\n\nVALUE = {\'a\':1}\n'
FLAGS_MODULE = '"""Flags."""\n\nFLAG = True\nTOTAL = 0\n' + "if FLAG:\n    TOTAL += 1\n" * 5
IMPORT_TEST = '"""Tests."""\n\nimport pkg\n\n\ndef test_import() -> None:\n    """The package imports."""\n    assert pkg\n'
LOOSE_COVERAGE = {
    "pyproject.toml": BASE_PYPROJECT + "\n[tool.coverage.run]\nbranch = false\n\n[tool.coverage.report]\nfail_under = 10\n",
    ".coveragerc": "[run]\nbranch = False\n\n[report]\nfail_under = 10\n",
    ".coveragerc.toml": "[run]\nbranch = false\n\n[report]\nfail_under = 10\n",
    "setup.cfg": "[coverage:run]\nbranch = False\n\n[coverage:report]\nfail_under = 10\n",
    "tox.ini": "[coverage:run]\nbranch = False\n\n[coverage:report]\nfail_under = 10\n",
}
NOT_REACHED = "Required test coverage of 95% not reached"
NO_FILES = "measured no files"


def write_files(root: Path, files: dict[str, str]) -> None:
    """
    Write each relative path in ``files`` under ``root``, creating parent directories.

    :param root: Directory the files are written under.
    :param files: File contents by relative path.
    """
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)


def run_max_lint(
    root: Path,
    files: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
    *arguments: str,
) -> tuple[int, str]:
    r"""
    Write ``files`` under ``root``, run ``max-lint`` there and return the exit code and the combined output.

    :param root: Directory the files are written under and max-lint runs in.
    :param files: File contents by relative path.
    :param monkeypatch: Changes the working directory to ``root``.
    :param capfd: Captures the output of the tools the run starts.
    :param \*arguments: Arguments given to max-lint.
    :return: Exit code and combined output.
    """
    write_files(root, files)
    monkeypatch.chdir(root)
    exit_code = main(list(arguments))
    captured = capfd.readouterr()

    return exit_code, captured.out + captured.err


def sized_module(missed: int, statements: int) -> str:
    """
    Return a module of ``statements`` statements of which ``missed`` are in a function that is never called.

    :param missed: Statements in the function that is never called.
    :param statements: Total statements in the module.
    :return: Source text of the module.
    """
    return f'"""Sized."""\n\ndef unused() -> None:\n{"    VALUE = 1\n" * missed}\n{"VALUE = 1\n" * (statements - 1 - missed)}'


def test_fully_covered_project_exits_zero(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """
    Passing tests over fully covered branches exit 0 and report the coverage.

    :param tmp_path: Project directory the fixture files are written to.
    :param monkeypatch: Used to run max-lint from the project directory.
    :param capfd: Captures the output of the tools the run starts.
    """
    exit_code, output = run_max_lint(tmp_path, BASE_FILES, monkeypatch, capfd, "test")

    assert exit_code == 0
    assert "Required test coverage of 95% reached. Total coverage: 100.00%" in output


def test_untested_branch_under_the_floor_exits_one_and_shows_missing_lines(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """
    An untested branch that drops coverage under 95% fails with the missing lines listed.

    :param tmp_path: Project directory the fixture files are written to.
    :param monkeypatch: Used to run max-lint from the project directory.
    :param capfd: Captures the output of the tools the run starts.
    """
    files = {**BASE_FILES, "tests/test_sign.py": POSITIVE_ONLY_TEST}

    exit_code, output = run_max_lint(tmp_path, files, monkeypatch, capfd, "test")

    assert exit_code == 1
    assert NOT_REACHED in output
    assert re.search(r"67%\s+14\n", output)


@pytest.mark.parametrize(
    ("missed", "statements", "exit_code"),
    [(5, 100, 0), (6, 100, 1), (53, 1000, 1)],
    ids=["95-percent-passes", "94-percent-fails", "94.7-percent-fails"],
)
def test_floor_is_95_percent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
    missed: int,
    statements: int,
    exit_code: int,
) -> None:
    """
    Exactly 95% passes, and 94% and 94.7% fail.

    :param tmp_path: Project directory the fixture files are written to.
    :param monkeypatch: Used to run max-lint from the project directory.
    :param capfd: Captures the output of the tools the run starts.
    :param missed: Statements in the function that is never called.
    :param statements: Total statements in the module.
    :param exit_code: Expected exit status.
    """
    files = {**BASE_FILES, "src/pkg/__init__.py": sized_module(missed, statements), "tests/test_sign.py": IMPORT_TEST}

    assert run_max_lint(tmp_path, files, monkeypatch, capfd, "test")[0] == exit_code


def test_branch_coverage_is_measured(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]) -> None:
    """
    Fully executed statements with untaken branches fall under the floor.

    :param tmp_path: Project directory the fixture files are written to.
    :param monkeypatch: Used to run max-lint from the project directory.
    :param capfd: Captures the output of the tools the run starts.
    """
    files = {**BASE_FILES, "src/pkg/__init__.py": FLAGS_MODULE, "tests/test_sign.py": IMPORT_TEST}

    exit_code, output = run_max_lint(tmp_path, files, monkeypatch, capfd, "test")

    assert exit_code == 1
    assert NOT_REACHED in output


@pytest.mark.parametrize("name", list(LOOSE_COVERAGE), ids=list(LOOSE_COVERAGE))
def test_project_coverage_settings_do_not_lower_the_floor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
    name: str,
) -> None:
    """
    A project that turns branch coverage off and sets fail_under to 10 still fails at 77% branch coverage.

    :param tmp_path: Project directory the fixture files are written to.
    :param monkeypatch: Used to run max-lint from the project directory.
    :param capfd: Captures the output of the tools the run starts.
    :param name: Name of the coverage settings file in the project.
    """
    files = {**BASE_FILES, "src/pkg/__init__.py": FLAGS_MODULE, "tests/test_sign.py": IMPORT_TEST, name: LOOSE_COVERAGE[name]}

    exit_code, output = run_max_lint(tmp_path, files, monkeypatch, capfd, "test")

    assert exit_code == 1
    assert "Total coverage: 77" in output


@pytest.mark.parametrize(
    "module",
    [
        '"""Mod."""\n\nVALUE = 1\n\n\ndef helper() -> None:  # pragma: no cover\n' + "    VALUE = 2\n" * 10,
        '"""Mod."""\n\nVALUE = 1\n\nif __name__ == "__main__":\n' + "    VALUE = 2\n" * 10,
    ],
    ids=["pragma-no-cover", "main-guard"],
)
def test_excluded_lines_do_not_count(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
    module: str,
) -> None:
    """
    Code under ``pragma: no cover`` or ``if __name__ == "__main__":`` is left out of the measurement.

    :param tmp_path: Project directory the fixture files are written to.
    :param monkeypatch: Used to run max-lint from the project directory.
    :param capfd: Captures the output of the tools the run starts.
    :param module: Contents of the measured module.
    """
    files = {**BASE_FILES, "src/pkg/__init__.py": module, "tests/test_sign.py": IMPORT_TEST}

    assert run_max_lint(tmp_path, files, monkeypatch, capfd, "test")[0] == 0


@pytest.mark.parametrize(
    "imports",
    [
        "from typing import TYPE_CHECKING\n\nif TYPE_CHECKING:\n    import json\n",
        "import typing\n\nif typing.TYPE_CHECKING:\n    import json\n",
    ],
    ids=["bare-name", "typing-attribute"],
)
def test_type_checking_blocks_do_not_count(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
    imports: str,
) -> None:
    """
    An import under ``if TYPE_CHECKING:`` leaves no missing line and no partial branch.

    :param tmp_path: Project directory the fixture files are written to.
    :param monkeypatch: Used to run max-lint from the project directory.
    :param capfd: Captures the output of the tools the run starts.
    :param imports: Import lines and the ``TYPE_CHECKING`` block of the measured module.
    """
    files = {**BASE_FILES, "src/pkg/__init__.py": f'"""Mod."""\n\n{imports}', "tests/test_sign.py": IMPORT_TEST}

    exit_code, output = run_max_lint(tmp_path, files, monkeypatch, capfd, "test")

    assert exit_code == 0
    assert re.search(r"^src/pkg/__init__\.py +\d+ +0 +\d+ +0 +100\.00%", output, re.MULTILINE)


def test_a_line_that_only_mentions_type_checking_is_measured(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """
    The block under an ``if`` that only mentions ``if TYPE_CHECKING:`` in a comment is measured.

    :param tmp_path: Project directory the fixture files are written to.
    :param monkeypatch: Used to run max-lint from the project directory.
    :param capfd: Captures the output of the tools the run starts.
    """
    module = '"""Mod."""\n\nFLAG = False\n\nif FLAG:  # if TYPE_CHECKING:\n' + "    VALUE = 1\n" * 10
    files = {**BASE_FILES, "src/pkg/__init__.py": module, "tests/test_sign.py": IMPORT_TEST}

    exit_code, output = run_max_lint(tmp_path, files, monkeypatch, capfd, "test")

    row = re.search(r"^src/pkg/__init__\.py.*$", output, re.MULTILINE)
    assert exit_code == 1
    assert row
    assert "100.00%" not in row[0]
    assert row[0].endswith("6-15")


@pytest.mark.parametrize("pattern", ["*/generated.py", "src/pkg/generated.py"], ids=["wildcard", "relative-to-project"])
def test_coverage_omit_removes_files_from_the_measurement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
    pattern: str,
) -> None:
    """
    A file matching a ``coverage-omit`` pattern is not measured, and is measured without the key.

    :param tmp_path: Directory holding the ``plain`` and ``omitting`` projects.
    :param monkeypatch: Used to run max-lint from the project directory.
    :param capfd: Captures the output of the tools the run starts.
    :param pattern: Pattern given as ``coverage-omit``.
    """
    generated = '"""Generated."""\n\n\ndef unused() -> None:\n' + "    VALUE = 1\n" * 20
    files = {**BASE_FILES, "src/pkg/generated.py": generated}
    omitting = {**files, "pyproject.toml": BASE_PYPROJECT.replace('["src/pkg"]', f'["src/pkg"]\ncoverage-omit = ["{pattern}"]')}

    assert run_max_lint(tmp_path / "plain", files, monkeypatch, capfd, "test")[0] == 1
    assert run_max_lint(tmp_path / "omitting", omitting, monkeypatch, capfd, "test")[0] == 0


def test_project_coverage_options_in_pytest_settings_do_not_widen_the_scope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """
    A bare ``--cov`` in the project's ``addopts`` does not add files outside ``coverage-source``.

    :param tmp_path: Project directory the fixture files are written to.
    :param monkeypatch: Used to run max-lint from the project directory.
    :param capfd: Captures the output of the tools the run starts.
    """
    pyproject = BASE_PYPROJECT + 'addopts = "--cov --cov-fail-under=10"\n'
    other = '"""Other."""\n\n\ndef unused() -> None:\n' + "    VALUE = 1\n" * 50
    files = {
        **BASE_FILES,
        "pyproject.toml": pyproject,
        "src/other/__init__.py": other,
        "tests/test_other.py": IMPORT_TEST.replace("pkg", "other"),
    }

    assert run_max_lint(tmp_path, files, monkeypatch, capfd, "test")[0] == 0


@pytest.mark.parametrize(
    "files",
    [
        {"pyproject.toml": BASE_PYPROJECT.replace("src/pkg", "nomatch")},
        {"src/pkg/__init__.py": '"""Documented only."""\n', "tests/test_sign.py": IMPORT_TEST},
        {"pyproject.toml": BASE_PYPROJECT.replace('["src/pkg"]', '["src/pkg"]\ncoverage-omit = ["*/pkg/*"]')},
    ],
    ids=["source-matches-nothing", "only-a-docstring", "everything-omitted"],
)
def test_measuring_no_files_fails_although_tests_pass(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
    files: dict[str, str],
) -> None:
    """
    When coverage has nothing to measure, the step exits 1 and says so.

    :param tmp_path: Project directory the fixture files are written to.
    :param monkeypatch: Used to run max-lint from the project directory.
    :param capfd: Captures the output of the tools the run starts.
    :param files: Files that replace or extend the base project.
    """
    exit_code, output = run_max_lint(tmp_path, {**BASE_FILES, **files}, monkeypatch, capfd, "test")

    assert exit_code == 1
    assert "1 passed" in output
    assert "max-lint: coverage measured no files that contain statements; check 'coverage-source' and 'coverage-omit'" in output


def test_failing_test_exits_one_without_the_no_files_message(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """
    A failing test is a tool failure and leaves the coverage report alone.

    :param tmp_path: Project directory the fixture files are written to.
    :param monkeypatch: Used to run max-lint from the project directory.
    :param capfd: Captures the output of the tools the run starts.
    """
    files = {**BASE_FILES, "tests/test_sign.py": SIGN_TEST.replace('"positive"', '"negative"')}

    exit_code, output = run_max_lint(tmp_path, files, monkeypatch, capfd, "test")

    assert exit_code == 1
    assert "1 failed" in output
    assert NO_FILES not in output


def test_interrupted_pytest_run_exits_one_without_the_no_files_message(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """
    A collection error ends the run with exit 1 and does not blame the coverage scope.

    :param tmp_path: Project directory the fixture files are written to.
    :param monkeypatch: Used to run max-lint from the project directory.
    :param capfd: Captures the output of the tools the run starts.
    """
    files = {**BASE_FILES, "tests/test_sign.py": "def broken(:\n"}

    exit_code, output = run_max_lint(tmp_path, files, monkeypatch, capfd, "test")

    assert exit_code == 1
    assert "Interrupted: 1 error during collection" in output
    assert NO_FILES not in output


@pytest.mark.parametrize("arguments", [["test"], []], ids=["test", "bare"])
def test_module_in_the_project_root_is_importable_by_the_tests(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
    arguments: list[str],
) -> None:
    """
    A project that is not installed passes, also after the lint tools ran with ``PYTHONSAFEPATH``.

    :param tmp_path: Project directory the fixture files are written to.
    :param monkeypatch: Used to run max-lint from the project directory.
    :param capfd: Captures the output of the tools the run starts.
    :param arguments: Arguments given to max-lint.
    """
    exit_code, output = run_max_lint(tmp_path, ROOT_MODULE_FILES, monkeypatch, capfd, *arguments)

    assert exit_code == 0
    assert "1 passed" in output


def test_python_safe_path_set_by_the_user_reaches_pytest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """
    A value the user set is passed on unchanged, so the root module is not importable.

    :param tmp_path: Project directory the fixture files are written to.
    :param monkeypatch: Changes the working directory and sets ``PYTHONSAFEPATH``.
    :param capfd: Captures the output of the tools the run starts.
    """
    monkeypatch.setenv("PYTHONSAFEPATH", "1")

    exit_code, output = run_max_lint(tmp_path, ROOT_MODULE_FILES, monkeypatch, capfd, "test")

    assert exit_code == 1
    assert "ModuleNotFoundError" in output


def test_tests_are_collected_with_the_importlib_import_mode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """
    Test files with the same base name in different directories do not clash.

    :param tmp_path: Project directory the fixture files are written to.
    :param monkeypatch: Used to run max-lint from the project directory.
    :param capfd: Captures the output of the tools the run starts.
    """
    files = {**BASE_FILES, "tests/one/test_same.py": IMPORT_TEST, "tests/two/test_same.py": IMPORT_TEST}

    exit_code, output = run_max_lint(tmp_path, files, monkeypatch, capfd, "test")

    assert exit_code == 0
    assert "3 passed" in output


def test_only_coverage_data_and_pytest_cache_are_written_to_the_project(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """
    Only the coverage data file and pytest's cache are left in the project directory.

    :param tmp_path: Project directory the fixture files are written to.
    :param monkeypatch: Used to run max-lint from the project directory.
    :param capfd: Captures the output of the tools the run starts.
    """
    run_max_lint(tmp_path, BASE_FILES, monkeypatch, capfd, "test")

    assert {path.name for path in tmp_path.iterdir()} == {"pyproject.toml", "src", "tests", ".coverage", ".pytest_cache"}


@pytest.mark.parametrize(
    ("pyproject", "key"),
    [
        (BASE_PYPROJECT.replace('test-paths = ["tests"]\n', ""), "'test-paths'"),
        (BASE_PYPROJECT.replace('test-paths = ["tests"]', "test-paths = []"), "'test-paths'"),
        (BASE_PYPROJECT.replace('coverage-source = ["src/pkg"]\n', ""), "'coverage-source'"),
        (BASE_PYPROJECT.replace('["src/pkg"]', "[]"), "'coverage-source'"),
    ],
    ids=["no-test-paths", "empty-test-paths", "no-coverage-source", "empty-coverage-source"],
)
@pytest.mark.parametrize("arguments", [["test"], []], ids=["test", "bare"])
def test_missing_test_settings_exit_two_before_anything_runs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
    pyproject: str,
    key: str,
    arguments: list[str],
) -> None:
    """
    The message names the key and no file is rewritten.

    :param tmp_path: Project directory the fixture files are written to.
    :param monkeypatch: Used to run max-lint from the project directory.
    :param capfd: Captures the output of the tools the run starts.
    :param pyproject: Contents of the ``pyproject.toml`` under test.
    :param key: Setting the message names.
    :param arguments: Arguments given to max-lint.
    """
    files = {**BASE_FILES, "pyproject.toml": pyproject, "src/pkg/data.py": UNFORMATTED_MODULE}

    exit_code, output = run_max_lint(tmp_path, files, monkeypatch, capfd, *arguments)

    assert exit_code == 2
    assert output.startswith(f"max-lint: {key} in [tool.max-lint]")
    assert output.count("\n") == 1
    assert (tmp_path / "src/pkg/data.py").read_text() == UNFORMATTED_MODULE


def test_lint_does_not_need_the_test_settings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """
    ``max-lint lint`` runs without ``test-paths`` or ``coverage-source``.

    :param tmp_path: Project directory the fixture files are written to.
    :param monkeypatch: Used to run max-lint from the project directory.
    :param capfd: Captures the output of the tools the run starts.
    """
    files = {"pyproject.toml": '[tool.max-lint]\npaths = ["src"]\n', "src/pkg/__init__.py": SIGN_MODULE}

    assert run_max_lint(tmp_path, files, monkeypatch, capfd, "lint")[0] == 0


def test_bare_run_with_a_lint_failure_does_not_run_pytest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """
    A flake8 failure stops the run before pytest starts.

    :param tmp_path: Project directory the fixture files are written to.
    :param monkeypatch: Used to run max-lint from the project directory.
    :param capfd: Captures the output of the tools the run starts.
    """
    files = {**BASE_FILES, "src/pkg/extra.py": UNDOCUMENTED_MODULE, "tests/test_marker.py": MARKER_TEST}

    exit_code, output = run_max_lint(tmp_path, files, monkeypatch, capfd)

    assert exit_code == 1
    assert "src/pkg/extra.py:1:1: D100" in output
    assert not (tmp_path / "ran").exists()


def test_bare_run_on_a_clean_project_runs_lint_then_tests(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """
    Both halves run and the run exits 0.

    :param tmp_path: Project directory the fixture files are written to.
    :param monkeypatch: Used to run max-lint from the project directory.
    :param capfd: Captures the output of the tools the run starts.
    """
    exit_code, output = run_max_lint(tmp_path, {**BASE_FILES, "tests/test_marker.py": MARKER_TEST}, monkeypatch, capfd)

    assert exit_code == 0
    assert "Total coverage: 100.00%" in output
    assert (tmp_path / "ran").exists()


def test_bare_run_stops_when_the_tests_fail(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """
    A passing lint step does not hide a failing test step.

    :param tmp_path: Project directory the fixture files are written to.
    :param monkeypatch: Used to run max-lint from the project directory.
    :param capfd: Captures the output of the tools the run starts.
    """
    files = {**BASE_FILES, "tests/test_sign.py": POSITIVE_ONLY_TEST}

    assert run_max_lint(tmp_path, files, monkeypatch, capfd)[0] == 1


@pytest.mark.parametrize(
    "arguments",
    [["--check"], ["--check", "lint"], ["lint", "--check"]],
    ids=["bare", "before-lint", "after-lint"],
)
def test_check_mode_does_not_rewrite_files_or_run_pytest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
    arguments: list[str],
) -> None:
    """
    ``--check`` fails on an unformatted file, leaves it as it is and never reaches pytest.

    :param tmp_path: Project directory the fixture files are written to.
    :param monkeypatch: Used to run max-lint from the project directory.
    :param capfd: Captures the output of the tools the run starts.
    :param arguments: Arguments given to max-lint.
    """
    files = {**BASE_FILES, "src/pkg/data.py": UNFORMATTED_MODULE, "tests/test_marker.py": MARKER_TEST}

    exit_code, output = run_max_lint(tmp_path, files, monkeypatch, capfd, *arguments)

    assert exit_code == 1
    assert "would reformat src/pkg/data.py" in output
    assert (tmp_path / "src/pkg/data.py").read_text() == UNFORMATTED_MODULE
    assert not (tmp_path / "ran").exists()


def test_bare_check_run_on_a_formatted_project_runs_the_tests(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """
    ``--check`` on a clean project continues to the test step.

    :param tmp_path: Project directory the fixture files are written to.
    :param monkeypatch: Used to run max-lint from the project directory.
    :param capfd: Captures the output of the tools the run starts.
    """
    exit_code, output = run_max_lint(tmp_path, {**BASE_FILES, "tests/test_marker.py": MARKER_TEST}, monkeypatch, capfd, "--check")

    assert exit_code == 0
    assert "Total coverage: 100.00%" in output
    assert (tmp_path / "ran").exists()


def test_test_command_does_not_lint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]) -> None:
    """
    ``max-lint test`` leaves unformatted and undocumented files alone.

    :param tmp_path: Project directory the fixture files are written to.
    :param monkeypatch: Used to run max-lint from the project directory.
    :param capfd: Captures the output of the tools the run starts.
    """
    files = {**BASE_FILES, "src/pkg/data.py": UNFORMATTED_MODULE, "src/pkg/extra.py": UNDOCUMENTED_MODULE}

    exit_code, output = run_max_lint(tmp_path, files, monkeypatch, capfd, "test")

    assert exit_code == 1
    assert (tmp_path / "src/pkg/data.py").read_text() == UNFORMATTED_MODULE
    assert "D100" not in output


def test_lint_command_does_not_run_pytest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """
    ``max-lint lint`` stops after the lint steps.

    :param tmp_path: Project directory the fixture files are written to.
    :param monkeypatch: Used to run max-lint from the project directory.
    :param capfd: Captures the output of the tools the run starts.
    """
    exit_code, _ = run_max_lint(tmp_path, {**BASE_FILES, "tests/test_marker.py": MARKER_TEST}, monkeypatch, capfd, "lint")

    assert exit_code == 0
    assert not (tmp_path / "ran").exists()


def test_test_rejects_unknown_option(capsys: pytest.CaptureFixture[str]) -> None:
    """
    An unrecognised option on ``test`` is a usage error with exit status 2.

    :param capsys: Captures what max-lint prints.
    """
    with pytest.raises(SystemExit) as exc_info:
        main(["test", "--check"])

    assert exc_info.value.code == 2
    assert "unrecognized arguments: --check" in capsys.readouterr().err


def test_test_path_named_like_an_option_is_a_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """
    A directory named ``--cov-fail-under=0`` does not lower the floor.

    :param tmp_path: Project directory the fixture files are written to.
    :param monkeypatch: Used to run max-lint from the project directory.
    :param capfd: Captures the output of the tools the run starts.
    """
    files = {
        "pyproject.toml": BASE_PYPROJECT.replace('"tests"', '"--cov-fail-under=0"'),
        "src/pkg/__init__.py": SIGN_MODULE,
        "--cov-fail-under=0/test_sign.py": POSITIVE_ONLY_TEST,
    }

    exit_code, output = run_max_lint(tmp_path, files, monkeypatch, capfd, "test")

    assert exit_code == 1
    assert NOT_REACHED in output


@pytest.mark.parametrize("absolute", [False, True], ids=["relative", "absolute"])
def test_test_path_named_like_a_plugin_switch_is_a_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
    absolute: bool,
) -> None:
    """
    A directory named ``-pevilplug`` is collected for tests and no ``evilplug`` plugin is loaded.

    :param tmp_path: Project directory the fixture files are written to.
    :param monkeypatch: Used to run max-lint from the project directory.
    :param capfd: Captures the output of the tools the run starts.
    :param absolute: Whether the test path is given as an absolute path.
    """
    entry = f"{tmp_path}/-pevilplug" if absolute else "-pevilplug"
    files = {
        "pyproject.toml": f'[tool.max-lint]\npaths = ["pkg"]\ntest-paths = ["{entry}"]\ncoverage-source = ["pkg"]\n',
        "pkg/__init__.py": SIGN_MODULE,
        "evilplug.py": 'from pathlib import Path\n\nPath("evil-ran").write_text("")\n',
        "-pevilplug/test_sign.py": SIGN_TEST,
    }

    exit_code, output = run_max_lint(tmp_path, files, monkeypatch, capfd, "test")

    assert exit_code == 0
    assert "1 passed" in output
    assert not (tmp_path / "evil-ran").exists()


@pytest.mark.parametrize(
    "pattern",
    ["a\x7fb", "$HOME/x/*", "${ZZ_NOPE?}", "$$", 'a"b\\c', "é\U0001f600*.py", "*/[ab]?.py"],
    ids=["delete", "home-variable", "strict-variable", "double-dollar", "quote-backslash", "non-ascii", "glob"],
)
def test_coverage_omit_reaches_coverage_unchanged(tmp_path: Path, pattern: str) -> None:
    """
    Coverage reads the generated config and gets exactly the ``coverage-omit`` pattern.

    :param tmp_path: Directory the coverage config is written to.
    :param pattern: Pattern given as ``coverage-omit``.
    """
    pytest_command(Config(["src"], ["tests"], [], ["src"], [pattern, "plain"], {}, []), tmp_path)

    assert Coverage(config_file=str(tmp_path / "coverage.toml")).get_option("run:omit") == [pattern, "plain"]
