"""Tests for ``max-lint lint`` against the real black, isort and flake8."""

import codecs
import http.server
import os
import re
import runpy
import signal
import subprocess
import sys
import threading
from pathlib import Path
from typing import Self

import pytest

from max_lint.cli import main
from max_lint.config import load_config
from max_lint.lint import lint_commands

PLAIN_PYPROJECT = '[tool.max-lint]\npaths = ["src"]\n'
LONG_LINE = (
    'PARTS = [basename("/tmp/archive.tar.gz"), join("first", "second"), "a string literal which pads this line to 120 chars"]\n'
)
UNDOCUMENTED_MODULE = f"from os.path import basename, join\n\n{LONG_LINE}"
UNFORMATTED_MODULE = '"""Fixture module."""\nimport sys\nimport os\n\n' "VALUE = {'platform':sys.platform, 'sep':os.sep}\n"
FORMATTED_MODULE = '"""Fixture module."""\n\nimport os\nimport sys\n\nVALUE = {"platform": sys.platform, "sep": os.sep}\n'
UNDOCUMENTED_FUNCTION = '"""Fixture module."""\n\n\ndef add(first: int, second: int) -> int:\n    """\n    Add two numbers.\n\n    :param first: Added to ``second``.\n    """\n    return first + second\n'
SHORT_DOCSTRING = '\n\ndef short(value: int) -> int:\n    """Return the value."""\n    return value\n'
LONG_WITH = (
    '"""Fixture module."""\n\n'
    'with open("the_first_file_with_a_rather_long_name.txt") as first_handle, open("the_second_file_with_a_long_name.txt") as second_handle:\n'
    "    pass\n"
)
NUMBERS = (
    "100000000, 100000001, 100000002, 100000003, 100000004, 100000005, 100000006, 100000007, 100000008, 100000009, 100000010"
)
FORMATTER_LIMITS = (
    '"""Fixture module."""\n\n'
    "from os.path import abspath, basename, commonpath, commonprefix, dirname, exists, getatime, getctime, isabs, isdir, isfile, islink\n"
    "# fmt: off\n"
    "from shutil import chown, copy, copy2, copyfile, copyfileobj, copymode, copystat, copytree, disk_usage, make_archive, rmtree, which\n"
    "# fmt: on\n\n"
    f"NUMBER = [{NUMBERS}]\nNUMBERS = [{NUMBERS}]\n"
)
FORMATTED_LIMITS = (
    '"""Fixture module."""\n\n'
    "from os.path import abspath, basename, commonpath, commonprefix, dirname, exists, getatime, getctime, isabs, isdir, isfile, islink\n\n"
    "# fmt: off\nfrom shutil import (\n    chown,\n    copy,\n    copy2,\n    copyfile,\n    copyfileobj,\n    copymode,\n    copystat,\n"
    "    copytree,\n    disk_usage,\n    make_archive,\n    rmtree,\n    which,\n)\n\n# fmt: on\n\n"
    f"NUMBER = [{NUMBERS}]\nNUMBERS = [\n" + "".join(f"    {number},\n" for number in NUMBERS.split(", ")) + "]\n"
)
FLAKE8_STYLE = '''"""Fixture module."""

from typing import Any, Self

URL = "https://example.com/a/path/long/enough/that/black/cannot/split/it/and/the/line/goes/past/one/hundred/and/thirty/characters/by/far"
TOTAL = (
    1_000_000_000_000_000_000_000_000_000_000_000_000_000_000_000_000_000_000_000_000
    + 2_000_000_000_000_000_000_000_000_000_000_000_000_000_000_000_000_000_000_000_000
)


def passthrough(value: int) -> Any:
    """
    Return the value unchanged.

    :param value: Returned as is.
    :return: ``value``, unchanged.
    """
    return value


def window(items: list[int], start: int) -> list[int]:
    """
    Return the slice after ``start``.

    :param items: List the slice is taken from.
    :param start: Index the slice follows.
    :return: Up to two items after ``start``.
    """
    return items[start + 1 : start + 3]


def short(value: int) -> int:
    """Return the value."""
    return value


def _private(value: int) -> int:
    """Return the value."""
    return value


class Box:
    """A box."""

    size: int = 1

    def __init__(self: Self, size: int) -> None:
        """
        Create the box.

        :param size: Stored as the box size.
        """
        self.size = size
'''
UNTYPED_FUNCTION = '"""Fixture module."""\n\n\ndef run():  # noqa: ANN201\n    """Do nothing."""\n'
MISTYPED_VALUE = '"""Fixture module."""\n\nVALUE: int = "text"\n'
LONG = "a" * 120
MISSING_COMMAS = (
    '"""Fixture module."""\n\n'
    f'ERROR = ValueError(\n    "{LONG}"\n)\nITEMS = [\n    "{LONG}"\n]\nMAPPING = {{\n    "k": "{LONG}"\n}}\n'
    f'KEYWORD = dict(\n    key="{LONG}"\n)\nSTAR = max(\n    *["{LONG}"]\n)\nNESTED = list(\n    list(\n        "{LONG}"\n    )\n)\n'
    f'LINE = ValueError("{LONG}")\n\n\ndef _pick[\n    T{LONG[:60]},\n    U{LONG[:60]}\n](first: int, second: int) -> int:\n    return first\n'
)
NESTED_SPEC = '"""Fixture module."""\n\nA = 1\nB = 2\nVALUE = f"{A:{\n    B\n}}"\n'
TRIPLE_QUOTED_SPEC = '"""Fixture module."""\n\nA = 5\nB = 3\nVALUE = f"""\n{A:{\n  B\n}}\n"""\n'
TEMPLATE_CALL = '"""Fixture module."""\n\nVALUE = t"{max(\n    1,\n    2\n)}"\n'
LONG_ITEMS = f'ITEMS = [\n    "{LONG}"\n]\n'
DOC_ITEMS = f'"""Doc."""\n\n{LONG_ITEMS}'
WITH_COMMA = DOC_ITEMS.replace('"\n]', '",\n]')
WITH_ITEM = 'with (open("a") as f,):\n    pass\n'
MYPY_ERROR = "src/mod.py:4: error: Function is missing a return type annotation  [no-untyped-def]"
UNREACHABLE_BRANCH = (
    '"""Fixture module."""\n\n\ndef run(value: int) -> None:\n    """\n    Print a string.\n\n    :param value: Printed when it is a string.\n    """\n'
    "    if isinstance(value, str):\n        print(value)\n"
)
UNREACHABLE_OVERRIDE = '\n[[tool.mypy.overrides]]\nmodule = ["mod"]\nwarn_unreachable = true\n'
UNTYPED_LIBRARY_OVERRIDE = '\n[[tool.mypy.overrides]]\nmodule = ["missing_pkg"]\nignore_missing_imports = true\n'
UNTYPED_LIBRARY_CLASS = (
    '"""Fixture module."""\n\nfrom missing_pkg import Widget\n\n\ndef run(widget: Widget) -> None:\n'
    '    """\n    Use the widget.\n\n    :param widget: Annotated with a class from an untyped library.\n    """\n'
)
BARE_GENERIC = '"""Fixture module."""\n\nVALUE: dict = {}\n'
EXPLICIT_ANY = '"""Fixture module."""\n\nfrom typing import Any\n\nVALUE: Any = 1\n'
RETURNED_ANY = (
    '"""Fixture module."""\n\nimport json\n\n\ndef run() -> int:\n    """\n    Parse a number.\n\n    :return: Number parsed from ``"1"``.\n    """\n'
    '    return json.loads("1")\n'
)


class BeaconHandler(http.server.BaseHTTPRequestHandler):
    """Record the path of each GET request and answer it with no content."""

    received: list[str] = []

    def do_GET(self: Self) -> None:
        """Record the request path."""
        self.received.append(self.path)
        self.send_response(204)
        self.end_headers()


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


def lint(root: Path, monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str], *arguments: str) -> tuple[int, str]:
    r"""
    Run ``max-lint lint`` from ``root`` and return the exit code and the combined output, with ``root`` replaced.

    :param root: Project directory the command runs in.
    :param monkeypatch: Changes the working directory to ``root``.
    :param capfd: Captures the output of the tools the run starts.
    :param \*arguments: Arguments given to max-lint.
    :return: Exit code and combined output.
    """
    monkeypatch.chdir(root)
    exit_code = main(["lint", *arguments])
    captured = capfd.readouterr()

    return exit_code, (captured.out + captured.err).replace(str(Path.cwd()), "<root>")


def flake8_codes(output: str) -> list[str]:
    """
    Return each flake8 violation in ``output`` as ``path:row:col: CODE``.

    :param output: Combined output of the tools.
    :return: Each violation as ``path:row:col: CODE``.
    """
    return re.findall(r"^(\S+\.py:\d+:\d+: [A-Z]+[0-9]+)", output, flags=re.MULTILINE)


def test_bundled_style_accepts_long_line_and_reports_missing_module_docstring(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """
    A 120-character line is left alone and a missing module docstring is reported.

    :param tmp_path: Project directory the fixture files are written to.
    :param monkeypatch: Used to run max-lint from the project directory.
    :param capfd: Captures the output of the tools the run starts.
    """
    write_files(tmp_path, {"pyproject.toml": PLAIN_PYPROJECT, "src/mod.py": UNDOCUMENTED_MODULE})

    exit_code, output = lint(tmp_path, monkeypatch, capfd)

    assert exit_code == 1
    assert flake8_codes(output) == ["src/mod.py:1:1: D100"]
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
    """
    Tool settings in the project leave output, exit code and files as they are without them.

    :param tmp_path: Directory holding the ``plain`` and ``overridden`` projects.
    :param monkeypatch: Used to run max-lint from the project directory.
    :param capfd: Captures the output of the tools the run starts.
    :param overrides: Text appended to the settings file of that name in the ``overridden`` project.
    """
    files = {"pyproject.toml": PLAIN_PYPROJECT, "src/mod.py": UNDOCUMENTED_MODULE}
    write_files(tmp_path / "plain", files)
    write_files(tmp_path / "overridden", files)

    for name, text in overrides.items():
        with (tmp_path / "overridden" / name).open("a") as file:
            file.write(text)

    plain = lint(tmp_path / "plain", monkeypatch, capfd)
    overridden = lint(tmp_path / "overridden", monkeypatch, capfd)

    assert overridden == plain
    assert (tmp_path / "overridden/src/mod.py").read_text() == (tmp_path / "plain/src/mod.py").read_text() == UNDOCUMENTED_MODULE


def test_bundled_formatter_line_lengths_and_isort_profile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """
    Lines of 130 characters stay and lines of 131 are wrapped, by black and by isort's black profile alike.

    :param tmp_path: Project directory the fixture files are written to.
    :param monkeypatch: Used to run max-lint from the project directory.
    :param capfd: Captures the output of the tools the run starts.
    """
    write_files(tmp_path, {"pyproject.toml": PLAIN_PYPROJECT, "src/mod.py": FORMATTER_LIMITS})

    lint(tmp_path, monkeypatch, capfd)

    assert (tmp_path / "src/mod.py").read_text() == FORMATTED_LIMITS


def test_bundled_flake8_and_pydoclint_options(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """
    Only ANN401 and the short docstring's missing sections are reported.

    :param tmp_path: Project directory the fixture files are written to.
    :param monkeypatch: Used to run max-lint from the project directory.
    :param capfd: Captures the output of the tools the run starts.
    """
    write_files(tmp_path, {"pyproject.toml": PLAIN_PYPROJECT, "src/mod.py": FLAKE8_STYLE})

    exit_code, output = lint(tmp_path, monkeypatch, capfd, "--check")

    assert exit_code == 1
    assert flake8_codes(output) == [
        "src/mod.py:12:35: ANN401",
        "src/mod.py:33:1: DOC101",
        "src/mod.py:33:1: DOC103",
        "src/mod.py:33:1: DOC201",
    ]


@pytest.mark.parametrize(
    ("paths", "package"),
    [("src", "src/app"), ("app", "app")],
    ids=["src-layout", "flat-layout"],
)
def test_lint_separates_first_party_imports(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
    paths: str,
    package: str,
) -> None:
    """
    The project's own package sorts after third-party imports.

    :param tmp_path: Project directory the fixture files are written to.
    :param monkeypatch: Used to run max-lint from the project directory.
    :param capfd: Captures the output of the tools the run starts.
    :param paths: Value of ``paths`` in the project settings.
    :param package: Directory of the project's own package.
    """
    module = '"""Fixture module."""\n\nimport os\nfrom app import helpers\nimport black\n\nVALUE = (os, helpers, black)\n'
    write_files(
        tmp_path,
        {
            "pyproject.toml": f'[tool.max-lint]\npaths = ["{paths}"]\n',
            f"{package}/__init__.py": "",
            f"{package}/helpers.py": '"""Helpers."""\n',
            f"{package}/main.py": module,
        },
    )

    exit_code, _ = lint(tmp_path, monkeypatch, capfd)

    assert exit_code == 0
    assert (tmp_path / package / "main.py").read_text() == (
        '"""Fixture module."""\n\nimport os\n\nimport black\n\nfrom app import helpers\n\nVALUE = (os, helpers, black)\n'
    )


@pytest.mark.parametrize(
    ("requires_python", "expected_with"),
    [
        (
            ">=3.8",
            'with open("the_first_file_with_a_rather_long_name.txt") as first_handle, open(\n'
            '    "the_second_file_with_a_long_name.txt",\n'
            ") as second_handle:\n",
        ),
        (
            ">=3.9",
            "with (\n"
            '    open("the_first_file_with_a_rather_long_name.txt") as first_handle,\n'
            '    open("the_second_file_with_a_long_name.txt") as second_handle,\n'
            "):\n",
        ),
    ],
)
def test_black_target_follows_requires_python(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
    requires_python: str,
    expected_with: str,
) -> None:
    """
    Parenthesized context managers are used only from a Python 3.9 lower bound.

    :param tmp_path: Project directory the fixture files are written to.
    :param monkeypatch: Used to run max-lint from the project directory.
    :param capfd: Captures the output of the tools the run starts.
    :param requires_python: Value of ``requires-python`` in the project.
    :param expected_with: Expected formatting of the ``with`` statement.
    """
    pyproject = f'[project]\nrequires-python = "{requires_python}"\n\n{PLAIN_PYPROJECT}'
    write_files(tmp_path, {"pyproject.toml": pyproject, "src/mod.py": LONG_WITH})

    lint(tmp_path, monkeypatch, capfd)

    assert (tmp_path / "src/mod.py").read_text() == f'"""Fixture module."""\n\n{expected_with}    pass\n'


def test_doc_codes_apply_to_test_paths_like_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """
    A function missing ``:param:`` lines reports DOC codes under ``test-paths`` as under ``paths``.

    :param tmp_path: Project directory the fixture files are written to.
    :param monkeypatch: Used to run max-lint from the project directory.
    :param capfd: Captures the output of the tools the run starts.
    """
    write_files(
        tmp_path,
        {
            "pyproject.toml": '[tool.max-lint]\npaths = ["lib"]\ntest-paths = ["checks"]\n',
            "lib/mod.py": UNDOCUMENTED_FUNCTION,
            "checks/nested/test_mod.py": UNDOCUMENTED_FUNCTION,
        },
    )

    exit_code, output = lint(tmp_path, monkeypatch, capfd, "--check")

    assert exit_code == 1
    assert flake8_codes(output) == [
        "checks/nested/test_mod.py:4:1: DOC101",
        "checks/nested/test_mod.py:4:1: DOC103",
        "checks/nested/test_mod.py:4:1: DOC201",
        "lib/mod.py:4:1: DOC101",
        "lib/mod.py:4:1: DOC103",
        "lib/mod.py:4:1: DOC201",
    ]


def test_documented_function_under_test_paths_passes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """
    A test file whose function documents every parameter and its return passes the lint.

    :param tmp_path: Project directory the fixture files are written to.
    :param monkeypatch: Used to run max-lint from the project directory.
    :param capfd: Captures the output of the tools the run starts.
    """
    documented = UNDOCUMENTED_FUNCTION.replace(
        "    :param first: Added to ``second``.\n",
        "    :param first: Added to ``second``.\n    :param second: Added to ``first``.\n    :return: Sum of both.\n",
    )
    write_files(
        tmp_path,
        {
            "pyproject.toml": '[tool.max-lint]\npaths = ["src"]\ntest-paths = ["tests"]\n',
            "src/mod.py": FORMATTED_MODULE,
            "tests/test_mod.py": documented,
        },
    )

    exit_code, _ = lint(tmp_path, monkeypatch, capfd, "--check")

    assert exit_code == 0


def test_check_mode_reports_unformatted_file_without_writing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """
    Check mode stops at black's failure and leaves the file byte-identical.

    :param tmp_path: Project directory the fixture files are written to.
    :param monkeypatch: Used to run max-lint from the project directory.
    :param capfd: Captures the output of the tools the run starts.
    """
    original = f"import json\n{UNFORMATTED_MODULE}".encode()
    write_files(tmp_path, {"pyproject.toml": PLAIN_PYPROJECT})
    (tmp_path / "src").mkdir()
    (tmp_path / "src/mod.py").write_bytes(original)

    exit_code, output = lint(tmp_path, monkeypatch, capfd, "--check")

    assert exit_code == 1
    assert "would reformat src/mod.py" in output
    assert "Imports are incorrectly sorted" not in output
    assert flake8_codes(output) == []
    assert (tmp_path / "src/mod.py").read_bytes() == original


def test_check_mode_reports_unsorted_imports_without_writing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """
    Check mode stops at isort's failure and leaves the file byte-identical.

    :param tmp_path: Project directory the fixture files are written to.
    :param monkeypatch: Used to run max-lint from the project directory.
    :param capfd: Captures the output of the tools the run starts.
    """
    original = b'"""Fixture module."""\n\nimport sys\nimport os\nimport json\n\nVALUE = (os.sep, sys.platform)\n'
    write_files(tmp_path, {"pyproject.toml": PLAIN_PYPROJECT})
    (tmp_path / "src/build").mkdir(parents=True)
    (tmp_path / "src/build/mod.py").write_bytes(original)

    exit_code, output = lint(tmp_path, monkeypatch, capfd, "--check")

    assert exit_code == 1
    assert "1 file would be left unchanged." in output
    assert "ERROR: <root>/src/build/mod.py Imports are incorrectly sorted and/or formatted." in output
    assert flake8_codes(output) == []
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
    """
    Write mode applies black and isort, then exits with flake8's result.

    :param tmp_path: Project directory the fixture files are written to.
    :param monkeypatch: Used to run max-lint from the project directory.
    :param capfd: Captures the output of the tools the run starts.
    :param extra_import: Import line added to the fixture module.
    :param expected_exit: Expected exit status.
    """
    module = UNFORMATTED_MODULE.replace("import sys\n", f"import sys\n{extra_import}")
    write_files(tmp_path, {"pyproject.toml": PLAIN_PYPROJECT, "src/mod.py": module})

    exit_code, _ = lint(tmp_path, monkeypatch, capfd)

    assert exit_code == expected_exit
    assert (tmp_path / "src/mod.py").read_text() == FORMATTED_MODULE.replace("import os\n", f"{extra_import}import os\n")


def test_ignored_codes_add_up_per_file_and_match_exactly(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """
    Each file ignores the union of the codes whose source matches it, and no other codes.

    :param tmp_path: Project directory the fixture files are written to.
    :param monkeypatch: Used to run max-lint from the project directory.
    :param capfd: Captures the output of the tools the run starts.
    """
    lambda_module = "import os\n\nSQUARE = lambda value: value * value\n"
    write_files(
        tmp_path,
        {
            "pyproject.toml": (
                '[tool.max-lint]\npaths = ["src"]\ntest-paths = ["tests", "test_main.py"]\n\n[tool.max-lint.per-file-ignores]\n'
                '"tests/__init__.py" = ["E731"]\n"./tests/test_a.py" = ["F401"]\n"src/pkg/__*" = ["E731"]\n'
                '"src/x y.py" = ["D100"]\n"other/y.py" = ["D100"]\n"src/m[[]1].py" = ["D100"]\n'
            ),
            "tests/__init__.py": lambda_module,
            "tests/test_a.py": '"""Fixture module."""\n\nimport os\n',
            "test_main.py": '"""Fixture module."""\n',
            "src/pkg/__init__.py": lambda_module,
            "src/pkg/test_main.py": '"""Fixture module."""\n' + SHORT_DOCSTRING,
            "src/other/y.py": "VALUE = 1\n",
            "src/m[1].py": "VALUE = 1\n",
            "src/m1.py": "VALUE = 1\n",
        },
    )

    exit_code, output = lint(tmp_path, monkeypatch, capfd, "--check")

    assert exit_code == 1
    assert flake8_codes(output) == [
        "src/m1.py:1:1: D100",
        "src/other/y.py:1:1: D100",
        "src/pkg/test_main.py:4:1: DOC101",
        "src/pkg/test_main.py:4:1: DOC103",
        "src/pkg/test_main.py:4:1: DOC201",
    ]


def test_per_file_ignores_apply_only_to_matching_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """
    An entry suppresses its code in the files its glob matches and nowhere else.

    :param tmp_path: Project directory the fixture files are written to.
    :param monkeypatch: Used to run max-lint from the project directory.
    :param capfd: Captures the output of the tools the run starts.
    """
    write_files(
        tmp_path,
        {
            "pyproject.toml": '[tool.max-lint]\npaths = ["app"]\nper-file-ignores = { "app/legacy_*.py" = ["D100"] }\n',
            "app/legacy_one.py": "VALUE = 1\n",
            "app/current.py": "VALUE = 1\n",
        },
    )

    exit_code, output = lint(tmp_path, monkeypatch, capfd, "--check")

    assert exit_code == 1
    assert flake8_codes(output) == ["app/current.py:1:1: D100"]


def test_exclude_removes_file_from_every_tool(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """
    Excluded files and the bundled ``.venv`` exclude are neither rewritten nor reported.

    :param tmp_path: Project directory the fixture files are written to.
    :param monkeypatch: Used to run max-lint from the project directory.
    :param capfd: Captures the output of the tools the run starts.
    """
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


def test_file_reached_through_two_spellings_is_linted_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """
    A file under both ``src`` and ``./src/other`` is checked once.

    :param tmp_path: Project directory the fixture files are written to.
    :param monkeypatch: Used to run max-lint from the project directory.
    :param capfd: Captures the output of the tools the run starts.
    """
    write_files(
        tmp_path,
        {"pyproject.toml": '[tool.max-lint]\npaths = ["src", "./src/other"]\n', "src/other/mod.py": "VALUE = 1\n"},
    )

    exit_code, output = lint(tmp_path, monkeypatch, capfd, "--check")

    assert exit_code == 1
    assert "1 file would be left unchanged." in output
    assert flake8_codes(output) == ["src/other/mod.py:1:1: D100"]


def test_path_outside_project_is_linted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """
    Files outside the project are rewritten and keep the ``__init__.py`` ignores, with no tools on ``PATH``.

    :param tmp_path: Directory holding ``project`` and the ``shared`` directory it lints.
    :param monkeypatch: Changes the working directory and sets ``PATH`` to a directory that does not exist.
    :param capfd: Captures the output of the tools the run starts.
    """
    write_files(
        tmp_path,
        {
            "project/pyproject.toml": '[tool.max-lint]\npaths = ["../shared/etl"]\n',
            "shared/etl/__init__.py": "import os\n",
            "shared/etl/job.py": UNFORMATTED_MODULE,
        },
    )
    monkeypatch.setenv("PATH", str(tmp_path / "no-tools"))

    exit_code, output = lint(tmp_path / "project", monkeypatch, capfd)

    assert exit_code == 0
    assert "reformatted ../shared/etl/job.py" in output
    assert (tmp_path / "shared/etl/job.py").read_text() == FORMATTED_MODULE


@pytest.mark.parametrize(
    "planted",
    [
        "black.py",
        "click.py",
        "isort/__init__.py",
        "flake8/__init__.py",
        "mypy.py",
        "pathspec/__init__.py",
        "add_trailing_comma.py",
        "tokenize_rt.py",
    ],
)
def test_project_modules_named_like_tools_are_not_imported(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
    planted: str,
) -> None:
    """
    A module at the project root named like a tool or a dependency never runs.

    :param tmp_path: Project directory the fixture files are written to.
    :param monkeypatch: Used to run max-lint from the project directory.
    :param capfd: Captures the output of the tools the run starts.
    :param planted: Path of the module named like a tool.
    """
    marker = tmp_path / "imported"
    write_files(
        tmp_path,
        {"pyproject.toml": PLAIN_PYPROJECT, "src/mod.py": UNFORMATTED_MODULE, planted: f"open({str(marker)!r}, 'w').close()\n"},
    )

    check = lint(tmp_path, monkeypatch, capfd, "--check")
    write = lint(tmp_path, monkeypatch, capfd)

    assert (check[0], write[0]) == (1, 0)
    assert "would reformat src/mod.py" in check[1]
    assert (tmp_path / "src/mod.py").read_text() == FORMATTED_MODULE
    assert not marker.exists()


@pytest.mark.parametrize("arguments", [("--check",), ()], ids=["check", "write"])
def test_docstring_parsing_ignores_project_docutils_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
    arguments: tuple[str, ...],
) -> None:
    """
    A ``docutils.conf`` in the project, even one named by ``DOCUTILSCONFIG``, does not open the files it names.

    :param tmp_path: Directory holding ``project`` and the file its docutils config names.
    :param monkeypatch: Changes the working directory and sets ``DOCUTILSCONFIG`` to the project file.
    :param capfd: Captures the output of the tools the run starts.
    :param arguments: Arguments given to max-lint.
    """
    outside = tmp_path / "outside.txt"
    outside.write_text("unchanged\n")
    write_files(
        tmp_path,
        {
            "project/pyproject.toml": PLAIN_PYPROJECT,
            "project/docutils.conf": f"[general]\nwarning_stream: {outside}\nrecord_dependencies: {outside}\n",
            "project/src/mod.py": '"""Do *bad."""\n',
        },
    )

    monkeypatch.setenv("DOCUTILSCONFIG", str(tmp_path / "project/docutils.conf"))

    exit_code, output = lint(tmp_path / "project", monkeypatch, capfd, *arguments)

    assert exit_code == 1
    assert flake8_codes(output) == ["src/mod.py:1:1: RST213"]
    assert outside.read_text() == "unchanged\n"


def test_docstring_raw_and_include_directives_are_disabled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """
    A ``raw`` directive with a URL fetches nothing, and ``raw`` and ``include`` are reported as disabled.

    :param tmp_path: Project directory the fixture files are written to.
    :param monkeypatch: Used to run max-lint from the project directory.
    :param capfd: Captures the output of the tools the run starts.
    """
    BeaconHandler.received.clear()
    server = http.server.HTTPServer(("127.0.0.1", 0), BeaconHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    docstring = (
        f'"""\nFixture module.\n\n.. raw:: html\n   :url: http://127.0.0.1:{server.server_address[1]}/beacon\n\n'
        f'.. include:: {tmp_path}\n\n.. raw:: html\n\n   <b>inline</b>\n"""\n'
    )
    write_files(tmp_path, {"pyproject.toml": PLAIN_PYPROJECT, "src/mod.py": docstring})

    exit_code, output = lint(tmp_path, monkeypatch, capfd, "--check")
    server.shutdown()
    server.server_close()

    assert BeaconHandler.received == []
    assert exit_code == 1
    assert re.findall(r"RST299 .*", output) == [
        'RST299 "raw" directive disabled.',
        'RST299 "include" directive disabled.',
        'RST299 "raw" directive disabled.',
    ]


def test_symlinked_directory_listed_with_its_target_is_linted_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """
    A file reached through a symlinked directory and through its target is reported once.

    :param tmp_path: Project directory the fixture files are written to.
    :param monkeypatch: Used to run max-lint from the project directory.
    :param capfd: Captures the output of the tools the run starts.
    """
    write_files(tmp_path, {"pyproject.toml": '[tool.max-lint]\npaths = ["src", "link"]\n', "src/pkg/mod.py": "VALUE = 1\n"})
    (tmp_path / "link").symlink_to(tmp_path / "src/pkg", target_is_directory=True)

    exit_code, output = lint(tmp_path, monkeypatch, capfd, "--check")

    assert exit_code == 1
    assert "1 file would be left unchanged." in output
    assert flake8_codes(output) == ["src/pkg/mod.py:1:1: D100"]


def test_unresolvable_python_entries_are_skipped(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """
    Dangling and looping symlinks and a device named like Python files are left out and the rest is linted.

    :param tmp_path: Project directory the fixture files are written to.
    :param monkeypatch: Used to run max-lint from the project directory.
    :param capfd: Captures the output of the tools the run starts.
    """
    write_files(tmp_path, {"pyproject.toml": PLAIN_PYPROJECT, "src/mod.py": FORMATTED_MODULE})
    (tmp_path / "src/dangling.py").symlink_to("nowhere.py")
    (tmp_path / "src/loop.py").symlink_to("loop.py")
    (tmp_path / "src/.#mod.py").symlink_to("user@host.local.12345:1700000000")
    (tmp_path / "src/null.py").symlink_to("/dev/null")

    exit_code, output = lint(tmp_path, monkeypatch, capfd, "--check")

    assert exit_code == 0
    assert "1 file would be left unchanged." in output


def test_only_unresolvable_python_entries_is_a_configuration_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """
    A project whose only Python entry is a dangling symlink has no Python files to lint.

    :param tmp_path: Project directory the fixture files are written to.
    :param monkeypatch: Used to run max-lint from the project directory.
    :param capfd: Captures the output of the tools the run starts.
    """
    write_files(tmp_path, {"pyproject.toml": PLAIN_PYPROJECT})
    (tmp_path / "src").mkdir()
    (tmp_path / "src/dangling.py").symlink_to("nowhere.py")

    exit_code, output = lint(tmp_path, monkeypatch, capfd, "--check")

    assert exit_code == 2
    assert output == (
        "max-lint: no Python files found under 'paths' and 'test-paths' in [tool.max-lint]; point them at Python sources.\n"
    )


def test_case_variant_spellings_are_linted_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """
    On a case-insensitive file system a file reached as ``src`` and ``SRC/pkg`` is reported once.

    :param tmp_path: Project directory the fixture files are written to.
    :param monkeypatch: Used to run max-lint from the project directory.
    :param capfd: Captures the output of the tools the run starts.
    """
    write_files(tmp_path, {"pyproject.toml": '[tool.max-lint]\npaths = ["src", "SRC/pkg"]\n', "src/pkg/mod.py": "VALUE = 1\n"})

    if not (tmp_path / "SRC").exists():
        pytest.skip("the file system is case-sensitive")

    exit_code, output = lint(tmp_path, monkeypatch, capfd, "--check")

    assert exit_code == 1
    assert flake8_codes(output) == ["src/pkg/mod.py:1:1: D100"]


def run_check_command(root: Path, piped: str = "") -> tuple[int, str]:
    """
    Run ``max-lint lint --check`` as a process in ``root`` and return its exit code and combined output.

    :param root: Project directory the process runs in.
    :param piped: Text written to the process's standard input.
    :return: Exit code and combined output.
    :raises subprocess.TimeoutExpired: when the run does not end within the time limit.
    """
    process = subprocess.Popen(
        [str(Path(sys.executable).parent / "max-lint"), "lint", "--check"],
        cwd=root,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )

    try:
        output, _ = process.communicate(piped, timeout=60)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.communicate()
        raise

    return process.returncode, output


def test_fifo_and_endless_device_are_left_out(tmp_path: Path) -> None:
    """
    A FIFO and a symlink to ``/dev/zero`` named like Python files are not linted.

    :param tmp_path: Project directory the fixture files are written to.
    """
    write_files(tmp_path, {"pyproject.toml": PLAIN_PYPROJECT, "src/mod.py": FORMATTED_MODULE})
    os.mkfifo(tmp_path / "src/fifo.py")
    (tmp_path / "src/zero.py").symlink_to("/dev/zero")

    exit_code, output = run_check_command(tmp_path)

    assert exit_code == 0
    assert "1 file would be left unchanged." in output


def test_file_named_dash_in_a_subdirectory_is_linted_not_read_from_stdin(tmp_path: Path) -> None:
    """
    ``sub/-`` holds what only black flags; the piped text is clean, so a tool reading it would pass.

    :param tmp_path: Project directory the fixture files are written to.
    """
    write_files(tmp_path, {"pyproject.toml": '[tool.max-lint]\npaths = ["sub/-"]\n', "sub/-": "VALUE = {'a':1}\n"})

    exit_code, output = run_check_command(tmp_path, piped=FORMATTED_MODULE)

    assert exit_code == 1
    assert "would reformat sub/-" in output


@pytest.mark.parametrize("arguments", [("--check",), ()], ids=["check", "write"])
@pytest.mark.parametrize(
    "settings",
    ['paths = ["-"]', 'paths = ["./-"]', 'paths = ["src"]\ntest-paths = ["-"]', 'paths = ["src", "-"]'],
    ids=["paths", "dot-slash", "test-paths", "beside-others"],
)
def test_file_named_dash_stops_the_run_before_any_tool_starts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
    settings: str,
    arguments: tuple[str, ...],
) -> None:
    """
    A file ``-`` in the project root is rejected with exit status 2 and no command runs.

    :param tmp_path: Project directory the fixture files are written to.
    :param monkeypatch: Used to run max-lint from the project directory and to record started commands.
    :param capfd: Captures the output of the run.
    :param settings: Lines of the ``[tool.max-lint]`` table.
    :param arguments: Arguments given to ``max-lint lint``.
    """
    write_files(
        tmp_path,
        {"pyproject.toml": f"[tool.max-lint]\n{settings}\n", "src/mod.py": FORMATTED_MODULE, "-": FORMATTED_MODULE},
    )
    started: list[list[str]] = []
    monkeypatch.setattr("max_lint.cli.subprocess.run", lambda command, **_: started.append(command))

    exit_code, output = lint(tmp_path, monkeypatch, capfd, *arguments)

    assert exit_code == 2
    assert "read as standard input; rename the file." in output
    assert started == []


@pytest.mark.parametrize("arguments", [("--check",), ()], ids=["check", "write"])
def test_mypy_runs_last_over_source_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
    arguments: tuple[str, ...],
) -> None:
    """
    An unannotated function under ``paths`` fails the mypy step with mypy's own error.

    :param tmp_path: Project directory the fixture files are written to.
    :param monkeypatch: Used to run max-lint from the project directory.
    :param capfd: Captures the output of the tools the run starts.
    :param arguments: Arguments given to max-lint.
    """
    write_files(tmp_path, {"pyproject.toml": PLAIN_PYPROJECT, "src/mod.py": UNTYPED_FUNCTION})

    exit_code, output = lint(tmp_path, monkeypatch, capfd, *arguments)

    assert exit_code == 1
    assert MYPY_ERROR in output
    assert "Found 1 error in 1 file (checked 1 source file)" in output


@pytest.mark.parametrize(
    ("source", "error"),
    [
        (UNTYPED_FUNCTION, MYPY_ERROR.replace("src/mod.py", "tests/test_mod.py")),
        (EXPLICIT_ANY, 'tests/test_mod.py:5: error: Explicit "Any" is not allowed'),
    ],
    ids=["untyped-function", "explicit-any"],
)
def test_mypy_checks_test_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
    source: str,
    error: str,
) -> None:
    """
    A file under ``test-paths`` fails the mypy step and is counted among the checked files.

    :param tmp_path: Project directory the fixture files are written to.
    :param monkeypatch: Used to run max-lint from the project directory.
    :param capfd: Captures the output of the tools the run starts.
    :param source: Contents of the fixture module.
    :param error: Error mypy is expected to report.
    """
    write_files(
        tmp_path,
        {
            "pyproject.toml": '[tool.max-lint]\npaths = ["src"]\ntest-paths = ["tests"]\n',
            "src/mod.py": FORMATTED_MODULE,
            "tests/test_mod.py": source,
        },
    )

    exit_code, output = lint(tmp_path, monkeypatch, capfd, "--check")

    assert exit_code == 1
    assert error in output
    assert "Found 1 error in 1 file (checked 2 source files)" in output


def test_mypy_does_not_run_after_a_flake8_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """
    A flake8 failure stops the command before mypy starts.

    :param tmp_path: Project directory the fixture files are written to.
    :param monkeypatch: Used to run max-lint from the project directory.
    :param capfd: Captures the output of the tools the run starts.
    """
    write_files(tmp_path, {"pyproject.toml": PLAIN_PYPROJECT, "src/mod.py": "def run():\n    pass\n"})

    exit_code, output = lint(tmp_path, monkeypatch, capfd, "--check")

    assert exit_code == 1
    assert "src/mod.py:1:1: D100" in output
    assert "no-untyped-def" not in output


@pytest.mark.parametrize(
    ("source", "error"),
    [
        (
            '"""Fixture module."""\n\nfrom typing import cast\n\nVALUE = cast(int, 1)\n',
            'src/mod.py:5: error: Redundant cast to "int"',
        ),
        (
            '"""Fixture module."""\n\n\ndef run(value: int = None) -> None:\n    """\n    Do nothing.\n\n    :param value: Defaults to ``None`` against its ``int`` annotation.\n    """\n',
            'src/mod.py:4: error: Incompatible default for parameter "value"',
        ),
        (BARE_GENERIC, 'src/mod.py:3: error: Missing type arguments for generic type "dict"'),
        (EXPLICIT_ANY, 'src/mod.py:5: error: Explicit "Any" is not allowed'),
        (RETURNED_ANY, 'src/mod.py:12: error: Returning Any from function declared to return "int"'),
    ],
    ids=["redundant-cast", "implicit-optional", "bare-generic", "explicit-any", "returned-any"],
)
def test_mypy_locked_settings_apply_without_project_settings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
    source: str,
    error: str,
) -> None:
    """
    A project with no ``[tool.mypy]`` table is checked with the locked settings.

    :param tmp_path: Project directory the fixture files are written to.
    :param monkeypatch: Used to run max-lint from the project directory.
    :param capfd: Captures the output of the tools the run starts.
    :param source: Contents of the fixture module.
    :param error: Error mypy is expected to report.
    """
    write_files(tmp_path, {"pyproject.toml": PLAIN_PYPROJECT, "src/mod.py": source})

    exit_code, output = lint(tmp_path, monkeypatch, capfd, "--check")

    assert exit_code == 1
    assert error in output


def test_mypy_command_receives_the_files_flake8_receives(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """
    The mypy command lists the files under ``paths`` and ``test-paths`` that the flake8 command lists.

    :param tmp_path: Project directory, also passed as the scratch directory.
    :param monkeypatch: Changes the working directory so the project's ``pyproject.toml`` resolves.
    """
    pyproject = '[tool.max-lint]\npaths = ["src"]\ntest-paths = ["tests"]\n'
    write_files(tmp_path, {"pyproject.toml": pyproject, "src/mod.py": FORMATTED_MODULE, "tests/test_mod.py": FORMATTED_MODULE})
    monkeypatch.chdir(tmp_path)

    commands = lint_commands(load_config(Path("pyproject.toml")), check=True, scratch=tmp_path)

    assert commands[2][-2:] == ["src/mod.py", "tests/test_mod.py"]
    assert commands[-1][-2:] == ["./src/mod.py", "./tests/test_mod.py"]


def test_mypy_command_carries_the_locked_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """
    The mypy command passes the project's pyproject.toml and the locked flags.

    :param tmp_path: Project directory, also passed as the scratch directory.
    :param monkeypatch: Changes the working directory so the project's ``pyproject.toml`` resolves.
    """
    write_files(tmp_path, {"pyproject.toml": PLAIN_PYPROJECT, "src/mod.py": FORMATTED_MODULE})
    monkeypatch.chdir(tmp_path)

    commands = lint_commands(load_config(Path("pyproject.toml")), check=True, scratch=tmp_path)

    assert commands[-1] == [
        sys.executable,
        "-m",
        "mypy",
        "--config-file",
        str(tmp_path.resolve() / "pyproject.toml"),
        "--python-executable",
        sys.executable,
        "--disallow-untyped-defs",
        "--warn-redundant-casts",
        "--no-implicit-optional",
        "--disallow-any-unimported",
        "--disallow-any-generics",
        "--disallow-any-explicit",
        "--warn-return-any",
        "--",
        "./src/mod.py",
    ]


def test_mypy_rejects_an_unimported_class_in_an_annotation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """
    A class from an ``ignore_missing_imports`` module fails when used in an annotation.

    :param tmp_path: Project directory the fixture files are written to.
    :param monkeypatch: Used to run max-lint from the project directory.
    :param capfd: Captures the output of the tools the run starts.
    """
    write_files(tmp_path, {"pyproject.toml": PLAIN_PYPROJECT + UNTYPED_LIBRARY_OVERRIDE, "src/mod.py": UNTYPED_LIBRARY_CLASS})

    exit_code, output = lint(tmp_path, monkeypatch, capfd, "--check")

    assert exit_code == 1
    assert 'src/mod.py:6: error: Argument 1 to "run" becomes "Any" due to an unfollowed import' in output


@pytest.mark.parametrize(("overrides", "exit_code"), [(UNREACHABLE_OVERRIDE, 1), ("", 0)], ids=["with-override", "without"])
def test_mypy_reads_project_overrides(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
    overrides: str,
    exit_code: int,
) -> None:
    """
    A ``warn_unreachable`` override in ``[[tool.mypy.overrides]]`` decides whether an unreachable branch fails.

    :param tmp_path: Project directory the fixture files are written to.
    :param monkeypatch: Used to run max-lint from the project directory.
    :param capfd: Captures the output of the tools the run starts.
    :param overrides: mypy settings appended to the project's ``pyproject.toml``.
    :param exit_code: Expected exit status.
    """
    write_files(tmp_path, {"pyproject.toml": PLAIN_PYPROJECT + overrides, "src/mod.py": UNREACHABLE_BRANCH})

    result, output = lint(tmp_path, monkeypatch, capfd, "--check")

    assert result == exit_code
    assert ("Statement is unreachable" in output) == bool(exit_code)


def test_mypy_ignores_other_mypy_config_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """
    A ``mypy.ini`` that relaxes a locked setting for a module does not change the result.

    :param tmp_path: Project directory the fixture files are written to.
    :param monkeypatch: Used to run max-lint from the project directory.
    :param capfd: Captures the output of the tools the run starts.
    """
    write_files(
        tmp_path,
        {
            "pyproject.toml": PLAIN_PYPROJECT,
            "src/mod.py": UNTYPED_FUNCTION,
            "mypy.ini": "[mypy-mod]\ndisallow_untyped_defs = False\n",
        },
    )

    exit_code, output = lint(tmp_path, monkeypatch, capfd, "--check")

    assert exit_code == 1
    assert MYPY_ERROR in output


def test_mypy_loads_plugins_named_in_the_project(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """
    A plugin given as a file path in ``[tool.mypy]`` is loaded.

    :param tmp_path: Project directory the fixture files are written to.
    :param monkeypatch: Used to run max-lint from the project directory.
    :param capfd: Captures the output of the tools the run starts.
    """
    marker = tmp_path / "loaded"
    write_files(
        tmp_path,
        {
            "pyproject.toml": PLAIN_PYPROJECT + '\n[tool.mypy]\nplugins = ["plugin.py"]\n',
            "src/mod.py": FORMATTED_MODULE,
            "plugin.py": f"from mypy.plugin import Plugin\n\nopen({str(marker)!r}, 'w').close()\n\n\ndef plugin(version):\n    return Plugin\n",
        },
    )

    exit_code, _ = lint(tmp_path, monkeypatch, capfd, "--check")

    assert exit_code == 0
    assert marker.exists()


def test_mypy_leaves_out_excluded_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """
    A file matched by ``exclude`` is not type-checked.

    :param tmp_path: Project directory the fixture files are written to.
    :param monkeypatch: Used to run max-lint from the project directory.
    :param capfd: Captures the output of the tools the run starts.
    """
    write_files(
        tmp_path,
        {
            "pyproject.toml": '[tool.max-lint]\npaths = ["src"]\nexclude = ["src/generated.py"]\n',
            "src/mod.py": FORMATTED_MODULE,
            "src/generated.py": UNTYPED_FUNCTION,
        },
    )

    exit_code, output = lint(tmp_path, monkeypatch, capfd, "--check")

    assert exit_code == 0
    assert "Success: no issues found in 1 source file" in output


def test_mypy_checks_a_file_reached_twice_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """
    A file reached through a symlinked directory and through its target is type-checked once.

    :param tmp_path: Project directory the fixture files are written to.
    :param monkeypatch: Used to run max-lint from the project directory.
    :param capfd: Captures the output of the tools the run starts.
    """
    write_files(tmp_path, {"pyproject.toml": '[tool.max-lint]\npaths = ["src", "link"]\n', "src/pkg/mod.py": UNTYPED_FUNCTION})
    (tmp_path / "link").symlink_to(tmp_path / "src/pkg", target_is_directory=True)

    exit_code, output = lint(tmp_path, monkeypatch, capfd, "--check")

    assert exit_code == 1
    assert output.count("no-untyped-def") == 1
    assert "Found 1 error in 1 file (checked 1 source file)" in output


@pytest.mark.parametrize(
    ("overrides", "place"),
    [
        ("\n[tool.mypy]\ndisallow_untyped_defs = false\n", "[tool.mypy]"),
        (
            '\n[[tool.mypy.overrides]]\nmodule = "mod"\ndisallow_untyped_defs = false\n',
            "[[tool.mypy.overrides]] for module 'mod'",
        ),
    ],
    ids=["table", "override"],
)
def test_locked_mypy_key_is_rejected_before_any_tool_runs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
    overrides: str,
    place: str,
) -> None:
    """
    A locked key in the project's mypy settings exits 2, naming the key, and rewrites nothing.

    :param tmp_path: Project directory the fixture files are written to.
    :param monkeypatch: Used to run max-lint from the project directory.
    :param capfd: Captures the output of the tools the run starts.
    :param overrides: mypy settings appended to the project's ``pyproject.toml``.
    :param place: Where the message says the key is set.
    """
    write_files(tmp_path, {"pyproject.toml": PLAIN_PYPROJECT + overrides, "src/mod.py": UNFORMATTED_MODULE})

    exit_code, output = lint(tmp_path, monkeypatch, capfd)

    assert exit_code == 2
    assert output == f"max-lint: 'disallow_untyped_defs' is set in {place}, but max-lint fixes it; remove it.\n"
    assert (tmp_path / "src/mod.py").read_text() == UNFORMATTED_MODULE


def test_mypy_workers_do_not_import_project_modules(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """
    A root module named like a mypy dependency does not run in mypy's worker processes.

    :param tmp_path: Project directory the fixture files are written to.
    :param monkeypatch: Used to run max-lint from the project directory.
    :param capfd: Captures the output of the tools the run starts.
    """
    marker = tmp_path / "imported"
    write_files(
        tmp_path,
        {
            "pyproject.toml": PLAIN_PYPROJECT + "\n[tool.mypy]\nnum_workers = 2\nlocal_partial_types = true\n",
            "src/mod.py": FORMATTED_MODULE,
            "librt.py": f"open({str(marker)!r}, 'w').close()\n",
        },
    )

    exit_code, output = lint(tmp_path, monkeypatch, capfd, "--check")

    assert exit_code == 0
    assert "Success: no issues found in 1 source file" in output
    assert not marker.exists()


def test_mypy_ignores_the_python_executable_named_by_the_project(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """
    A ``python_executable`` in ``[tool.mypy]`` is not run.

    :param tmp_path: Project directory the fixture files are written to.
    :param monkeypatch: Used to run max-lint from the project directory.
    :param capfd: Captures the output of the tools the run starts.
    """
    marker = tmp_path / "imported"
    write_files(
        tmp_path,
        {
            "pyproject.toml": PLAIN_PYPROJECT + '\n[tool.mypy]\npython_executable = "./evil.sh"\n',
            "src/mod.py": FORMATTED_MODULE,
            "evil.sh": f'#!/bin/sh\ntouch {str(marker)!r}\nexec {sys.executable!r} "$@"\n',
        },
    )
    (tmp_path / "evil.sh").chmod(0o755)

    exit_code, _ = lint(tmp_path, monkeypatch, capfd, "--check")

    assert exit_code == 0
    assert not marker.exists()


def test_mypy_checks_a_file_whose_name_starts_with_at_sign(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """
    A file named ``@x.py`` is type-checked, not read as a file of arguments.

    :param tmp_path: Project directory the fixture files are written to.
    :param monkeypatch: Used to run max-lint from the project directory.
    :param capfd: Captures the output of the tools the run starts.
    """
    write_files(tmp_path, {"pyproject.toml": '[tool.max-lint]\npaths = ["@x.py"]\n', "@x.py": MISTYPED_VALUE})

    exit_code, output = lint(tmp_path, monkeypatch, capfd, "--check")

    assert exit_code == 1
    assert '@x.py:3: error: Incompatible types in assignment (expression has type "str", variable has type "int")' in output


def test_one_write_run_adds_the_trailing_commas_black_leaves_out(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """
    Check mode writes nothing, one write run passes with one black summary, and a second write run changes no byte.

    :param tmp_path: Project directory the fixture files are written to.
    :param monkeypatch: Used to run max-lint from the project directory.
    :param capfd: Captures the output of the tools the run starts.
    """
    module = tmp_path / "src/mod.py"
    write_files(tmp_path, {"pyproject.toml": PLAIN_PYPROJECT, "src/mod.py": MISSING_COMMAS})

    check, _ = lint(tmp_path, monkeypatch, capfd, "--check")
    unchanged = module.read_text() == MISSING_COMMAS
    write, output = lint(tmp_path, monkeypatch, capfd)
    settled = module.read_bytes()
    lint(tmp_path, monkeypatch, capfd)

    assert (check, unchanged, write) == (1, True, 0)
    assert output.count("All done!") == 1
    assert module.read_bytes() == settled


def test_check_mode_reports_a_missing_comma_and_writes_nothing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """
    flake8 reports the comma black leaves out, and the file keeps its bytes.

    :param tmp_path: Project directory the fixture files are written to.
    :param monkeypatch: Used to run max-lint from the project directory.
    :param capfd: Captures the output of the tools the run starts.
    """
    write_files(tmp_path, {"pyproject.toml": PLAIN_PYPROJECT, "src/mod.py": DOC_ITEMS})

    _, output = lint(tmp_path, monkeypatch, capfd, "--check")

    assert (tmp_path / "src/mod.py").read_text() == DOC_ITEMS
    assert flake8_codes(output) == ["src/mod.py:4:127: C812"]


def test_multi_line_fstring_field_keeps_its_finding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """
    A container in a multi-line replacement field gets its inner comma and the field stays reported; on one line it does not.

    :param tmp_path: Project directory the fixture files are written to.
    :param monkeypatch: Used to run max-lint from the project directory.
    :param capfd: Captures the output of the tools the run starts.
    """
    header = '"""Fixture module."""\n\n'
    multi = header + 'NAME = f"{\n    [\n        1,\n        2\n    ]\n}"\n'
    single = header + 'NAME = f"{[1, 2]}"\n'
    write_files(tmp_path, {"pyproject.toml": PLAIN_PYPROJECT, "src/multi.py": multi, "src/single.py": single})

    _, output = lint(tmp_path, monkeypatch, capfd)

    assert [code for code in flake8_codes(output) if "C81" in code] == ["src/multi.py:7:6: C812"]
    assert (tmp_path / "src/multi.py").read_text() == multi.replace("2\n", "2,\n")


@pytest.mark.parametrize(
    ("source", "row"),
    [
        pytest.param(NESTED_SPEC, 9, id="nested-spec"),
        pytest.param(TRIPLE_QUOTED_SPEC, 11, id="triple-quoted-spec"),
        pytest.param(
            TEMPLATE_CALL,
            8,
            id="template-call",
            marks=pytest.mark.skipif(sys.version_info < (3, 14), reason="template strings need Python 3.14"),
        ),
        pytest.param('"""Fixture module."""\n\nVALUE = f"{max(\n    1,\n    2,\n)=}"\n', 8, id="debug-field"),
    ],
)
def test_rewrite_that_changes_the_syntax_tree_is_not_written(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
    source: str,
    row: int,
) -> None:
    """
    A file whose rewrite would not parse, or would mean something else, keeps its bytes and every missing comma.

    :param tmp_path: Project directory the fixture files are written to.
    :param monkeypatch: Used to run max-lint from the project directory.
    :param capfd: Captures the output of the tools the run starts.
    :param source: Module text the comma step would rewrite, before a second missing comma is appended.
    :param row: Row of the appended missing comma as flake8 reports it.
    """
    module = tmp_path / "src/mod.py"
    content = (source + LONG_ITEMS).encode()
    write_files(tmp_path, {"pyproject.toml": PLAIN_PYPROJECT})
    module.parent.mkdir()
    module.write_bytes(content)
    before = repr(runpy.run_path(str(module))["VALUE"])

    _, output = lint(tmp_path, monkeypatch, capfd)

    assert module.read_bytes() == content
    assert repr(runpy.run_path(str(module))["VALUE"]) == before
    assert f"src/mod.py:{row}:127: C812" in flake8_codes(output)


def test_file_with_a_byte_order_mark_gets_its_commas_and_keeps_the_mark(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """
    The missing comma is added and the mark stays first, before a bracket on the first line.

    :param tmp_path: Project directory the fixture files are written to.
    :param monkeypatch: Used to run max-lint from the project directory.
    :param capfd: Captures the output of the tools the run starts.
    """
    module = tmp_path / "src/mod.py"
    write_files(tmp_path, {"pyproject.toml": PLAIN_PYPROJECT})
    module.parent.mkdir()
    module.write_bytes(codecs.BOM_UTF8 + f"x = [1]\n{LONG_ITEMS}".encode())

    lint(tmp_path, monkeypatch, capfd)

    assert module.read_bytes() == codecs.BOM_UTF8 + f"x = [1]\n{LONG_ITEMS}".replace('"\n]', '",\n]').encode()


def test_read_only_file_keeps_its_finding_and_the_run_continues(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """
    The file is left as it was and flake8 reports its missing comma, while another file gains its comma.

    :param tmp_path: Project directory the fixture files are written to.
    :param monkeypatch: Used to run max-lint from the project directory.
    :param capfd: Captures the output of the tools the run starts.
    """
    stuck = tmp_path / "src/stuck.py"
    write_files(tmp_path, {"pyproject.toml": PLAIN_PYPROJECT, "src/ordinary.py": DOC_ITEMS, "src/stuck.py": DOC_ITEMS})
    stuck.chmod(0o444)

    _, output = lint(tmp_path, monkeypatch, capfd)

    assert stuck.read_text() == DOC_ITEMS
    assert (tmp_path / "src/ordinary.py").read_text() == WITH_COMMA
    assert [code for code in flake8_codes(output) if "C81" in code] == ["src/stuck.py:4:127: C812"]


def test_file_that_is_not_utf8_and_has_no_coding_line_stops_the_run_at_black(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """
    The file keeps its bytes, and black fails on it before the comma step runs.

    :param tmp_path: Project directory the fixture files are written to.
    :param monkeypatch: Used to run max-lint from the project directory.
    :param capfd: Captures the output of the tools the run starts.
    """
    write_files(tmp_path, {"pyproject.toml": PLAIN_PYPROJECT, "src/ordinary.py": DOC_ITEMS})
    (tmp_path / "src/bad.py").write_bytes(b'VALUE = "\xff"\n')

    exit_code, output = lint(tmp_path, monkeypatch, capfd)

    assert exit_code == 1
    assert (tmp_path / "src/bad.py").read_bytes() == b'VALUE = "\xff"\n'
    assert (tmp_path / "src/ordinary.py").read_text() == DOC_ITEMS
    assert "error: cannot format src/bad.py: invalid or missing encoding declaration" in output


@pytest.mark.parametrize(
    "source",
    [
        WITH_COMMA,
        '"""Doc."""\n\nN = f"{max(\n    1,\n    2,\n)}"\n',
        f'"""Doc."""\n\n{WITH_ITEM}',
        DOC_ITEMS + LONG_ITEMS + WITH_ITEM,
    ],
    ids=["nothing-missing", "layout-only", "comma-removed", "comma-removed-and-two-added"],
)
def test_file_that_gains_no_comma_is_not_written(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
    source: str,
) -> None:
    """
    The file keeps its bytes and modification time and reports the same flake8 codes after a write run as under check mode.

    :param tmp_path: Project directory the fixture files are written to.
    :param monkeypatch: Used to run max-lint from the project directory.
    :param capfd: Captures the output of the tools the run starts.
    :param source: Module whose rewrite would insert no comma, or would also change something else.
    """
    module = tmp_path / "src/mod.py"
    write_files(tmp_path, {"pyproject.toml": PLAIN_PYPROJECT, "src/mod.py": source})
    os.utime(module, ns=(10**9, 10**9))

    _, check = lint(tmp_path, monkeypatch, capfd, "--check")
    _, write = lint(tmp_path, monkeypatch, capfd)

    assert (module.read_text(), module.stat().st_mtime_ns) == (source, 10**9)
    assert flake8_codes(write) == flake8_codes(check)


@pytest.mark.parametrize(
    "content",
    [
        b'"""Doc."""\n\n# fmt: off\nMATRIX = [1, 0,\n          0, 1]\n# fmt: on\n',
        f'# coding: latin-1\n"""Doc \xe9."""\n\n{LONG_ITEMS}'.encode(),
        b"# a\rB = 1  # coding: iso2022_jp\nV = [1,\n    2]  # fmt\x1b(B: skip\n",
        b'"""Doc."""\n\nX = 1\r# fmt: off\nV = [1,\n    2]\n',
    ],
    ids=["fmt-off", "latin-1-valid-utf-8", "bare-cr-iso2022-jp-fmt-skip", "bare-cr-fmt-off"],
)
def test_file_that_opts_out_of_black_or_is_not_read_alike_by_every_reader_is_left_alone(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
    content: bytes,
) -> None:
    """
    The file keeps its bytes and its flake8 codes, while another file in the same run gains its comma.

    :param tmp_path: Project directory the fixture files are written to.
    :param monkeypatch: Used to run max-lint from the project directory.
    :param capfd: Captures the output of the tools the run starts.
    :param content: Bytes of a module with a black directive, another declared encoding or a bare carriage return.
    """
    module = tmp_path / "src/mod.py"
    write_files(tmp_path, {"pyproject.toml": PLAIN_PYPROJECT, "src/ordinary.py": DOC_ITEMS})
    module.write_bytes(content)

    _, check = lint(tmp_path, monkeypatch, capfd, "--check")
    _, write = lint(tmp_path, monkeypatch, capfd)

    assert module.read_bytes() == content
    assert (tmp_path / "src/ordinary.py").read_text() == WITH_COMMA
    assert [code for code in flake8_codes(write) if "mod.py" in code] == [
        code for code in flake8_codes(check) if "mod.py" in code
    ]


@pytest.mark.parametrize("line", ['X = "a;fmt: off;b"\n', 'X = f"# fmt: off{1}"\n'], ids=["string", "f-string"])
def test_directive_text_outside_a_comment_does_not_stop_the_step(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
    line: str,
) -> None:
    """
    A file whose string holds directive text gains its comma.

    :param tmp_path: Project directory the fixture files are written to.
    :param monkeypatch: Used to run max-lint from the project directory.
    :param capfd: Captures the output of the tools the run starts.
    :param line: Statement holding directive text in a string.
    """
    write_files(tmp_path, {"pyproject.toml": PLAIN_PYPROJECT, "src/mod.py": f'"""Doc."""\n\n{line}{LONG_ITEMS}'})

    lint(tmp_path, monkeypatch, capfd)

    assert (tmp_path / "src/mod.py").read_text() == f'"""Doc."""\n\n{line}{LONG_ITEMS}'.replace('"\n]', '",\n]')


def test_call_split_in_an_fstring_field_moves_when_the_file_gains_a_comma(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """
    The field is put on lines of its own and keeps a finding, while the file gains its missing comma.

    :param tmp_path: Project directory the fixture files are written to.
    :param monkeypatch: Used to run max-lint from the project directory.
    :param capfd: Captures the output of the tools the run starts.
    """
    write_files(
        tmp_path,
        {"pyproject.toml": PLAIN_PYPROJECT, "src/mod.py": f'"""Doc."""\n\nN = f"{{max(\n    1,\n    2,\n)}}"\n{LONG_ITEMS}'},
    )

    _, output = lint(tmp_path, monkeypatch, capfd)

    field = 'N = f"{\n    max(\n        1,\n        2,\n    )\n}"\n'
    assert (tmp_path / "src/mod.py").read_text() == f'"""Doc."""\n\n{field}{LONG_ITEMS}'.replace('"\n]', '",\n]')
    assert flake8_codes(output) == ["src/mod.py:7:6: C812"]
