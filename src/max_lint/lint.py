"""Build the add-trailing-comma, black, isort, flake8 and mypy commands that apply the bundled style."""

import contextlib
import os
import re
import stat
import sys
from fnmatch import fnmatchcase
from importlib.resources import files
from pathlib import Path

from flake8.discover_files import expand_paths  # type: ignore[import-untyped]
from flake8.utils import normalize_paths  # type: ignore[import-untyped]

from max_lint.config import Config, ConfigError

STYLE = files("max_lint") / "style"
BUNDLED_EXCLUDE = (".git", ".venv")
INIT_CODES = ("D104", "F401")
FLAKE8_SEPARATORS = re.compile(r"[\s:,]")
TOOL_ENVIRONMENT = {"DOCUTILSCONFIG": str(STYLE / "docutils.conf"), "PYTHONSAFEPATH": "1"}


def _identity(path: str | Path) -> tuple[int, int]:
    """Return the device and inode of the file or directory ``path`` resolves to."""
    status = os.stat(path)

    return status.st_dev, status.st_ino


def python_files(config: Config) -> list[str]:
    """
    List the Python files under ``paths`` and ``test-paths``, minus the excluded ones.

    :param config: project settings; exclude patterns follow flake8's ``exclude`` matching.
    :return: paths relative to the current directory, sorted, with each file once under the first spelling found and
        entries that do not resolve to a regular file left out.
    :raises ConfigError: when no Python file is left to lint or one of them is the file ``-``.
    """
    found = expand_paths(
        paths=[*config.paths, *config.test_paths],
        stdin_display_name="stdin",
        filename_patterns=["*.py"],
        exclude=normalize_paths([*BUNDLED_EXCLUDE, *config.exclude]),
    )
    spellings: dict[tuple[int, int], str] = {}

    for path in found:
        with contextlib.suppress(OSError):
            if stat.S_ISREG(os.stat(path).st_mode):
                spellings.setdefault(_identity(path), os.path.relpath(path))

    result = sorted(spellings.values())

    if not result:
        raise ConfigError(
            "no Python files found under 'paths' and 'test-paths' in [tool.max-lint]; point them at Python sources.",
        )

    if "-" in result:
        raise ConfigError(
            "'-' in [tool.max-lint] names a file that black and flake8 read as standard input; rename the file.",
        )

    return result


def per_file_ignores(config: Config, targets: list[str]) -> str:
    """
    Build a flake8 config whose ``per-file-ignores`` name each target exactly, with all of its ignored codes.

    :param config: project settings.
    :param targets: paths from ``python_files``.
    :return: the config file text.
    :raises ConfigError: when a target that needs ignored codes has whitespace, ``:``, ``,`` or a non-UTF-8 name.
    """
    lines = ["[flake8]", "per-file-ignores ="]

    for target in targets:
        codes = list(INIT_CODES) if os.path.basename(target) == "__init__.py" else []

        for glob, entry_codes in config.per_file_ignores.items():
            if fnmatchcase(target, os.path.normpath(glob)):
                codes.extend(entry_codes)

        if not codes:
            continue

        if FLAKE8_SEPARATORS.search(target) or target.encode("utf-8", "replace").decode("utf-8") != target:
            raise ConfigError(
                f"{target!r} needs ignored codes from [tool.max-lint] but flake8 cannot name a path with whitespace, ':', ',' "
                "or a name that is not UTF-8; rename it or add it to 'exclude'.",
            )

        pattern = re.sub(r"([*?[])", r"[\1]", target)
        lines.append(f"    ./{pattern}: {', '.join(dict.fromkeys(codes))}")

    return "\n".join(lines) + "\n"


def lint_commands(config: Config, check: bool, scratch: Path) -> list[list[str]]:
    """
    Return the lint commands in the order they run: black, add-trailing-comma and a quiet black in write mode, then isort, flake8 and mypy.

    :param config: project settings.
    :param check: run black and isort in their check modes and leave out add-trailing-comma, so nothing is written.
    :param scratch: directory outside the project for the generated flake8 config; it must outlive the commands.
    :return: one argument list per tool, each run with the current interpreter.
    """
    targets = python_files(config)
    ignores = scratch / "per-file-ignores.ini"
    ignores.write_text(per_file_ignores(config, targets), encoding="utf-8")
    formatters = str(STYLE / "formatters.toml")
    root = Path.cwd()
    black = [sys.executable, "-m", "black", "--config", formatters]
    black += [f"--target-version={version}" for version in config.black_target_versions]
    isort = [sys.executable, "-m", "isort", "--settings-file", formatters, "--src", str(root / "src"), "--src", str(root)]

    if check:
        black.append("--check")
        isort.append("--check-only")

    flake8 = [sys.executable, "-m", "flake8", "--config", str(STYLE / "flake8.ini"), "--append-config", str(ignores)]

    commands = [[*command, "--", *targets] for command in (black, isort, flake8)]

    if not check:
        commands[1:1] = [[sys.executable, "-m", "max_lint.commas", *targets], [*black, "--quiet", "--", *targets]]

    mypy = [sys.executable, "-m", "mypy", "--config-file", str(root / "pyproject.toml")]
    mypy += ["--python-executable", sys.executable, "--disallow-untyped-defs", "--warn-redundant-casts", "--no-implicit-optional"]
    mypy += ["--disallow-any-unimported", "--disallow-any-generics", "--disallow-any-explicit", "--warn-return-any"]

    return [*commands, [*mypy, "--", *(f"./{path}" for path in targets)]]
