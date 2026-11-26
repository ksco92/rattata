"""Tests for the bundled ``MXL`` flake8 rules."""

import ast
import io
import re
import tokenize
from pathlib import Path

import pytest

from max_lint.cli import main
from max_lint.rules import MaxLintPlugin

PLAIN_PYPROJECT = '[tool.max-lint]\npaths = ["src"]\n'


def _write_files(root: Path, files: dict[str, str]) -> None:
    """
    Write each relative path in ``files`` under ``root``.

    :param root: Directory to write fixture files into.
    :param files: Mapping of relative paths to file contents.
    """
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)


def _lint(root: Path, monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]) -> tuple[int, str]:
    """
    Run ``max-lint lint --check`` in ``root`` and return exit code and output.

    :param root: Project directory to lint.
    :param monkeypatch: Changes cwd to ``root``.
    :param capfd: Captures stdout and stderr.
    :return: ``(exit_code, combined_output)`` tuple.
    """
    monkeypatch.chdir(root)
    exit_code = main(["lint", "--check"])
    captured = capfd.readouterr()

    return exit_code, captured.out + captured.err


def _codes(output: str) -> list[str]:
    """
    Return every flake8 ``path:row:col: CODE`` hit in ``output``.

    :param output: Combined stdout and stderr from flake8.
    :return: Matching ``path:row:col: CODE`` strings in order.
    """
    return re.findall(r"^(\S+\.py:\d+:\d+: [A-Z]+[0-9]+)", output, flags=re.MULTILINE)


def _run_plugin(source: str, filename: str = "src/mod.py") -> list[tuple[int, int, str]]:
    """
    Run ``MaxLintPlugin`` in-process on ``source`` and return ``(line, col, code)`` tuples.

    :param source: Python source text to check.
    :param filename: Virtual path used to classify test vs production files.
    :return: ``(line, col, code)`` tuples for each reported violation.
    """
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
    plugin = MaxLintPlugin(tree=tree, filename=filename, lines=lines, file_tokens=tokens)

    return [(line, col, message.split()[0]) for line, col, message, _ in plugin.run()]


def test_deprecated_typing_imports_report_mxl001(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """
    Legacy typing generics and ``Optional`` report ``MXL001``; modern typing imports pass.

    :param tmp_path: Project directory for fixture files.
    :param monkeypatch: Changes cwd to ``tmp_path``.
    :param capfd: Captures tool output.
    """
    source = (
        '"""Fixture module."""\n\n'
        "from typing import Dict, Optional, Self\n\n"
        "VALUE: Optional[Dict[str, int]] = None\n"
        "SELF_REF = Self\n"
    )
    _write_files(tmp_path, {"pyproject.toml": PLAIN_PYPROJECT, "src/mod.py": source})

    assert _run_plugin(source) == [(3, 0, "MXL001"), (3, 0, "MXL001")]

    exit_code, output = _lint(tmp_path, monkeypatch, capfd)

    assert exit_code == 1
    assert _codes(output) == ["src/mod.py:3:1: MXL001", "src/mod.py:3:1: MXL001"]


def test_module_docstring_over_ten_lines_reports_mxl002(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """
    A module docstring over 10 physical lines reports ``MXL002``; 10 lines passes.

    :param tmp_path: Project directory for fixture files.
    :param monkeypatch: Changes cwd to ``tmp_path``.
    :param capfd: Captures tool output.
    """
    ten_lines = '"""\nSummary.\n\n' + "Line.\n" * 6 + '"""\n\nVALUE = 1\n'
    eleven_lines = '"""\nSummary.\n\n' + "Line.\n" * 7 + '"""\n\nVALUE = 1\n'
    _write_files(
        tmp_path,
        {"pyproject.toml": PLAIN_PYPROJECT, "src/ok.py": ten_lines, "src/too_long.py": eleven_lines},
    )

    assert _run_plugin(ten_lines) == []
    assert _run_plugin(eleven_lines) == [(1, 0, "MXL002")]

    exit_code, output = _lint(tmp_path, monkeypatch, capfd)

    assert exit_code == 1
    assert _codes(output) == ["src/too_long.py:1:1: MXL002"]


def test_multi_exception_and_silent_swallow_report_mxl003_and_mxl004(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """
    Multi-exception clauses report ``MXL003`` and silent broad swallows report ``MXL004``.

    :param tmp_path: Project directory for fixture files.
    :param monkeypatch: Changes cwd to ``tmp_path``.
    :param capfd: Captures tool output.
    """
    source = (
        '"""Fixture module."""\n\n\n'
        "def _run() -> None:\n"
        "    try:\n"
        '        int("1")\n'
        "    except (ValueError, TypeError):\n"
        "        return\n\n"
        "    try:\n"
        '        int("1")\n'
        "    except Exception:\n"
        "        pass\n\n"
        "    try:\n"
        '        int("1")\n'
        "    except BaseException:\n"
        "        ...\n\n"
        "    try:\n"
        '        int("1")\n'
        "    except:\n"
        "        pass\n\n"
        "    try:\n"
        '        int("1")\n'
        "    except Exception:\n"
        "        return\n"
    )
    _write_files(tmp_path, {"pyproject.toml": PLAIN_PYPROJECT, "src/mod.py": source})

    assert _run_plugin(source) == [
        (7, 4, "MXL003"),
        (12, 4, "MXL004"),
        (17, 4, "MXL004"),
        (22, 4, "MXL004"),
    ]

    exit_code, output = _lint(tmp_path, monkeypatch, capfd)
    codes = _codes(output)

    assert exit_code == 1
    assert "src/mod.py:7:5: MXL003" in codes
    assert "src/mod.py:12:5: MXL004" in codes
    assert "src/mod.py:17:5: MXL004" in codes
    assert "src/mod.py:22:5: MXL004" in codes
    assert "src/mod.py:27:5: MXL004" not in codes


def test_comment_ratio_over_forty_percent_reports_mxl005(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """
    A file with >=20 non-blank lines and >40% prose reports ``MXL005``; Sphinx fields and doctests are excluded.

    :param tmp_path: Project directory for fixture files.
    :param monkeypatch: Changes cwd to ``tmp_path``.
    :param capfd: Captures tool output.
    """
    comments = "".join(f"# Prose line {index}.\n" for index in range(12))
    code = "".join(f"VALUE_{index} = {index}\n" for index in range(10))
    noisy = f'"""Fixture module."""\n\n{comments}{code}'
    clean_doc = (
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
        "    :param a: First.\n"
        "    :param b: Second.\n"
        "    :param c: Third.\n"
        "    :param d: Fourth.\n"
        "    :param e: Fifth.\n"
        "    :return: Total.\n"
        '    """\n'
        "    total = a + b + c + d + e  # inline comment\n\n"
        "    return total\n"
    )
    _write_files(tmp_path, {"pyproject.toml": PLAIN_PYPROJECT, "src/noisy.py": noisy, "src/clean.py": clean_doc})

    assert _run_plugin(noisy) == [(1, 0, "MXL005")]
    assert _run_plugin(clean_doc) == []

    exit_code, output = _lint(tmp_path, monkeypatch, capfd)

    assert exit_code == 1
    assert _codes(output) == ["src/noisy.py:1:1: MXL005"]


def test_not_implemented_and_nesting_report_mxl006_and_mxl007(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """
    Bare ``NotImplementedError()`` reports ``MXL006`` and nesting past 4 reports ``MXL007``.

    :param tmp_path: Project directory for fixture files.
    :param monkeypatch: Changes cwd to ``tmp_path``.
    :param capfd: Captures tool output.
    """
    source = (
        '"""Fixture module."""\n\n\n'
        "def _stub() -> None:\n"
        "    raise NotImplementedError()\n\n\n"
        "def _explained() -> None:\n"
        '    raise NotImplementedError("override in subclass")\n\n\n'
        "def _deep(flag: bool) -> int:\n"
        "    def _nested() -> int:\n"
        "        return 2\n\n"
        "    if flag:\n"
        "        if flag:\n"
        "            if flag:\n"
        "                if flag:\n"
        "                    if flag:\n"
        "                        return _nested()\n\n"
        "    return 0\n"
    )
    _write_files(tmp_path, {"pyproject.toml": PLAIN_PYPROJECT, "src/mod.py": source})

    assert _run_plugin(source) == [(5, 4, "MXL006"), (20, 20, "MXL007")]

    exit_code, output = _lint(tmp_path, monkeypatch, capfd)

    assert exit_code == 1
    assert _codes(output) == ["src/mod.py:5:5: MXL006", "src/mod.py:20:21: MXL007"]


def test_documented_absence_and_crumb_todo_report_mxl008_and_mxl009(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """
    Documented absences report ``MXL008`` and non-test TODO crumbs report ``MXL009``.

    :param tmp_path: Project directory for fixture files.
    :param monkeypatch: Changes cwd to ``tmp_path``.
    :param capfd: Captures tool output.
    """
    source = (
        '"""Fixture module."""\n\n'
        "# TODO: remove later\n"
        "# Panics: never\n"
        "VALUE = 1\n\n\n"
        "def _helper() -> int:\n"
        '    """\n    Return one.\n\n    :return: One.\n    :raises: nothing\n    """\n'
        "    return VALUE\n"
    )
    _write_files(tmp_path, {"pyproject.toml": PLAIN_PYPROJECT, "src/mod.py": source})

    assert _run_plugin(source) == [(3, 0, "MXL009"), (4, 0, "MXL008"), (9, 4, "MXL008")]
    assert _run_plugin(source, filename="tests/test_mod.py") == [(4, 0, "MXL008"), (9, 4, "MXL008")]

    exit_code, output = _lint(tmp_path, monkeypatch, capfd)

    assert exit_code == 1
    assert _codes(output) == [
        "src/mod.py:3:1: MXL009",
        "src/mod.py:4:1: MXL008",
        "src/mod.py:8:1: DOC502",
        "src/mod.py:9:5: MXL008",
    ]


def test_test_file_rules_report_mxl010_mxl011_mxl012(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """
    Test files disallow unittest, test classes, ``@patch`` decorators and sibling test imports.

    :param tmp_path: Project directory for fixture files.
    :param monkeypatch: Changes cwd to ``tmp_path``.
    :param capfd: Captures tool output.
    """
    test_source = (
        '"""Fixture tests."""\n\n'
        "import unittest\n"
        "from unittest import TestCase, mock\n"
        "from unittest.mock import patch\n\n"
        "import pytest\n"
        "import test_other\n\n"
        "from tests.test_other import helper\n\n\n"
        "class TestSuite(TestCase):\n"
        '    """Grouped tests."""\n\n\n'
        '@patch("os.getcwd")\n'
        '@mock.patch("os.getpid")\n'
        '@mock.patch.object(unittest, "TestCase")\n'
        "@pytest.mark.slow\n"
        "@pytest.fixture\n"
        "def test_decorated(mock_cwd: object, mock_pid: object, mock_tc: object) -> None:\n"
        '    """\n'
        "    Use decorated patches.\n\n"
        "    :param mock_cwd: Mocked cwd.\n"
        "    :param mock_pid: Mocked pid.\n"
        "    :param mock_tc: Mocked class.\n"
        '    """\n'
        "    assert (mock_cwd, mock_pid, mock_tc, test_other, helper)\n"
    )
    other_test = (
        '"""Other test."""\n\n\ndef helper() -> int:\n    """\n    Return one.\n\n    :return: One.\n    """\n    return 1\n'
    )
    _write_files(
        tmp_path,
        {
            "pyproject.toml": '[tool.max-lint]\npaths = ["src"]\ntest-paths = ["tests"]\n',
            "src/ok.py": '"""Ok."""\n\nVALUE = 1\n',
            "tests/test_other.py": other_test,
            "tests/test_bad.py": test_source,
        },
    )

    in_proc = _run_plugin(test_source, filename="tests/test_bad.py")
    assert (3, 0, "MXL010") in in_proc
    assert (4, 0, "MXL010") in in_proc
    assert (8, 0, "MXL012") in in_proc
    assert (10, 0, "MXL012") in in_proc
    assert (13, 0, "MXL010") in in_proc
    assert (17, 1, "MXL011") in in_proc
    assert (18, 1, "MXL011") in in_proc
    assert (19, 1, "MXL011") in in_proc
    assert (20, 1, "MXL011") not in in_proc
    assert (21, 1, "MXL011") not in in_proc

    exit_code, output = _lint(tmp_path, monkeypatch, capfd)
    codes = _codes(output)

    assert exit_code == 1
    assert "tests/test_bad.py:3:1: MXL010" in codes
    assert "tests/test_bad.py:4:1: MXL010" in codes
    assert "tests/test_bad.py:8:1: MXL012" in codes
    assert "tests/test_bad.py:10:1: MXL012" in codes
    assert "tests/test_bad.py:13:1: MXL010" in codes
    assert "tests/test_bad.py:17:2: MXL011" in codes
    assert "tests/test_bad.py:18:2: MXL011" in codes
    assert "tests/test_bad.py:19:2: MXL011" in codes


def test_plugin_edge_cases_empty_and_non_test_paths() -> None:
    """Empty files, non-test paths and ``tests/`` directory paths are handled cleanly."""
    assert _run_plugin("", filename="src/empty.py") == []
    assert _run_plugin("import unittest\n", filename="src/helper.py") == []
    assert _run_plugin("import unittest\n", filename="tests/support.py") == [(1, 0, "MXL010")]
    assert _run_plugin("@other\ndef test_ok() -> None:\n    pass\n", filename="conftest.py") == []
    assert _run_plugin("@(get_dec())\ndef test_ok() -> None:\n    pass\n", filename="conftest.py") == []
    assert (
        _run_plugin(
            "def _f(x: bool) -> int:\n    if x:\n        class Inner:\n            pass\n        return 1\n    return 0\n",
        )
        == []
    )
