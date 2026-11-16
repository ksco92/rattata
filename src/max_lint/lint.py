"""Build the black, isort and flake8 commands that apply the bundled style."""

import sys
from importlib.resources import files
from pathlib import Path

from flake8.discover_files import expand_paths  # type: ignore[import-untyped]
from flake8.utils import normalize_paths  # type: ignore[import-untyped]

from max_lint.config import Config, ConfigError

STYLE = files("max_lint") / "style"
BUNDLED_EXCLUDE = (".git", ".venv")
BUNDLED_PER_FILE_IGNORES = "*/__init__.py: D104, F401"


def python_files(config: Config) -> list[str]:
    """
    List the Python files under ``paths`` and ``test-paths``, minus the excluded ones.

    Exclude patterns follow flake8's ``exclude`` matching.

    :param config: project settings.
    :return: file paths relative to the current directory, sorted.
    :raises ConfigError: when no Python file is left to lint.
    """
    found = expand_paths(
        paths=[*config.paths, *config.test_paths],
        stdin_display_name="stdin",
        filename_patterns=["*.py"],
        exclude=normalize_paths([*BUNDLED_EXCLUDE, *config.exclude]),
    )
    # Every file goes on one command line; batch the list if a project reaches the OS argument limit.
    result = sorted(set(found))

    if not result:
        raise ConfigError(
            "no Python files found under 'paths' and 'test-paths' in [tool.max-lint]; point them at Python sources.",
        )

    return result


def per_file_ignores(config: Config) -> str:
    """
    Combine the bundled per-file ignores, the ``DOC`` exemption of test paths and the project's own entries.

    :param config: project settings.
    :return: a value for flake8's ``--per-file-ignores``.
    """
    entries = [BUNDLED_PER_FILE_IGNORES]

    for path in config.test_paths:
        pattern = path.rstrip("/")
        entries.append(f"{pattern}/*: DOC" if Path(pattern).is_dir() else f"{pattern}: DOC")

    entries.extend(f"{pattern}: {', '.join(codes)}" for pattern, codes in config.per_file_ignores.items())

    return "\n".join(entries)


def lint_commands(config: Config, check: bool) -> list[list[str]]:
    """
    Return the black, isort and flake8 commands, in the order they run.

    :param config: project settings.
    :param check: run black and isort in their check modes, which write nothing.
    :return: one argument list per tool, each run with the current interpreter.
    """
    targets = python_files(config)
    formatters = str(STYLE / "formatters.toml")
    root = Path.cwd()
    black = [sys.executable, "-m", "black", "--config", formatters]
    black += [f"--target-version={version}" for version in config.black_target_versions]
    isort = [sys.executable, "-m", "isort", "--settings-file", formatters, "--src", str(root / "src"), "--src", str(root)]

    if check:
        black.append("--check")
        isort.append("--check-only")

    flake8 = [
        sys.executable,
        "-m",
        "flake8",
        "--config",
        str(STYLE / "flake8.ini"),
        f"--per-file-ignores={per_file_ignores(config)}",
    ]

    return [[*command, "--", *targets] for command in (black, isort, flake8)]
