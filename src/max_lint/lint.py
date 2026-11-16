"""Build the black, isort and flake8 commands that apply the bundled style."""

import os
import re
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


def python_files(config: Config) -> list[str]:
    """
    List the Python files under ``paths`` and ``test-paths``, minus the excluded ones.

    :param config: project settings; exclude patterns follow flake8's ``exclude`` matching.
    :return: normalized paths relative to the current directory, sorted and without duplicates.
    :raises ConfigError: when no Python file is left to lint.
    """
    found = expand_paths(
        paths=[*config.paths, *config.test_paths],
        stdin_display_name="stdin",
        filename_patterns=["*.py"],
        exclude=normalize_paths([*BUNDLED_EXCLUDE, *config.exclude]),
    )
    result = sorted({os.path.relpath(path) for path in found})

    if not result:
        raise ConfigError(
            "no Python files found under 'paths' and 'test-paths' in [tool.max-lint]; point them at Python sources.",
        )

    return result


def per_file_ignores(config: Config, targets: list[str]) -> str:
    """
    Build a flake8 config whose ``per-file-ignores`` name each target exactly, with all of its ignored codes.

    :param config: project settings.
    :param targets: paths from ``python_files``.
    :return: the config file text.
    :raises ConfigError: when a target that needs ignored codes has whitespace, ``:`` or ``,`` in its path.
    """
    test_roots = [Path(os.path.abspath(path)) for path in config.test_paths]
    lines = ["[flake8]", "per-file-ignores ="]

    for target in targets:
        codes = list(INIT_CODES) if os.path.basename(target) == "__init__.py" else []

        if any(Path(os.path.abspath(target)).is_relative_to(root) for root in test_roots):
            codes.append("DOC")

        for glob, entry_codes in config.per_file_ignores.items():
            if fnmatchcase(target, os.path.normpath(glob)):
                codes.extend(entry_codes)

        if not codes:
            continue

        if FLAKE8_SEPARATORS.search(target):
            raise ConfigError(
                f"'{target}' needs ignored codes from [tool.max-lint] but flake8 cannot name a path with whitespace, ':' or ','; "
                "rename it or add it to 'exclude'.",
            )

        pattern = re.sub(r"([*?[])", r"[\1]", target)
        lines.append(f"    ./{pattern}: {', '.join(dict.fromkeys(codes))}")

    return "\n".join(lines) + "\n"


def lint_commands(config: Config, check: bool, scratch: Path) -> list[list[str]]:
    """
    Return the black, isort and flake8 commands, in the order they run.

    :param config: project settings.
    :param check: run black and isort in their check modes, which write nothing.
    :param scratch: directory outside the project for the generated flake8 config; it must outlive the commands.
    :return: one argument list per tool, each run with the current interpreter and without the working directory on ``sys.path``.
    """
    targets = python_files(config)
    ignores = scratch / "per-file-ignores.ini"
    ignores.write_text(per_file_ignores(config, targets))
    formatters = str(STYLE / "formatters.toml")
    root = Path.cwd()
    black = [sys.executable, "-P", "-m", "black", "--config", formatters]
    black += [f"--target-version={version}" for version in config.black_target_versions]
    isort = [sys.executable, "-P", "-m", "isort", "--settings-file", formatters, "--src", str(root / "src"), "--src", str(root)]

    if check:
        black.append("--check")
        isort.append("--check-only")

    flake8 = [sys.executable, "-P", "-m", "flake8", "--config", str(STYLE / "flake8.ini"), "--append-config", str(ignores)]

    return [[*command, "--", *targets] for command in (black, isort, flake8)]
