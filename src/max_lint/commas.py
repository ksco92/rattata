"""Add trailing commas with add-trailing-comma, keeping only rewrites that leave the syntax tree unchanged."""

import ast
import codecs
import sys
from pathlib import Path

from add_trailing_comma._main import _fix_src  # type: ignore[import-untyped]


def main(files: list[str]) -> None:
    """
    Add missing trailing commas to ``files`` in place.

    A rewrite is written only when it parses, read as Python reads the file, to the same syntax tree as the file; a file that
    cannot be read, decoded, processed or written is left byte-identical and the next file is processed.

    :param files: paths to rewrite.
    """
    for name in files:
        path = Path(name)

        try:
            raw = path.read_bytes()
            mark = codecs.BOM_UTF8 if raw.startswith(codecs.BOM_UTF8) else b""
            text = raw.removeprefix(mark).decode()
            fixed: bytes = mark + _fix_src(text).encode()

            if fixed != raw and ast.dump(ast.parse(fixed)) == ast.dump(ast.parse(raw)):
                path.write_bytes(fixed)
        except Exception:
            continue


if __name__ == "__main__":
    main(sys.argv[1:])
