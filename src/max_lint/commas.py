"""Add trailing commas with add-trailing-comma, keeping only rewrites that leave the syntax tree unchanged."""

import ast
import sys
from pathlib import Path

from add_trailing_comma._main import _fix_src  # type: ignore[import-untyped]


def main(files: list[str]) -> int:
    """
    Add missing trailing commas to ``files`` in place.

    A file is left byte-identical when it is not UTF-8, the tool cannot process it, or the rewrite changes its syntax tree.

    :param files: paths to rewrite.
    :return: 0.
    """
    for name in files:
        path = Path(name)

        try:
            text = path.read_bytes().decode()
        except UnicodeDecodeError:
            continue

        try:
            fixed: str = _fix_src(text)
            same_tree = ast.dump(ast.parse(fixed)) == ast.dump(ast.parse(text))
        except Exception:
            continue

        if fixed != text and same_tree:
            path.write_bytes(fixed.encode())

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
