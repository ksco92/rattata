"""Tests for the comma step against the real add-trailing-comma, run in process so its branches are measured."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from max_lint.commas import _inserts_only_commas, main

if sys.platform != "win32":
    import resource


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (b"# coding: utf8\nx = [\n    1,\n    2\n]\n", b"# coding: utf8\nx = [\n    1,\n    2,\n]\n"),
        (b"\xff\n", b"\xff\n"),
        (b"x = [\r    1,\r    2\r]\r", b"x = [\r    1,\r    2\r]\r"),
        (b"# coding: latin-1\nx = [\n    1,\n    2\n]\n", b"# coding: latin-1\nx = [\n    1,\n    2\n]\n"),
        (b"with (open(name) as handle,):\n    pass\n", b"with (open(name) as handle,):\n    pass\n"),
        (b"x = [  # fmt:skip\n    1\n]\n", b"x = [  # fmt:skip\n    1\n]\n"),
    ],
    ids=["utf8-alias", "not-utf8", "bare-cr", "declared-latin-1", "comma-removed", "black-directive"],
)
def test_comma_step_writes_only_rewrites_that_insert_commas(tmp_path: Path, source: bytes, expected: bytes) -> None:
    """
    Each outcome of the step on one file.

    :param tmp_path: Directory holding the file the step runs on.
    :param source: Bytes of the file before the step.
    :param expected: Bytes of the file after the step.
    """
    target = tmp_path / "mod.py"
    target.write_bytes(source)

    main([str(target)])

    assert target.read_bytes() == expected


@pytest.mark.parametrize(
    ("raw", "fixed", "accepted"),
    [
        (b"x", b"x;", False),
        (b"ab", b"a,", False),
        (b"a", b"a", False),
        (b"ab", b"a,,", False),
        (b"a\nb", b"a b,", True),
        (b"a,b", b"a,,b", True),
    ],
)
def test_inserts_only_commas(raw: bytes, fixed: bytes, accepted: bool) -> None:
    """
    A rewrite is accepted only when it is the file with commas inserted, whitespace aside.

    :param raw: Bytes of the file.
    :param fixed: Bytes of the rewrite.
    :param accepted: Whether the rewrite only inserts commas.
    """
    assert _inserts_only_commas(raw, fixed) is accepted


@pytest.mark.parametrize("warnings", [None, "error"])
def test_comma_step_prints_nothing_for_a_file_that_warns(tmp_path: Path, warnings: str | None) -> None:
    """
    A file with an invalid escape sequence gains its comma and the step writes nothing to stderr.

    :param tmp_path: Directory holding the file the step runs on.
    :param warnings: Value of ``PYTHONWARNINGS`` for the step, or none.
    """
    target = tmp_path / "mod.py"
    target.write_bytes(b'X = "\\d"\nY = [\n    1,\n    2\n]\n')
    environment = {key: value for key, value in os.environ.items() if key != "PYTHONWARNINGS"}

    result = subprocess.run(
        [sys.executable, "-m", "max_lint.commas", str(target)],
        capture_output=True,
        text=True,
        check=False,
        env=environment | ({"PYTHONWARNINGS": warnings} if warnings else {}),
    )

    assert (result.returncode, result.stderr) == (0, "")
    assert target.read_bytes() == b'X = "\\d"\nY = [\n    1,\n    2,\n]\n'


@pytest.mark.skipif(sys.platform == "win32", reason="file-size limits need the POSIX resource module")
def test_comma_step_stops_with_the_error_when_a_write_fails(tmp_path: Path) -> None:
    """
    A write cut short by a file-size limit ends the step with a non-zero exit and the error on stderr.

    :param tmp_path: Directory holding the file the step runs on.
    """
    target = tmp_path / "mod.py"
    target.write_bytes(b"x = [\n    1,\n    2\n]\n")

    result = subprocess.run(
        [sys.executable, "-m", "max_lint.commas", str(target)],
        capture_output=True,
        text=True,
        check=False,
        preexec_fn=lambda: resource.setrlimit(resource.RLIMIT_FSIZE, (8, 8)),
    )

    assert result.returncode != 0
    assert "OSError: [Errno 27] File too large" in result.stderr
