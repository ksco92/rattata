"""Add trailing commas with add-trailing-comma, keeping only rewrites that leave the syntax tree unchanged."""

import ast
import codecs
import sys
from pathlib import Path

from add_trailing_comma._main import _fix_src  # type: ignore[import-untyped]


def main(files: list[str]) -> None:
    """
    Write to each of ``files`` a rewrite that adds more than whitespace and parses, from bytes, to the file's own syntax tree.

    A file that cannot be read, decoded, processed or opened for writing is left as it was; an error while writing stops the step.

    :param files: paths to rewrite.
    """
    for name in files:
        path = Path(name)

        try:
            raw = path.read_bytes()
            mark = codecs.BOM_UTF8 if raw.startswith(codecs.BOM_UTF8) else b""
            text = raw.removeprefix(mark).decode()
            fixed: bytes = mark + _fix_src(text).encode()

            if b"".join(fixed.split()) == b"".join(raw.split()) or ast.dump(ast.parse(fixed)) != ast.dump(ast.parse(raw)):
                continue

            stream = path.open("wb")
        except Exception:
            continue

        with stream:
            stream.write(fixed)


if __name__ == "__main__":
    main(sys.argv[1:])
