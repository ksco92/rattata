"""Flake8 plugin enforcing deterministic coding, docstring, comment-ratio and test rules."""

import ast
import re
import tokenize
from collections.abc import Iterator
from pathlib import Path

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
CRUMB_COMMENT = re.compile(r"^#\s*(?:TODO|FIXME|XXX|HACK)(?:[:\s]|$)", re.IGNORECASE)
DOCUMENTED_ABSENCE = re.compile(
    r"(?:#\s*Panics:\s*never\b|^\s*:raises(?:\s+\w+)?:\s*(?:none|nothing|never)\.?$)",
    re.IGNORECASE | re.MULTILINE,
)
SPHINX_FIELD = re.compile(r"^\s*:(?:param|type|return|returns|rtype|yield|yields|ytype|raises|raise|ivar|cvar|var)\b")
SILENT_EXCEPT_NAMES = frozenset({"Exception", "BaseException"})
NESTING_NODES = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.With, ast.AsyncWith, ast.Try, ast.TryStar, ast.Match)

ErrorTuple = tuple[int, int, str, type["MaxLintPlugin"]]


def _is_test_file(filename: str) -> bool:
    """
    Return whether ``filename`` is a pytest test file.

    :param filename: Path of the Python file being checked.
    :return: True when the file is a test module or lives under a test directory.
    """
    path = Path(filename)
    name = path.name

    if name.startswith("test_") or name.endswith("_test.py") or name == "conftest.py":
        return True

    return any(part in {"tests", "test"} for part in path.parts[:-1])


def _docstring_node(node: ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef) -> ast.Constant | None:
    """
    Return the docstring ``ast.Constant`` of ``node``, or ``None`` when absent.

    :param node: AST node that may begin with a string literal docstring.
    :return: Leading docstring constant node, or None when absent.
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

    :param body: Statement list from an ``except`` handler.
    :return: True when every statement is ``pass`` or an ellipsis literal.
    """
    for stmt in body:
        if isinstance(stmt, ast.Pass):
            continue

        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant) and stmt.value.value is Ellipsis:
            continue

        return False

    return bool(body)


def _is_broad_except(handler: ast.ExceptHandler) -> bool:
    """
    Return whether ``handler`` catches bare ``except``, ``Exception`` or ``BaseException``.

    :param handler: Exception handler AST node.
    :return: True when the handler catches all exceptions broadly.
    """
    if handler.type is None:
        return True

    return isinstance(handler.type, ast.Name) and handler.type.id in SILENT_EXCEPT_NAMES


def _is_patch_decorator(decorator: ast.expr) -> bool:
    """
    Return whether ``decorator`` is a ``@patch`` or ``@mock.patch`` call or reference.

    :param decorator: Function decorator expression AST node.
    :return: True when the decorator invokes ``patch`` or ``patch.*``.
    """
    target = decorator.func if isinstance(decorator, ast.Call) else decorator

    if isinstance(target, ast.Name):
        return target.id == "patch"

    if isinstance(target, ast.Attribute):
        if target.attr == "patch":
            return True

        return isinstance(target.value, ast.Attribute) and target.value.attr == "patch"

    return False


def _max_nesting_violations(node: ast.AST, depth: int) -> Iterator[tuple[int, int]]:
    """
    Yield ``(line, col)`` for each block in ``node`` whose nesting exceeds ``MAX_NESTING_DEPTH``.

    :param node: Current AST node being traversed.
    :param depth: Current control-flow nesting depth inside the enclosing function.
    :yields: ``(line, col)`` location of each control-flow node past the depth limit.
    """
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue

        if isinstance(child, NESTING_NODES):
            next_depth = depth + 1

            if next_depth > MAX_NESTING_DEPTH:
                yield child.lineno, child.col_offset
            else:
                yield from _max_nesting_violations(child, next_depth)
        else:
            yield from _max_nesting_violations(child, depth)


def _docstring_prose_lines(tree: ast.Module, lines: list[str]) -> set[int]:
    """
    Return 1-based line numbers of docstring prose, excluding Sphinx field and doctest lines.

    :param tree: Parsed module AST.
    :param lines: Physical source lines of the module.
    :return: Set of 1-based line numbers containing docstring prose.
    """
    prose: set[int] = set()

    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        doc = _docstring_node(node)

        if doc is None or doc.end_lineno is None:
            continue

        in_doctest = False

        for line_no in range(doc.lineno, min(doc.end_lineno, len(lines)) + 1):
            raw = lines[line_no - 1]
            stripped = raw.strip()

            if not stripped:
                in_doctest = False
                continue

            if stripped.startswith(">>>"):
                in_doctest = True
                continue

            if in_doctest:
                continue

            if SPHINX_FIELD.match(raw):
                continue

            prose.add(line_no)

    return prose


def _check_comment_ratio(tree: ast.Module, lines: list[str], tokens: list[tokenize.TokenInfo]) -> Iterator[tuple[int, int, str]]:
    """
    Yield ``MXL005`` when prose comments and docstrings exceed 40% of non-blank lines.

    :param tree: Parsed module AST.
    :param lines: Physical source lines of the module.
    :param tokens: Token stream of the module.
    :yields: ``(line, col, message)`` violation tuple when the prose ratio exceeds 40%.
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
        percent = int(round(ratio * 100))
        yield 1, 0, f"MXL005 comment and docstring prose is {percent}% of non-blank lines (max 40%)"


def _check_tokens(
    tokens: list[tokenize.TokenInfo],
    is_test: bool,
) -> Iterator[tuple[int, int, str]]:
    """
    Yield token-level violations (``MXL008`` documented absence, ``MXL009`` crumb comments).

    :param tokens: Token stream of the module.
    :param is_test: Whether the file is classified as a test module.
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

    :param node: Import or from-import AST node.
    :param is_test: Whether the file is classified as a test module.
    :yields: ``(line, col, message)`` violation tuples for banned imports.
    """
    if isinstance(node, ast.Import):
        for alias in node.names:
            if is_test and alias.name == "unittest":
                yield node.lineno, node.col_offset, "MXL010 use pytest instead of unittest in tests"

            if is_test and alias.name.split(".")[-1].startswith("test_"):
                yield node.lineno, node.col_offset, f"MXL012 do not import sibling test module {alias.name!r}"

        return

    module = node.module or ""

    if module == "typing":
        for alias in node.names:
            if alias.name in DEPRECATED_TYPING_NAMES:
                yield (
                    node.lineno,
                    node.col_offset,
                    f"MXL001 deprecated typing.{alias.name}; use builtin generics, '|' or collections.abc",
                )

    if is_test and module == "unittest":
        for alias in node.names:
            if alias.name != "mock":
                yield node.lineno, node.col_offset, "MXL010 use pytest instead of unittest in tests"

    if is_test and module and module.split(".")[-1].startswith("test_"):
        yield node.lineno, node.col_offset, f"MXL012 do not import sibling test module {module!r}"


def _check_function(node: ast.FunctionDef | ast.AsyncFunctionDef, is_test: bool) -> Iterator[tuple[int, int, str]]:
    """
    Yield function-level violations (``MXL007`` nesting, ``MXL011`` patch decorator).

    :param node: Function or async function definition AST node.
    :param is_test: Whether the file is classified as a test module.
    :yields: ``(line, col, message)`` violation tuples for the function.
    """
    for line, col in _max_nesting_violations(node, 0):
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
    :param is_test: Whether the file is classified as a test module.
    :yields: ``(line, col, message)`` violation tuples for ``node``.
    """
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        yield from _check_imports(node, is_test)

    if isinstance(node, ast.ExceptHandler):
        if isinstance(node.type, ast.Tuple):
            yield node.lineno, node.col_offset, "MXL003 use separate single-exception except clauses"

        if _is_broad_except(node) and _is_silent_pass_body(node.body):
            yield node.lineno, node.col_offset, "MXL004 do not silently swallow exceptions with pass"

    if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call):
        func = node.exc.func

        if isinstance(func, ast.Name) and func.id == "NotImplementedError" and not node.exc.args and not node.exc.keywords:
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
    version = "0.11.0"

    def __init__(
        self: "MaxLintPlugin",
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

    def run(self: "MaxLintPlugin") -> list[ErrorTuple]:
        """
        Run every ``MXL`` rule on the module and return flake8 violation tuples.

        :return: ``(line, col, message, cls)`` tuples for each violation.
        """
        errors: list[ErrorTuple] = []
        is_test = _is_test_file(self.filename)
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
