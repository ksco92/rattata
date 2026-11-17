"""Tests for the comma step against the real add-trailing-comma, run in process so its branches are measured."""

import subprocess
import sys
from pathlib import Path

import pytest

from max_lint.commas import main

if sys.platform != "win32":
    import resource


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (b"x = [\n    1,\n    2\n]\n", b"x = [\n    1,\n    2,\n]\n"),
        (b"\xff\n", b"\xff\n"),
        (
            b"# coding: utf-7\nx = print(0,  # +AAo-)+AAo-y = (\n    1\n)\n",
            b"# coding: utf-7\nx = print(0,  # +AAo-)+AAo-y = (\n    1\n)\n",
        ),
    ],
    ids=["comma-added", "not-utf8", "tree-changed"],
)
def test_comma_step_writes_only_rewrites_that_keep_the_tree(tmp_path: Path, source: bytes, expected: bytes) -> None:
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
