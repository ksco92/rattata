"""Tests for the bundled ``MXL`` flake8 rules."""

import argparse
import ast
import io
import json
import os
import subprocess
import sys
import time
import tokenize
from importlib.metadata import version as package_version
from pathlib import Path
from unittest import mock

import pytest

from max_lint.rules import MaxLintPlugin
from tests.helpers import PLAIN_PYPROJECT, flake8_codes, lint, write_files

TESTS_PYPROJECT = '[tool.max-lint]\npaths = ["src"]\ntest-paths = ["tests"]\n'
CLASSIFIED = '"""Fixture module."""\n\nimport unittest\n\n# TODO: later\nVALUE = unittest\n'

SOURCE_MXL_CASES = [
    pytest.param(
        {
            "pyproject.toml": PLAIN_PYPROJECT,
            "src/mod.py": (
                '"""Fixture module."""\n\n'
                "from typing import Dict, Optional, Self\n\n"
                "VALUE: Optional[Dict[str, int]] = None\n"
                "SELF_REF = Self\n"
            ),
        },
        [(3, 0, "MXL001"), (3, 0, "MXL001")],
        ["src/mod.py:3:1: MXL001", "src/mod.py:3:1: MXL001"],
        id="mxl001",
    ),
    pytest.param(
        {
            "pyproject.toml": PLAIN_PYPROJECT,
            "src/mod.py": '"""\nSummary.\n\n' + "".join(f"Line {i}.\n" for i in range(1, 9)) + '"""\n\nVALUE = 1\n',
        },
        [(1, 0, "MXL002")],
        ["src/mod.py:1:1: MXL002"],
        id="mxl002",
    ),
    pytest.param(
        {
            "pyproject.toml": PLAIN_PYPROJECT,
            "src/mod.py": (
                '"""Fixture module."""\n\n\n'
                "def _run(value: str) -> int:\n"
                '    """\n    Parse value.\n\n    :param value: input text.\n    :return: parsed int or zero.\n    """\n'
                "    try:\n"
                "        return int(value)\n"
                "    except (ValueError, TypeError):\n"
                "        return 0\n\n\n"
                "def _swallow() -> None:\n"
                '    """Swallow errors silently."""\n'
                "    try:\n"
                '        int("x")\n'
                "    except Exception:\n"
                "        pass\n"
                "    try:\n"
                '        int("y")\n'
                "    except BaseException:\n"
                "        ...\n"
                "    try:\n"
                '        int("z")\n'
                "    except Exception:\n"
                "        pass\n"
                '        int("1")\n'
            ),
        },
        [(13, 4, "MXL003"), (21, 4, "MXL004"), (25, 4, "MXL004")],
        ["src/mod.py:13:5: MXL003", "src/mod.py:21:5: MXL004", "src/mod.py:25:5: MXL004"],
        id="mxl003-mxl004",
    ),
    pytest.param(
        {
            "pyproject.toml": PLAIN_PYPROJECT,
            "src/mod.py": (
                '"""Fixture module."""\n\n'
                + "".join(f"# Comment line {i}\n" for i in range(12))
                + "".join(f"V{i} = {i}\n" for i in range(10))
            ),
            "src/clean.py": (
                '"""Fixture module."""\n\n\n'
                "def compute(\n"
                "    a: int,\n"
                "    b: int,\n"
                "    c: int,\n"
                "    d: int,\n"
                "    e: int,\n"
                ") -> int:\n"
                '    """\n'
                "    Compute sum.\n\n"
                "    >>> compute(1, 2, 3, 4, 5)\n"
                "    15\n\n"
                "    :param a: first\n"
                "        wrapped detail.\n"
                "    :param b: second.\n"
                "    :param c: third.\n"
                "    :param d: fourth.\n"
                "    :param e: fifth.\n"
                "    :return: total\n"
                "        wrapped return.\n"
                '    """\n'
                "    total = a + b + c + d + e  # inline comment\n\n"
                "    return total\n"
            ),
        },
        [(1, 0, "MXL005")],
        ["src/mod.py:1:1: MXL005"],
        id="mxl005",
    ),
    pytest.param(
        {
            "pyproject.toml": PLAIN_PYPROJECT,
            "src/mod.py": (
                '"""Fixture module."""\n\n\n'
                "def _stub() -> None:\n"
                '    """\n    Raise bare call.\n\n    :raises NotImplementedError: always.\n    """\n'
                "    raise NotImplementedError()\n\n\n"
                "def _stub_name() -> None:\n"
                '    """\n    Raise bare name.\n\n    :raises NotImplementedError: always.\n    """\n'
                "    raise NotImplementedError\n\n\n"
                "def _explained() -> None:\n"
                '    """\n    Raise explained error.\n\n    :raises NotImplementedError: always.\n    """\n'
                '    raise NotImplementedError("override in subclass")\n\n\n'
                "def _flat_elif(x: int) -> int:\n"
                '    """\n    Check flat elif chain.\n\n    :param x: selector.\n    :return: branch code.\n    """\n'
                "    if x == 1:\n"
                "        return 1\n"
                "    elif x == 2:\n"
                "        return 2\n"
                "    elif x == 3:\n"
                "        return 3\n"
                "    elif x == 4:\n"
                "        return 4\n"
                "    elif x == 5:\n"
                "        return 5\n"
                "    return 0\n\n\n"
                "def _deep(flag: bool) -> int:\n"
                '    """\n    Exercise nesting past limit.\n\n    :param flag: branch toggle.\n    :return: nested result.\n    """\n\n'
                "    def _nested() -> int:\n"
                '        """\n        Return two.\n\n        :return: constant two.\n        """\n'
                "        return 2\n\n"
                "    if flag:\n"
                "        for _ in range(1):\n"
                "            while flag:\n"
                "                try:\n"
                "                    if flag:\n"
                "                        return _nested()\n"
                "                except ValueError:\n"
                "                    break\n"
                "                break\n\n"
                "    return 0\n"
            ),
        },
        [(10, 4, "MXL006"), (19, 4, "MXL006"), (71, 20, "MXL007")],
        ["src/mod.py:10:5: MXL006", "src/mod.py:19:5: MXL006", "src/mod.py:71:21: MXL007"],
        id="mxl006-mxl007",
    ),
    pytest.param(
        {
            "pyproject.toml": PLAIN_PYPROJECT,
            "src/mod.py": (
                '"""Fixture module."""\n\n'
                "# TODO(alice): remove later\n"
                "# fixme: clean up\n"
                "# XXX check me\n"
                "# HACK: temporary\n"
                "# Panics: never\n"
                "VALUE = 1\n\n\n"
                "def _helper() -> int:\n"
                '    """\n    Return one.\n\n    :return: one.\n    :raises: nothing\n    """\n'
                "    return VALUE\n"
            ),
        },
        [
            (3, 0, "MXL009"),
            (4, 0, "MXL009"),
            (5, 0, "MXL009"),
            (6, 0, "MXL009"),
            (7, 0, "MXL008"),
            (12, 4, "MXL008"),
        ],
        [
            "src/mod.py:3:1: MXL009",
            "src/mod.py:4:1: MXL009",
            "src/mod.py:5:1: MXL009",
            "src/mod.py:6:1: MXL009",
            "src/mod.py:7:1: MXL008",
            "src/mod.py:11:1: DOC502",
            "src/mod.py:12:5: MXL008",
        ],
        id="mxl008-mxl009",
    ),
]


def _run_plugin(source: str, filename: str = "src/mod.py", test_paths: tuple[str, ...] = ()) -> list[tuple[int, int, str]]:
    """
    Run ``MaxLintPlugin`` in-process on ``source`` and return ``(line, col, code)`` tuples.

    :param source: Python source text to check.
    :param filename: virtual path of the file, relative to the working directory.
    :param test_paths: test paths relative to the working directory, given to the plugin as max-lint gives them.
    :return: ``(line, col, code)`` tuples for each reported violation.
    """
    test_paths_json = json.dumps([os.path.abspath(path) for path in test_paths])
    MaxLintPlugin.parse_options(argparse.Namespace(max_lint_test_paths=test_paths_json))
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
    plugin = MaxLintPlugin(tree=tree, filename=filename, lines=lines, file_tokens=tokens)

    return [(line, col, message.split()[0]) for line, col, message, _ in plugin.run()]


def _run_flake8(directory: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    r"""
    Run flake8 directly, without max-lint, in ``directory``.

    :param directory: working directory of the run.
    :param \*arguments: arguments given to flake8.
    :return: the finished process with its text output.
    """
    return subprocess.run(
        [sys.executable, "-m", "flake8", *arguments],
        cwd=directory,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize(
    ("files", "expected_in_proc", "expected_flake8"),
    SOURCE_MXL_CASES,
)
def test_source_mxl_rules_end_to_end(
    files: dict[str, str],
    expected_in_proc: list[tuple[int, int, str]],
    expected_flake8: list[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """
    Source-level ``MXL001``–``MXL009`` rules match both in-process and under ``max-lint lint --check``.

    :param files: project fixture files to write under ``tmp_path``.
    :param expected_in_proc: expected in-process violations for ``src/mod.py``.
    :param expected_flake8: expected flake8 codes from ``max-lint lint --check``.
    :param tmp_path: project directory for fixture files.
    :param monkeypatch: changes cwd to ``tmp_path``.
    :param capfd: captures tool output.
    """
    write_files(tmp_path, files)

    assert _run_plugin(files["src/mod.py"]) == expected_in_proc

    if "src/clean.py" in files:
        assert _run_plugin(files["src/clean.py"]) == []

    exit_code, output = lint(tmp_path, monkeypatch, capfd, "--check")

    assert exit_code == 1
    assert flake8_codes(output) == expected_flake8


def test_comment_ratio_boundaries_and_exclusions() -> None:
    """Pin 19-vs-20 line floor, exact 40% vs >40% ratio, and doctest/delimiter/Sphinx/inline exclusions."""
    short_19 = "".join(f"# c{i}\n" for i in range(15)) + "".join(f"X{i} = {i}\n" for i in range(4))

    assert _run_plugin(short_19) == []

    exact_40 = "".join(f"# c{i}\n" for i in range(8)) + "".join(f"X{i} = {i}\n" for i in range(12))

    assert _run_plugin(exact_40) == []

    over_40 = "".join(f"# c{i}\n" for i in range(9)) + "".join(f"X{i} = {i}\n" for i in range(11))

    assert _run_plugin(over_40) == [(1, 0, "MXL005")]

    exact_40_with_exclusions = (
        '"""\n'
        "Summary.\n\n"
        ">>> 1 + 1\n"
        "2\n"
        "3\n\n"
        ":param a: wrapped\n"
        "    continuation.\n"
        '"""\n' + "".join(f"# c{i}\n" for i in range(9)) + "".join(f"V{i} = {i}  # inline\n" for i in range(8))
    )

    assert _run_plugin(exact_40_with_exclusions) == []


def test_relative_imports_else_nesting_and_absence_variants() -> None:
    """Check relative imports, indented ``else: if`` nesting, non-test ``test_*`` imports and absence spellings."""
    allowed_imports = (
        "from .typing import Dict\n"
        "from .unittest import HELPER\n"
        "from myapp.network import test_connection\n"
        "from tests import helpers\n"
        "from tests.helpers import test_factory\n"
    )

    assert _run_plugin(allowed_imports, filename="tests/test_rel.py", test_paths=("tests",)) == []

    indented_else_if = (
        "def f(x: int) -> int:\n"
        "    if x == 1:\n"
        "        return 1\n"
        "    else:\n"
        "        if x == 2:\n"
        "            return 2\n"
        "        else:\n"
        "            if x == 3:\n"
        "                return 3\n"
        "            else:\n"
        "                if x == 4:\n"
        "                    return 4\n"
        "                else:\n"
        "                    if x == 5:\n"
        "                        return 5\n"
        "    return 0\n"
    )

    assert _run_plugin(indented_else_if) == [(14, 20, "MXL007")]

    absence_src = (
        'def f() -> None:\n    """\n    Do nothing.\n\n    :raises ValueError: none.\n    """\n\n'
        'def g() -> None:\n    """\n    Do nothing.\n\n    :raises: never\n    """\n'
    )

    assert _run_plugin(absence_src) == [(2, 4, "MXL008"), (9, 4, "MXL008")]
    assert _run_plugin("# panics: NEVER\n") == [(1, 0, "MXL008")]


def test_test_file_rules_report_mxl010_mxl011_mxl012(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """
    Test files disallow unittest (except mock), test classes, ``@patch`` decorators and sibling test imports.

    :param tmp_path: project directory for fixture files.
    :param monkeypatch: changes cwd to ``tmp_path``.
    :param capfd: captures tool output.
    """
    test_source = (
        '"""Fixture tests."""\n\n'
        "import unittest\n"
        "import unittest.case\n"
        "import unittest.mock\n"
        "from unittest import TestCase, mock\n"
        "from unittest.case import TestCase as Case\n"
        "from unittest.mock import patch\n\n"
        "import pytest\n"
        "import test_other\n\n"
        "from tests import test_other as sibling\n"
        "from tests.test_other import helper\n\n\n"
        "class TestSuite(TestCase):\n"
        '    """Grouped tests."""\n\n\n'
        '@patch("os.getcwd")\n'
        '@patch.object(unittest, "TestCase")\n'
        '@patch.dict("os.environ", {})\n'
        '@mock.patch("os.getpid")\n'
        '@unittest.mock.patch.multiple("os", getcwd=None)\n'
        "@pytest.mark.slow\n"
        "@pytest.fixture\n"
        "def test_decorated(a: object, b: object, c: object, d: object, e: object) -> None:\n"
        '    """\n'
        "    Use decorated patches.\n\n"
        "    :param a: first.\n"
        "    :param b: second.\n"
        "    :param c: third.\n"
        "    :param d: fourth.\n"
        "    :param e: fifth.\n"
        '    """\n'
        "    assert (a, b, c, d, e, Case, unittest.mock, test_other, sibling, helper)\n"
    )

    other_test = (
        '"""Other test."""\n\n\n'
        "def helper() -> int:\n"
        '    """\n    Return one.\n\n    :return: one.\n    """\n'
        "    return 1\n"
    )

    write_files(
        tmp_path,
        {
            "pyproject.toml": TESTS_PYPROJECT,
            "src/ok.py": '"""Ok."""\n\nVALUE = 1\n',
            "tests/test_other.py": other_test,
            "tests/test_bad.py": test_source,
        },
    )

    in_proc = _run_plugin(test_source, filename="tests/test_bad.py", test_paths=("tests",))

    assert (3, 0, "MXL010") in in_proc
    assert (4, 0, "MXL010") in in_proc
    assert (5, 0, "MXL010") not in in_proc
    assert (6, 0, "MXL010") in in_proc
    assert (7, 0, "MXL010") in in_proc
    assert (8, 0, "MXL010") not in in_proc
    assert (11, 0, "MXL012") in in_proc
    assert (13, 0, "MXL012") in in_proc
    assert (14, 0, "MXL012") in in_proc
    assert (17, 0, "MXL010") in in_proc
    assert (21, 1, "MXL011") in in_proc
    assert (22, 1, "MXL011") in in_proc
    assert (23, 1, "MXL011") in in_proc
    assert (24, 1, "MXL011") in in_proc
    assert (25, 1, "MXL011") in in_proc
    assert (26, 1, "MXL011") not in in_proc
    assert (27, 1, "MXL011") not in in_proc

    exit_code, output = lint(tmp_path, monkeypatch, capfd, "--check")
    codes = flake8_codes(output)

    assert exit_code == 1
    assert any(code.endswith("MXL010") for code in codes)
    assert any(code.endswith("MXL011") for code in codes)
    assert any(code.endswith("MXL012") for code in codes)


def test_plugin_edge_cases_and_security_bounds() -> None:
    """Cover test-path detection, non-mock ``.patch`` decorators, version metadata, ReDoS and deep expressions."""
    assert MaxLintPlugin.version == package_version("max-lint")
    assert _run_plugin("") == []
    assert _run_plugin("class Empty:\n    pass\n") == []
    assert _run_plugin("try:\n    pass\nexcept:\n    pass\n") == [(3, 0, "MXL004")]
    assert _run_plugin("import unittest\n", filename="checks/helpers.py", test_paths=("checks",)) == [(1, 0, "MXL010")]
    assert _run_plugin("import unittest\n", filename="checks_extra/helpers.py", test_paths=("checks",)) == []
    assert _run_plugin("from . import test_other\n", filename="tests/test_a.py", test_paths=("tests",)) == [(1, 0, "MXL012")]
    assert _run_plugin("# TODO: test note\n", filename="tests/test_a.py", test_paths=("tests",)) == []

    non_patch_decorators = '@app.patch("/items")\n@decs[0]\ndef test_ok() -> None:\n    pass\n'

    assert _run_plugin(non_patch_decorators, filename="tests/test_a.py", test_paths=("tests",)) == []

    deep_expr = "def f() -> int:\n    return " + " + ".join(["1"] * 1200) + "\n"

    assert _run_plugin(deep_expr) == []

    many_newlines_doc = 'def f() -> None:\n    """' + ("\\n" * 30000) + '"""\n'
    start = time.monotonic()

    assert _run_plugin(many_newlines_doc) == []
    assert time.monotonic() - start < 1.0


@pytest.mark.parametrize(
    ("source_path", "test_path", "tests", "sources"),
    [
        pytest.param(
            "src",
            "checks",
            ["checks/helpers.py"],
            ["src/pkg/test_utils.py", "src/pkg/tests/factories.py"],
            id="test-names-under-paths",
        ),
        pytest.param("src", "./checks", ["checks/helpers.py"], ["src/mod.py"], id="leading-dot-slash"),
        pytest.param("src", "checks/", ["checks/helpers.py"], ["src/mod.py"], id="trailing-slash"),
        pytest.param("src", "src/one.py", ["src/one.py"], ["src/two.py"], id="single-file"),
        pytest.param("src", "../shared/checks", ["../shared/checks/helpers.py"], ["src/mod.py"], id="outside-project"),
        pytest.param("src", "my checks", ["my checks/helpers.py"], ["src/mod.py"], id="space"),
        pytest.param("src", "a,b", ["a,b/helpers.py"], ["src/mod.py"], id="comma"),
        pytest.param("app", "app/checks", ["app/checks/helpers.py"], ["app/main.py"], id="nested-in-source-path"),
    ],
)
def test_test_paths_decide_which_files_are_tests(
    source_path: str,
    test_path: str,
    tests: list[str],
    sources: list[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """
    Under ``max-lint lint --check`` the files under ``test-paths`` get ``MXL010`` and the others ``MXL009``, whatever their names.

    :param source_path: the project's only entry in ``paths``.
    :param test_path: the project's only entry in ``test-paths``.
    :param tests: files under ``test-paths``, relative to the project.
    :param sources: files outside ``test-paths``, relative to the project.
    :param tmp_path: holds the project directory and a sibling directory outside it.
    :param monkeypatch: changes cwd to the project.
    :param capfd: captures tool output.
    """
    project = tmp_path / "project"
    pyproject = f"[tool.max-lint]\npaths = [{json.dumps(source_path)}]\ntest-paths = [{json.dumps(test_path)}]\n"
    write_files(project, {"pyproject.toml": pyproject, **dict.fromkeys([*tests, *sources], CLASSIFIED)})

    exit_code, output = lint(project, monkeypatch, capfd, "--check")
    expected = [f"{path}:3:1: MXL010" for path in tests] + [f"{path}:5:1: MXL009" for path in sources]

    assert exit_code == 1
    assert flake8_codes(output) == sorted(expected)


def test_flake8_without_max_lint_treats_no_file_as_a_test(tmp_path: Path) -> None:
    """
    flake8 run directly reports ``MXL009`` and no ``MXL010`` for a file named and placed like a test.

    :param tmp_path: project directory for fixture files.
    """
    write_files(tmp_path, {"tests/test_mod.py": CLASSIFIED})

    result = _run_flake8(tmp_path, "--select=MXL", "tests")

    assert result.returncode == 1
    assert flake8_codes(result.stdout) == ["tests/test_mod.py:5:1: MXL009"]

    option_manager = mock.Mock()
    MaxLintPlugin.add_options(option_manager)
    MaxLintPlugin.parse_options(argparse.Namespace(max_lint_test_paths=option_manager.add_option.call_args.kwargs["default"]))

    assert MaxLintPlugin.test_paths == ()


@pytest.mark.parametrize(
    "value",
    ["not json", '"/"', "[1]", "1" * 4301, "[" * 100000 + "]" * 100000],
    ids=["not-json", "not-a-list", "non-string-entry", "over-int-digit-limit", "over-recursion-limit"],
)
def test_flake8_rejects_a_test_paths_value_that_is_not_a_list_of_strings(value: str, tmp_path: Path) -> None:
    """
    A ``max-lint-test-paths`` value other than a JSON list of strings ends flake8 with one line and no findings.

    :param value: the option's value in the project's flake8 config.
    :param tmp_path: project directory for fixture files.
    """
    write_files(tmp_path, {".flake8": f"[flake8]\nmax-lint-test-paths = {value}\n", "a.py": CLASSIFIED})

    result = _run_flake8(tmp_path, "--select=MXL", ".")
    output = result.stdout + result.stderr

    assert result.returncode != 0
    assert output == "flake8: the max-lint-test-paths option must be a JSON list of strings.\n"

    with pytest.raises(SystemExit, match="max-lint-test-paths"):
        MaxLintPlugin.parse_options(argparse.Namespace(max_lint_test_paths=value))
