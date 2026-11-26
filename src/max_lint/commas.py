"""Add trailing commas with add-trailing-comma, keeping only rewrites that insert commas and leave the syntax tree unchanged."""

import ast
import codecs
import io
import sys
import tokenize
import warnings
from pathlib import Path

from add_trailing_comma._main import _fix_src  # type: ignore[import-untyped]
from black.comments import FMT_OFF, FMT_SKIP, contains_fmt_directive


def _inserts_only_commas(raw: bytes, fixed: bytes) -> bool:
    """
    Return whether ``fixed``, with whitespace removed, is ``raw`` with one or more commas inserted and nothing else changed.

    :param raw: original file bytes.
    :param fixed: rewritten file bytes.
    :return: True when only commas were inserted.
    """
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
    Write add-trailing-comma's rewrite of each UTF-8 file in ``files`` that only inserts commas and parses to the same tree.

    A file with a bare carriage return or black directive, or that fails to read, process or open, is left; a write error stops.

    :param files: paths to rewrite.
    """
    for name in files:
        path = Path(name)

        try:
            raw = path.read_bytes()

            if b"\r" in raw.replace(b"\r\n", b""):
                continue

            if codecs.lookup(tokenize.detect_encoding(io.BytesIO(raw).readline)[0]).name not in ("utf-8", "utf-8-sig"):
                continue

            mark = codecs.BOM_UTF8 if raw.startswith(codecs.BOM_UTF8) else b""
            text = raw.removeprefix(mark).decode()

            if any(
                token.type == tokenize.COMMENT and contains_fmt_directive(token.string, FMT_OFF | FMT_SKIP)
                for token in tokenize.generate_tokens(io.StringIO(text).readline)
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
    warnings.simplefilter("ignore")
    main(sys.argv[1:])
