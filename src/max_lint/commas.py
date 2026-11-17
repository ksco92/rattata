"""Add trailing commas with add-trailing-comma, keeping only rewrites that insert commas and leave the syntax tree unchanged."""

import ast
import codecs
import io
import sys
import tokenize
from pathlib import Path

from add_trailing_comma._main import _fix_src  # type: ignore[import-untyped]
from black.comments import FMT_OFF, FMT_SKIP, contains_fmt_directive


def _inserts_only_commas(raw: bytes, fixed: bytes) -> bool:
    """Whether ``fixed``, with whitespace removed, is ``raw`` with one or more commas inserted and nothing else changed."""
    old, new = b"".join(raw.split()), b"".join(fixed.split())
    matched = 0

    for byte in new:
        if matched < len(old) and byte == old[matched]:
            matched += 1
        elif byte != ord(","):
            return False

    return matched == len(old) < len(new)


def main(files: list[str]) -> None:
    """
    Write add-trailing-comma's rewrite of each of ``files`` that only inserts commas and parses, from bytes, to the same tree.

    A file with a black formatting directive, or that cannot be read, decoded or opened for writing, is left; a write error stops.

    :param files: paths to rewrite.
    """
    for name in files:
        path = Path(name)

        try:
            raw = path.read_bytes()
            mark = codecs.BOM_UTF8 if raw.startswith(codecs.BOM_UTF8) else b""
            text = raw.removeprefix(mark).decode()
            tokens = tokenize.generate_tokens(io.StringIO(text).readline)

            if any(
                token.type == tokenize.COMMENT and contains_fmt_directive(token.string, FMT_OFF | FMT_SKIP) for token in tokens
            ):
                continue

            fixed: bytes = mark + _fix_src(text).encode()

            if not _inserts_only_commas(raw, fixed) or ast.dump(ast.parse(fixed)) != ast.dump(ast.parse(raw)):
                continue

            stream = path.open("wb")
        except Exception:
            continue

        with stream:
            stream.write(fixed)


if __name__ == "__main__":
    main(sys.argv[1:])
