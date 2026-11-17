"""Tests for the comma step against the real add-trailing-comma, run in process so its branches are measured."""

from pathlib import Path

import pytest

from max_lint.commas import main


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
