"""Load the ``[tool.max-lint]`` table that declares what a project owns."""

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

from black.files import infer_target_version

LIST_KEYS = ("paths", "test-paths", "exclude")
KNOWN_KEYS = (*LIST_KEYS, "per-file-ignores")
FLAKE8_CODE = re.compile(r"[A-Z]+[0-9]*")


class ConfigError(Exception):
    """A missing or invalid project setting; the message names the problem and the fix."""


@dataclass(frozen=True)
class Config:
    """Project settings, with paths relative to the directory of ``pyproject.toml``."""

    paths: list[str]
    test_paths: list[str]
    exclude: list[str]
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

    if not isinstance(table, dict):
        raise ConfigError(f'{pyproject} has no [tool.max-lint] table; add one with paths = ["src"].')

    for key in table:
        if key not in KNOWN_KEYS:
            raise ConfigError(f"unknown key '{key}' in [tool.max-lint]; remove it (known keys: {', '.join(KNOWN_KEYS)}).")

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

    for key in ("paths", "test-paths"):
        for path in table.get(key, []):
            if not (pyproject.parent / path).exists():
                raise ConfigError(f"'{key}' in [tool.max-lint] lists '{path}', which does not exist; fix or remove it.")

    if not isinstance(_table(document, "project").get("requires-python", ""), str):
        raise ConfigError("'requires-python' in [project] must be a string, for example \">=3.13\".")

    return Config(
        paths=table["paths"],
        test_paths=table.get("test-paths", []),
        exclude=table.get("exclude", []),
        per_file_ignores=per_file_ignores,
        black_target_versions=[version.name.lower() for version in infer_target_version(document) or []],
    )
