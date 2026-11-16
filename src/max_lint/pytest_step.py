"""Build and run the pytest command with branch coverage and a coverage floor the project cannot lower."""

import json
import os
import subprocess
import sys
from pathlib import Path

from max_lint.config import Config, ConfigError
from max_lint.lint import STYLE

FAIL_UNDER = 95
REPORT_NAME = "coverage.json"


def pytest_command(config: Config, scratch: Path) -> list[str]:
    """
    Return the pytest command that measures ``coverage-source`` over ``test-paths``.

    :param config: project settings.
    :param scratch: directory outside the project for the generated coverage config and report; it must outlive the command.
    :return: an argument list that runs pytest with the current interpreter and the working directory on ``sys.path``.
    :raises ConfigError: when ``test-paths`` or ``coverage-source`` is empty.
    """
    if not config.test_paths:
        raise ConfigError("'test-paths' in [tool.max-lint] is empty; list the test paths, for example test-paths = [\"tests\"].")

    if not config.coverage_source:
        raise ConfigError(
            "'coverage-source' in [tool.max-lint] is missing or empty; list the packages or directories to measure, "
            'for example coverage-source = ["src"].',
        )

    coverage_config = scratch / "coverage.toml"
    text = (STYLE / "coverage.toml").read_text(encoding="utf-8")

    if config.coverage_omit:
        omit = ", ".join(
            json.dumps(pattern, ensure_ascii=False).replace("\x7f", "\\u007f").replace("$", "$$")
            for pattern in config.coverage_omit
        )
        text += f"\n[run]\nomit = [{omit}]\n"

    coverage_config.write_text(text, encoding="utf-8")

    return [
        sys.executable,
        "-m",
        "pytest",
        "--import-mode=importlib",
        "--cov-reset",
        *[f"--cov={source}" for source in config.coverage_source],
        f"--cov-config={coverage_config}",
        "--cov-branch",
        "--cov-report=term-missing",
        f"--cov-report=json:{scratch / REPORT_NAME}",
        f"--cov-fail-under={FAIL_UNDER}",
        "--cov-precision=2",
        *(path if os.path.isabs(path) else f"./{path}" for path in config.test_paths),
    ]


def run_tests(command: list[str], scratch: Path) -> int:
    """
    Run the pytest command and fail when coverage measured no statements, even if every test passed.

    :param command: the result of ``pytest_command``.
    :param scratch: the directory ``command`` was built with.
    :return: 0 when pytest passes and measured code, otherwise 1.
    """
    returncode = subprocess.run(command, check=False).returncode

    if returncode not in (0, 1):
        return 1

    try:
        statements = json.loads((scratch / REPORT_NAME).read_text(encoding="utf-8"))["totals"]["num_statements"]
    except FileNotFoundError:
        statements = 0

    if statements == 0:
        print(
            "max-lint: coverage measured no files that contain statements; check 'coverage-source' and 'coverage-omit' in [tool.max-lint].",
            file=sys.stderr,
        )
        return 1

    return returncode
