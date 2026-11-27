"""Flake8 plugin enforcing deterministic coding, docstring, comment-ratio and test rules."""

import argparse
import ast
import contextlib
import json
import os
import re
import sys
import tokenize
from collections.abc import Iterator
from importlib.metadata import version as package_version
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, Self

DEPRECATED_TYPING_NAMES = frozenset(
    {
        "AbstractSet",
        "AsyncGenerator",
        "AsyncIterable",
        "AsyncIterator",
        "Awaitable",
        "Callable",
        "Collection",
        "Coroutine",
        "Dict",
        "FrozenSet",
        "Generator",
        "Iterable",
        "Iterator",
        "List",
        "Mapping",
        "MutableMapping",
        "MutableSequence",
        "MutableSet",
        "Optional",
        "Sequence",
        "Set",
        "Tuple",
        "Type",
        "Union",
    },
)
MAX_MODULE_DOCSTRING_LINES = 10
MAX_NESTING_DEPTH = 4
MAX_COMMENT_RATIO = 0.40
MIN_LINES_FOR_RATIO = 20
CRUMB_COMMENT = re.compile(r"^#[ \t]*(?:TODO|FIXME|XXX|HACK)(?:[:(\s]|$)", re.IGNORECASE)
DOCUMENTED_ABSENCE = re.compile(
    r"(?:#[ \t]*Panics:[ \t]*never\b|^[ \t]*:raises(?:[ \t]+\w+)?:[ \t]*(?:none|nothing|never)\.?$)",
    re.IGNORECASE | re.MULTILINE,
)
SPHINX_FIELD = re.compile(r"^[ \t]*:(?:param|type|return|returns|rtype|yield|yields|ytype|raises|raise|ivar|cvar|var)\b")
DOCSTRING_DELIMITER = re.compile(r'^[rRuUfFbB]{0,2}(?:"""|\'\'\')$')
SILENT_EXCEPT_NAMES = frozenset({"Exception", "BaseException"})
NESTING_NODES = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.With, ast.AsyncWith, ast.Try, ast.TryStar, ast.Match)
PATCH_DECORATORS = frozenset(
    {
        "patch",
        "patch.object",
        "patch.dict",
        "patch.multiple",
        "mock.patch",
        "mock.patch.object",
        "mock.patch.dict",
        "mock.patch.multiple",
        "unittest.mock.patch",
        "unittest.mock.patch.object",
        "unittest.mock.patch.dict",
        "unittest.mock.patch.multiple",
    },
)

ErrorTuple = tuple[int, int, str, type["MaxLintPlugin"]]


if TYPE_CHECKING:

    class _OptionManager(Protocol):
        def add_option(self: Self, *args: str, **kwargs: str | bool) -> None: ...


def _is_banned_unittest_module(module: str) -> bool:
    """
    Return whether ``module`` is ``unittest`` or a non-``mock`` submodule of ``unittest``.

    :param module: dotted module name from an import statement.
    :return: True when the module is banned in pytest suites.
    """
    if module == "unittest":
        return True

    return module.startswith("unittest.") and module != "unittest.mock" and not module.startswith("unittest.mock.")


def _docstring_node(node: ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef) -> ast.Constant | None:
    """
    Return the docstring ``ast.Constant`` of ``node``, or ``None`` when absent.

    :param node: AST node that may begin with a string literal docstring.
    :return: leading docstring constant node, or None when absent.
    """
    if not node.body:
        return None

    first = node.body[0]

    if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
        return first.value

    return None


def _is_silent_pass_body(body: list[ast.stmt]) -> bool:
    """
    Return whether ``body`` consists solely of ``pass`` or ``...`` statements.

    :param body: statement list from an ``except`` handler.
    :return: True when every statement is ``pass`` or an ellipsis literal.
    """
    for stmt in body:
        if isinstance(stmt, ast.Pass):
            continue

        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant) and stmt.value.value is Ellipsis:
            continue

        return False

    return bool(body)


def _is_patch_decorator(decorator: ast.expr) -> bool:
    """
    Return whether ``decorator`` is a ``unittest.mock.patch`` decorator call or reference.

    :param decorator: function decorator expression AST node.
    :return: True when the decorator references ``patch``, ``mock.patch`` or ``unittest.mock.patch`` and their helpers.
    """
    parts: list[str] = []
    current: ast.expr = decorator.func if isinstance(decorator, ast.Call) else decorator

    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value

    if not isinstance(current, ast.Name):
        return False

    parts.append(current.id)
    parts.reverse()

    return ".".join(parts) in PATCH_DECORATORS


def _max_nesting_violations(root: ast.AST) -> Iterator[tuple[int, int]]:
    """
    Yield ``(line, col)`` for each block in ``root`` whose nesting exceeds ``MAX_NESTING_DEPTH``, flattening ``elif`` chains.

    :param root: function AST node whose body is inspected.
    :yields: ``(line, col)`` location of each control-flow node past the depth limit.
    """
    stack: list[tuple[ast.AST, int]] = [(root, 0)]

    while stack:
        current, depth = stack.pop()
        elif_child: ast.If | None = None

        if (
            isinstance(current, ast.If)
            and len(current.orelse) == 1
            and isinstance(current.orelse[0], ast.If)
            and current.orelse[0].col_offset == current.col_offset
        ):
            elif_child = current.orelse[0]

        pending: list[tuple[ast.AST, int]] = []

        for child in ast.iter_child_nodes(current):
            if isinstance(child, (ast.expr, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue

            if child is elif_child:
                pending.append((child, depth))
            elif isinstance(child, NESTING_NODES):
                next_depth = depth + 1

                if next_depth > MAX_NESTING_DEPTH:
                    yield child.lineno, child.col_offset
                else:
                    pending.append((child, next_depth))
            else:
                pending.append((child, depth))

        stack.extend(reversed(pending))


def _docstring_prose_lines(tree: ast.Module, lines: list[str]) -> set[int]:
    """
    Return 1-based line numbers of docstring prose, excluding delimiters, Sphinx fields and doctests.

    :param tree: parsed module AST.
    :param lines: physical source lines of the module.
    :return: set of 1-based line numbers containing docstring prose.
    """
    prose: set[int] = set()

    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        doc = _docstring_node(node)

        if doc is None or doc.end_lineno is None:
            continue

        in_doctest = False
        in_sphinx_field = False
        field_indent = 0

        for line_no in range(doc.lineno, min(doc.end_lineno, len(lines)) + 1):
            raw = lines[line_no - 1]
            stripped = raw.strip()

            if not stripped:
                in_doctest = False
                in_sphinx_field = False
                continue

            if DOCSTRING_DELIMITER.match(stripped):
                in_doctest = False
                in_sphinx_field = False
                continue

            if stripped.startswith(">>>"):
                in_doctest = True
                in_sphinx_field = False
                continue

            if in_doctest:
                continue

            if SPHINX_FIELD.match(raw):
                in_sphinx_field = True
                field_indent = len(raw) - len(raw.lstrip())
                continue

            if in_sphinx_field and (len(raw) - len(raw.lstrip())) > field_indent:
                continue

            in_sphinx_field = False
            prose.add(line_no)

    return prose


def _check_comment_ratio(tree: ast.Module, lines: list[str], tokens: list[tokenize.TokenInfo]) -> Iterator[tuple[int, int, str]]:
    """
    Yield ``MXL005`` when prose comments and docstrings exceed ``MAX_COMMENT_RATIO`` of non-blank lines.

    :param tree: parsed module AST.
    :param lines: physical source lines of the module.
    :param tokens: token stream of the module.
    :yields: ``(line, col, message)`` violation tuple when the prose ratio exceeds ``MAX_COMMENT_RATIO``.
    """
    non_blank = {index for index, line in enumerate(lines, start=1) if line.strip()}

    if len(non_blank) < MIN_LINES_FOR_RATIO:
        return

    comment_only: set[int] = set()
    code_tokens_on_line: set[int] = set()

    for token in tokens:
        if token.type in (
            tokenize.NL,
            tokenize.NEWLINE,
            tokenize.INDENT,
            tokenize.DEDENT,
            tokenize.ENDMARKER,
            tokenize.ENCODING,
        ):
            continue

        if token.type == tokenize.COMMENT:
            comment_only.add(token.start[0])
        else:
            for line_no in range(token.start[0], token.end[0] + 1):
                code_tokens_on_line.add(line_no)

    doc_prose = _docstring_prose_lines(tree, lines)
    pure_comments = comment_only - code_tokens_on_line
    prose_lines = (pure_comments | doc_prose) & non_blank
    ratio = len(prose_lines) / len(non_blank)

    if ratio > MAX_COMMENT_RATIO:
        yield (
            1,
            0,
            f"MXL005 comment and docstring prose is {round(ratio * 100)}% of non-blank lines (max {MAX_COMMENT_RATIO:.0%})",
        )


def _check_tokens(
    tokens: list[tokenize.TokenInfo],
    is_test: bool,
) -> Iterator[tuple[int, int, str]]:
    """
    Yield token-level violations (``MXL008`` documented absence, ``MXL009`` crumb comments).

    :param tokens: token stream of the module.
    :param is_test: whether the file is classified as a test module.
    :yields: ``(line, col, message)`` violation tuples from comments.
    """
    for token in tokens:
        if token.type != tokenize.COMMENT:
            continue

        if DOCUMENTED_ABSENCE.search(token.string):
            yield token.start[0], token.start[1], "MXL008 do not document absences in comments"

        if not is_test and CRUMB_COMMENT.match(token.string):
            yield token.start[0], token.start[1], "MXL009 remove TODO/FIXME/XXX/HACK crumb from production source"


def _check_imports(node: ast.Import | ast.ImportFrom, is_test: bool) -> Iterator[tuple[int, int, str]]:
    """
    Yield import violations (``MXL001``, ``MXL010``, ``MXL012``).

    :param node: import or from-import AST node.
    :param is_test: whether the file is classified as a test module.
    :yields: ``(line, col, message)`` violation tuples for banned imports.
    """
    if isinstance(node, ast.Import):
        for alias in node.names:
            if is_test and _is_banned_unittest_module(alias.name):
                yield node.lineno, node.col_offset, "MXL010 use pytest instead of unittest in tests"

            if is_test and alias.name.split(".")[-1].startswith("test_"):
                yield node.lineno, node.col_offset, f"MXL012 do not import sibling test module {alias.name!r}"

        return

    module = node.module or ""

    if node.level == 0 and module == "typing":
        for alias in node.names:
            if alias.name in DEPRECATED_TYPING_NAMES:
                yield (
                    node.lineno,
                    node.col_offset,
                    f"MXL001 deprecated typing.{alias.name}; use builtin generics, '|' or collections.abc",
                )

    if is_test and node.level == 0 and module == "unittest":
        for alias in node.names:
            if alias.name != "mock":
                yield node.lineno, node.col_offset, "MXL010 use pytest instead of unittest in tests"

    if is_test and node.level == 0 and module != "unittest" and _is_banned_unittest_module(module):
        yield node.lineno, node.col_offset, "MXL010 use pytest instead of unittest in tests"

    if is_test and module and module.split(".")[-1].startswith("test_"):
        yield node.lineno, node.col_offset, f"MXL012 do not import sibling test module {module!r}"
    elif is_test and ((node.level > 0 and not module) or module.split(".")[-1] in {"tests", "test"}):
        for alias in node.names:
            if alias.name.startswith("test_"):
                yield node.lineno, node.col_offset, f"MXL012 do not import sibling test module {alias.name!r}"


def _check_function(node: ast.FunctionDef | ast.AsyncFunctionDef, is_test: bool) -> Iterator[tuple[int, int, str]]:
    """
    Yield function-level violations (``MXL007`` nesting, ``MXL011`` patch decorator).

    :param node: function or async function definition AST node.
    :param is_test: whether the file is classified as a test module.
    :yields: ``(line, col, message)`` violation tuples for the function.
    """
    for line, col in _max_nesting_violations(node):
        yield line, col, f"MXL007 block nesting exceeds {MAX_NESTING_DEPTH} levels"

    if is_test:
        for decorator in node.decorator_list:
            if _is_patch_decorator(decorator):
                yield (
                    decorator.lineno,
                    decorator.col_offset,
                    "MXL011 use a 'with patch(...)' context manager instead of @patch decorator",
                )


def _check_node(node: ast.AST, is_test: bool) -> Iterator[tuple[int, int, str]]:
    """
    Yield AST violations for a single syntax node.

    :param node: AST node visited during module traversal.
    :param is_test: whether the file is classified as a test module.
    :yields: ``(line, col, message)`` violation tuples for ``node``.
    """
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        yield from _check_imports(node, is_test)

    if isinstance(node, ast.ExceptHandler):
        if isinstance(node.type, ast.Tuple):
            yield node.lineno, node.col_offset, "MXL003 use separate single-exception except clauses"

        is_broad = node.type is None or (isinstance(node.type, ast.Name) and node.type.id in SILENT_EXCEPT_NAMES)

        if is_broad and _is_silent_pass_body(node.body):
            yield node.lineno, node.col_offset, "MXL004 do not silently swallow exceptions with pass"

    if isinstance(node, ast.Raise):
        exc = node.exc

        is_bare_call = (
            isinstance(exc, ast.Call)
            and isinstance(exc.func, ast.Name)
            and exc.func.id == "NotImplementedError"
            and not exc.args
            and not exc.keywords
        )

        is_bare_name = isinstance(exc, ast.Name) and exc.id == "NotImplementedError"

        if is_bare_call or is_bare_name:
            yield node.lineno, node.col_offset, "MXL006 raise NotImplementedError with an explanatory message"

    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        yield from _check_function(node, is_test)

    if isinstance(node, ast.ClassDef) and is_test and node.name.startswith("Test"):
        yield node.lineno, node.col_offset, "MXL010 use module-level pytest functions instead of test classes"

    if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
        doc = _docstring_node(node)

        if doc is not None and isinstance(doc.value, str) and DOCUMENTED_ABSENCE.search(doc.value):
            yield doc.lineno, doc.col_offset, "MXL008 do not document absences in docstrings"


class MaxLintPlugin:
    """Flake8 AST and token checker for deterministic max-lint rules (``MXL001``–``MXL012``)."""

    name = "max-lint-rules"
    version = package_version("max-lint")
    test_paths: tuple[str, ...] = ()

    def __init__(
        self: Self,
        tree: ast.Module,
        filename: str = "",
        lines: list[str] | None = None,
        file_tokens: list[tokenize.TokenInfo] | None = None,
    ) -> None:
        """
        Store the parsed syntax tree, path, lines and tokens supplied by flake8.

        :param tree: parsed AST of the module.
        :param filename: path of the file being checked.
        :param lines: physical lines of the file.
        :param file_tokens: token stream of the file.
        """
        self.tree = tree
        self.filename = filename
        self.lines = lines or []
        self.file_tokens = file_tokens or []

    @staticmethod
    def add_options(option_manager: "_OptionManager") -> None:
        """
        Register ``max-lint-test-paths``, the JSON list of absolute test paths that max-lint writes into its flake8 config.

        :param option_manager: flake8's option manager.
        """
        option_manager.add_option("--max-lint-test-paths", default="[]", parse_from_config=True, help=argparse.SUPPRESS)

    @classmethod
    def parse_options(cls: type[Self], options: argparse.Namespace) -> None:
        """
        Store the test paths from the parsed flake8 options, ending the run unless they are a JSON list of strings.

        Without max-lint the list is empty and no file is a test.

        :param options: flake8's parsed options.
        """
        test_paths = None

        with contextlib.suppress(ValueError, RecursionError):
            test_paths = json.loads(options.max_lint_test_paths)

        if not isinstance(test_paths, list) or not all(isinstance(path, str) for path in test_paths):
            sys.exit("flake8: the max-lint-test-paths option must be a JSON list of strings.")

        cls.test_paths = tuple(test_paths)

    def run(self: Self) -> list[ErrorTuple]:
        """
        Run every ``MXL`` rule on the module and return flake8 violation tuples.

        :return: ``(line, col, message, cls)`` tuples for each violation.
        """
        errors: list[ErrorTuple] = []
        path = Path(os.path.abspath(self.filename))
        is_test = any(path.is_relative_to(test_path) for test_path in self.test_paths)
        module_doc = _docstring_node(self.tree)

        if module_doc is not None and module_doc.end_lineno is not None:
            span = module_doc.end_lineno - module_doc.lineno + 1

            if span > MAX_MODULE_DOCSTRING_LINES:
                errors.append(
                    (
                        module_doc.lineno,
                        module_doc.col_offset,
                        f"MXL002 module docstring is {span} lines (max {MAX_MODULE_DOCSTRING_LINES})",
                        type(self),
                    ),
                )

        for node in ast.walk(self.tree):
            for line, col, message in _check_node(node, is_test):
                errors.append((line, col, message, type(self)))

        for line, col, message in _check_tokens(self.file_tokens, is_test):
            errors.append((line, col, message, type(self)))

        for line, col, message in _check_comment_ratio(self.tree, self.lines, self.file_tokens):
            errors.append((line, col, message, type(self)))

        errors.sort(key=lambda item: (item[0], item[1], item[2]))

        return errors
