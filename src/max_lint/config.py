"""Load the ``[tool.max-lint]`` table that declares what a project owns."""

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

from black.files import infer_target_version

LIST_KEYS = ("paths", "test-paths", "exclude", "coverage-source", "coverage-omit")
KNOWN_KEYS = (*LIST_KEYS, "per-file-ignores")
FLAKE8_CODE = re.compile(r"[A-Z]+[0-9]*")
LOCKED_MYPY_KEYS = (
    "disallow_untyped_defs",
    "allow_untyped_defs",
    "no_disallow_untyped_defs",
    "warn_redundant_casts",
    "no_warn_redundant_casts",
    "no_implicit_optional",
    "implicit_optional",
    "disallow_any_unimported",
    "allow_any_unimported",
    "no_disallow_any_unimported",
    "disallow_any_generics",
    "allow_any_generics",
    "no_disallow_any_generics",
    "disallow_any_explicit",
    "allow_any_explicit",
    "no_disallow_any_explicit",
    "warn_return_any",
    "no_warn_return_any",
)


class ConfigError(Exception):
    """A missing or invalid project setting; the message names the problem and the fix."""


@dataclass(frozen=True)
class Config:
    """Project settings, with paths relative to the directory of ``pyproject.toml``."""

    paths: list[str]
    test_paths: list[str]
    exclude: list[str]
    coverage_source: list[str]
    coverage_omit: list[str]
    per_file_ignores: dict[str, list[str]]
    black_target_versions: list[str]


def _is_str_list(value: object) -> bool:
    """Return whether ``value`` is a list of non-empty strings."""
    return isinstance(value, list) and all(isinstance(item, str) and item for item in value)


def _table(document: dict[str, object], key: str) -> dict[str, object]:
    table = document.get(key, {})

    if not isinstance(table, dict):
        raise ConfigError(f"'{key}' in pyproject.toml must be a table, for example [{key}].")

    return table


def _reject_locked_mypy_keys(document: dict[str, object]) -> None:
    """
    Reject a ``[tool.mypy]`` table or ``[[tool.mypy.overrides]]`` entry that sets a key max-lint fixes, in any spelling mypy accepts.

    :param document: the parsed ``pyproject.toml``.
    :raises ConfigError: when the mypy tables are malformed or set a locked key.
    """
    mypy = _table(document, "tool").get("mypy", {})
    overrides = mypy.get("overrides", []) if isinstance(mypy, dict) else None

    if not isinstance(overrides, list) or not all(isinstance(entry, dict) for entry in overrides):
        raise ConfigError(
            "'mypy' in [tool] must be a table and its 'overrides' a list of tables; write [tool.mypy] and [[tool.mypy.overrides]].",
        )

    places = [
        ("[tool.mypy]", mypy),
        *((f"[[tool.mypy.overrides]] for module {entry.get('module')!r}", entry) for entry in overrides),
    ]

    for place, settings in places:
        for key in settings:
            if key in LOCKED_MYPY_KEYS:
                raise ConfigError(f"{key!r} is set in {place}, but max-lint fixes it; remove it.")


def load_config(pyproject: Path) -> Config:
    """
    Read and validate the ``[tool.max-lint]`` table of a ``pyproject.toml``.

    :param pyproject: path to the project's ``pyproject.toml``.
    :return: the validated settings.
    :raises ConfigError: when the file, the table or a key is missing or invalid.
    """
    try:
        with pyproject.open("rb") as file:
            document = tomllib.load(file)
    except FileNotFoundError:
        raise ConfigError(f"{pyproject} not found; run max-lint from the directory that holds pyproject.toml.") from None
    except tomllib.TOMLDecodeError as error:
        raise ConfigError(f"{pyproject} is not valid TOML ({error}); fix the syntax.") from None

    table = _table(document, "tool").get("max-lint")

    if table is None:
        raise ConfigError(f'{pyproject} has no [tool.max-lint] table; add one with paths = ["src"].')

    if not isinstance(table, dict):
        raise ConfigError("'max-lint' in [tool] must be a table; write it as [tool.max-lint] with paths = [\"src\"].")

    for key in table:
        if key not in KNOWN_KEYS:
            raise ConfigError(f"unknown key {key!r} in [tool.max-lint]; remove it (known keys: {', '.join(KNOWN_KEYS)}).")

    if "paths" not in table:
        raise ConfigError("[tool.max-lint] is missing 'paths'; add the source paths, for example paths = [\"src\"].")

    for key in LIST_KEYS:
        if not _is_str_list(table.get(key, [])):
            raise ConfigError(f"'{key}' in [tool.max-lint] must be a list of non-empty strings.")

    if not table["paths"]:
        raise ConfigError("'paths' in [tool.max-lint] is empty; list at least one source path.")

    per_file_ignores = table.get("per-file-ignores", {})

    if not isinstance(per_file_ignores, dict) or not all(
        glob and _is_str_list(codes) and all(FLAKE8_CODE.fullmatch(code) for code in codes)
        for glob, codes in per_file_ignores.items()
    ):
        raise ConfigError(
            "'per-file-ignores' in [tool.max-lint] must be a table of non-empty path glob to a list of flake8 codes such as \"D100\".",
        )

    for glob in per_file_ignores:
        if Path(glob).is_absolute() or glob.endswith("/"):
            raise ConfigError(
                f"'per-file-ignores' in [tool.max-lint] has the glob {glob!r}, which matches no file; "
                "use a path relative to pyproject.toml that ends in a file name or pattern.",
            )

    for key in ("paths", "test-paths"):
        for path in table.get(key, []):
            if not (pyproject.parent / path).exists():
                raise ConfigError(f"'{key}' in [tool.max-lint] lists {path!r}, which does not exist; fix or remove it.")

    if not isinstance(_table(document, "project").get("requires-python", ""), str):
        raise ConfigError("'requires-python' in [project] must be a string, for example \">=3.13\".")

    _reject_locked_mypy_keys(document)

    return Config(
        paths=table["paths"],
        test_paths=table.get("test-paths", []),
        exclude=table.get("exclude", []),
        coverage_source=table.get("coverage-source", []),
        coverage_omit=table.get("coverage-omit", []),
        per_file_ignores=per_file_ignores,
        black_target_versions=[version.name.lower() for version in infer_target_version(document) or []],
    )
