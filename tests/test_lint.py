"""Tests for ``max-lint lint`` against the real black, isort and flake8."""

from pathlib import Path

import pytest

from max_lint.cli import main
from max_lint.config import Config
from max_lint.lint import per_file_ignores

LONG_LINE = (
    'PARTS = [basename("/tmp/archive.tar.gz"), join("first", "second"), "a string literal which pads this line to 120 chars"]\n'
)
UNDOCUMENTED_MODULE = f"from os.path import basename, join\n\n{LONG_LINE}"
UNFORMATTED_MODULE = '"""Fixture module."""\nimport sys\nimport os\n\n' "VALUE = {'platform':sys.platform, 'sep':os.sep}\n"
FORMATTED_MODULE = '"""Fixture module."""\n\nimport os\nimport sys\n\nVALUE = {"platform": sys.platform, "sep": os.sep}\n'
UNDOCUMENTED_FUNCTION = '"""Fixture module."""\n\n\ndef add(first: int, second: int) -> int:\n    """\n    Add two numbers.\n\n    :param first: first addend.\n    """\n    return first + second\n'
LONG_WITH = (
    '"""Fixture module."""\n\n'
    'with open("the_first_file_with_a_rather_long_name.txt") as first_handle, open("the_second_file_with_a_long_name.txt") as second_handle:\n'
    "    pass\n"
)


def write_files(root: Path, files: dict[str, str]) -> None:
    """Write each relative path in ``files`` under ``root``, creating parent directories."""
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)


def lint(root: Path, monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str], *arguments: str) -> tuple[int, str]:
    """Run ``max-lint lint`` from ``root`` and return the exit code and the combined output, with ``root`` replaced."""
    monkeypatch.chdir(root)
    exit_code = main(["lint", *arguments])
    captured = capfd.readouterr()

    return exit_code, (captured.out + captured.err).replace(str(Path.cwd()), "<root>")


# Bundled style lock tests
def test_bundled_style_accepts_long_line_and_reports_missing_module_docstring(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """The fixture line is 120 characters: over the 80 of the override fixtures, under the bundled 130."""
    assert len(LONG_LINE.rstrip("\n")) == 120
    write_files(tmp_path, {"pyproject.toml": '[tool.max-lint]\npaths = ["src"]\n', "src/mod.py": UNDOCUMENTED_MODULE})

    exit_code, output = lint(tmp_path, monkeypatch, capfd)

    assert exit_code == 1
    assert "src/mod.py:1:1: D100 Missing docstring in public module" in output
    assert "E501" not in output
    assert (tmp_path / "src/mod.py").read_text() == UNDOCUMENTED_MODULE


@pytest.mark.parametrize(
    "overrides",
    [
        {
            "pyproject.toml": '[tool.black]\nline-length = 80\n\n[tool.isort]\nprofile = "google"\n',
            ".flake8": "[flake8]\nmax-line-length = 80\nextend-ignore = D100\n",
        },
        {"setup.cfg": "[flake8]\nmax-line-length = 80\nextend-ignore = D100\n\n[isort]\nprofile = google\n"},
        {"tox.ini": "[flake8]\nmax-line-length = 80\nextend-ignore = D100\n\n[isort]\nprofile = google\n"},
        {".isort.cfg": "[settings]\nprofile = google\n"},
    ],
    ids=["pyproject-and-flake8", "setup.cfg", "tox.ini", "isort.cfg"],
)
def test_project_tool_settings_do_not_change_the_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
    overrides: dict[str, str],
) -> None:
    """flake8 reads only the first of setup.cfg, tox.ini and .flake8, so each file is its own case."""
    files = {"pyproject.toml": '[tool.max-lint]\npaths = ["src"]\n', "src/mod.py": UNDOCUMENTED_MODULE}
    write_files(tmp_path / "plain", files)
    write_files(tmp_path / "overridden", files)

    for name, text in overrides.items():
        with (tmp_path / "overridden" / name).open("a") as file:
            file.write(text)

    plain = lint(tmp_path / "plain", monkeypatch, capfd)
    overridden = lint(tmp_path / "overridden", monkeypatch, capfd)

    assert overridden == plain
    assert (tmp_path / "overridden/src/mod.py").read_text() == (tmp_path / "plain/src/mod.py").read_text() == UNDOCUMENTED_MODULE


def test_lint_separates_first_party_imports(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """``app`` is first party because it is a package under ``src``."""
    module = '"""Fixture module."""\n\nimport os\nfrom app import helpers\nimport black\n\nVALUE = (os, helpers, black)\n'
    write_files(
        tmp_path,
        {"pyproject.toml": '[tool.max-lint]\npaths = ["src"]\n', "src/app/__init__.py": "", "src/app/main.py": module},
    )

    exit_code, _ = lint(tmp_path, monkeypatch, capfd)

    assert exit_code == 0
    assert (tmp_path / "src/app/main.py").read_text() == (
        '"""Fixture module."""\n\nimport os\n\nimport black\n\nfrom app import helpers\n\nVALUE = (os, helpers, black)\n'
    )


@pytest.mark.parametrize(
    ("project_table", "expected_with"),
    [
        (
            "",
            'with open("the_first_file_with_a_rather_long_name.txt") as first_handle, open(\n'
            '    "the_second_file_with_a_long_name.txt"\n'
            ") as second_handle:\n",
        ),
        (
            '[project]\nrequires-python = ">=3.8"\n',
            'with open("the_first_file_with_a_rather_long_name.txt") as first_handle, open(\n'
            '    "the_second_file_with_a_long_name.txt"\n'
            ") as second_handle:\n",
        ),
        (
            '[project]\nrequires-python = ">=3.9"\n',
            "with (\n"
            '    open("the_first_file_with_a_rather_long_name.txt") as first_handle,\n'
            '    open("the_second_file_with_a_long_name.txt") as second_handle,\n'
            "):\n",
        ),
    ],
    ids=["no-requires-python", "lower-bound-3.8", "lower-bound-3.9"],
)
def test_black_target_follows_requires_python(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
    project_table: str,
    expected_with: str,
) -> None:
    """Parenthesized context managers need Python 3.9, so the lower bound decides how black splits the line."""
    write_files(tmp_path, {"pyproject.toml": f'{project_table}[tool.max-lint]\npaths = ["src"]\n', "src/mod.py": LONG_WITH})

    lint(tmp_path, monkeypatch, capfd)

    assert (tmp_path / "src/mod.py").read_text() == f'"""Fixture module."""\n\n{expected_with}    pass\n'


# Docstring rule tests
def test_doc_codes_apply_to_paths_but_not_test_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """The same undocumented function sits in a source path and a nested test path."""
    write_files(
        tmp_path,
        {
            "pyproject.toml": '[tool.max-lint]\npaths = ["lib"]\ntest-paths = ["checks"]\n',
            "lib/mod.py": UNDOCUMENTED_FUNCTION,
            "checks/nested/test_mod.py": UNDOCUMENTED_FUNCTION.replace("\n\n\n", "\n\nimport os\n\n\n"),
        },
    )

    exit_code, output = lint(tmp_path, monkeypatch, capfd, "--check")
    doc_files = {line.split(":")[0] for line in output.splitlines() if ": DOC" in line}

    assert exit_code == 1
    assert doc_files == {"lib/mod.py"}
    assert "checks/nested/test_mod.py:3:1: F401 'os' imported but unused" in output


# Check and write mode tests
def test_check_mode_reports_unformatted_file_without_writing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """The fixture also has unsorted imports and an unused import, which isort and flake8 would report."""
    original = f"import json\n{UNFORMATTED_MODULE}".encode()
    write_files(tmp_path, {"pyproject.toml": '[tool.max-lint]\npaths = ["src"]\n'})
    (tmp_path / "src").mkdir()
    (tmp_path / "src/mod.py").write_bytes(original)

    exit_code, output = lint(tmp_path, monkeypatch, capfd, "--check")

    assert exit_code == 1
    assert "would reformat src/mod.py" in output
    assert "Imports are incorrectly sorted" not in output
    assert "F401" not in output
    assert (tmp_path / "src/mod.py").read_bytes() == original


def test_check_mode_reports_unsorted_imports_without_writing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """The file is black-clean, sits in a directory isort skips by default, and has an unused import for flake8."""
    original = b'"""Fixture module."""\n\nimport sys\nimport os\nimport json\n\nVALUE = (os.sep, sys.platform)\n'
    write_files(tmp_path, {"pyproject.toml": '[tool.max-lint]\npaths = ["src"]\n'})
    (tmp_path / "src/build").mkdir(parents=True)
    (tmp_path / "src/build/mod.py").write_bytes(original)

    exit_code, output = lint(tmp_path, monkeypatch, capfd, "--check")

    assert exit_code == 1
    assert "1 file would be left unchanged." in output
    assert "ERROR: <root>/src/build/mod.py Imports are incorrectly sorted and/or formatted." in output
    assert "F401" not in output
    assert (tmp_path / "src/build/mod.py").read_bytes() == original


@pytest.mark.parametrize(
    ("extra_import", "expected_exit"),
    [("", 0), ("import json\n", 1)],
    ids=["flake8-clean", "flake8-unused-import"],
)
def test_write_mode_rewrites_file_and_exits_with_flake8_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
    extra_import: str,
    expected_exit: int,
) -> None:
    """Run the write mode on a file that black and isort both change."""
    module = UNFORMATTED_MODULE.replace("import sys\n", f"import sys\n{extra_import}")
    write_files(tmp_path, {"pyproject.toml": '[tool.max-lint]\npaths = ["src"]\n', "src/mod.py": module})

    exit_code, _ = lint(tmp_path, monkeypatch, capfd)

    assert exit_code == expected_exit
    assert (tmp_path / "src/mod.py").read_text() == FORMATTED_MODULE.replace("import os\n", f"{extra_import}import os\n")


# Project table tests
def test_per_file_ignores_apply_only_to_matching_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """The ``__init__.py`` keeps the bundled D104 and F401 exemption next to the project entry."""
    write_files(
        tmp_path,
        {
            "pyproject.toml": '[tool.max-lint]\npaths = ["app"]\nper-file-ignores = { "app/legacy_*.py" = ["D100"] }\n',
            "app/__init__.py": "import os\n",
            "app/legacy_one.py": "VALUE = 1\n",
            "app/current.py": "VALUE = 1\n",
        },
    )

    exit_code, output = lint(tmp_path, monkeypatch, capfd, "--check")

    assert exit_code == 1
    assert [line for line in output.splitlines() if line.startswith("app/")] == [
        "app/current.py:1:1: D100 Missing docstring in public module",
    ]


def test_exclude_removes_file_from_every_tool(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """The excluded file breaks black, isort and flake8 alike."""
    broken = f"import json\n{UNFORMATTED_MODULE}"
    write_files(
        tmp_path,
        {
            "pyproject.toml": '[tool.max-lint]\npaths = ["app"]\nexclude = ["app/gen*"]\n',
            "app/generated/models.py": broken,
            "app/.venv/lib/site.py": broken,
            "app/ok.py": FORMATTED_MODULE,
        },
    )

    exit_code, _ = lint(tmp_path, monkeypatch, capfd)

    assert exit_code == 0
    assert (tmp_path / "app/generated/models.py").read_text() == broken
    assert (tmp_path / "app/.venv/lib/site.py").read_text() == broken


def test_path_outside_project_is_linted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """``PATH`` holds no tools, so each one must come from max-lint's own interpreter."""
    write_files(
        tmp_path,
        {"project/pyproject.toml": '[tool.max-lint]\npaths = ["../shared/etl"]\n', "shared/etl/job.py": UNFORMATTED_MODULE},
    )
    monkeypatch.setenv("PATH", str(tmp_path / "no-tools"))

    exit_code, output = lint(tmp_path / "project", monkeypatch, capfd)

    assert exit_code == 0
    assert "reformatted ../shared/etl/job.py" in output
    assert (tmp_path / "shared/etl/job.py").read_text() == FORMATTED_MODULE


# Per-file ignore composition tests
def test_per_file_ignores_exempts_test_directories_and_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A test path written with a trailing slash still yields a directory pattern."""
    write_files(tmp_path, {"suite/test_a.py": "", "test_b.py": ""})
    monkeypatch.chdir(tmp_path)
    config = Config(
        paths=["src"],
        test_paths=["suite/", "test_b.py"],
        exclude=[],
        per_file_ignores={"src/old.py": ["D100", "E731"]},
        black_target_versions=[],
    )

    assert per_file_ignores(config).splitlines() == [
        "*/__init__.py: D104, F401",
        "suite/*: DOC",
        "test_b.py: DOC",
        "src/old.py: D100, E731",
    ]
