"""Tests for the comma step against the real add-trailing-comma."""

from pathlib import Path

import pytest

from max_lint.commas import main


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (b"x = [\n    1,\n    2\n]\n", b"x = [\n    1,\n    2,\n]\n"),
        (b'a = 5\nb = 3\nx = f"""\n{a:{\n  b\n}}\n"""\n', b'a = 5\nb = 3\nx = f"""\n{a:{\n  b\n}}\n"""\n'),
        (b"\xef\xbb\xbfprint(1)\n", b"\xef\xbb\xbfprint(1)\n"),
        (b'x = "\xff"\n', b'x = "\xff"\n'),
    ],
    ids=["comma-added", "tree-changed", "tool-raises", "not-utf8"],
)
def test_comma_step_writes_only_rewrites_that_keep_the_tree(tmp_path: Path, source: bytes, expected: bytes) -> None:
    """
    Each outcome of the step on one file, run in process.

    :param tmp_path: Directory holding the file the step runs on.
    :param source: Bytes of the file before the step.
    :param expected: Bytes of the file after the step.
    """
    target = tmp_path / "mod.py"
    target.write_bytes(source)

    assert main([str(target)]) == 0
    assert target.read_bytes() == expected
