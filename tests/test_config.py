"""Tests for loading the [tool.max-lint] table."""

from pathlib import Path

import pytest

from max_lint.config import Config, ConfigError, load_config


def write_pyproject(root: Path, text: str) -> Path:
    """Write ``pyproject.toml`` under ``root`` with ``src`` and ``tests`` directories beside it."""
    (root / "src").mkdir()
    (root / "tests").mkdir()
    pyproject = root / "pyproject.toml"
    pyproject.write_text(text)

    return pyproject


def test_load_config_reads_every_key(tmp_path: Path) -> None:
    """A path may point outside the project directory."""
    (tmp_path / "shared").mkdir()
    project = tmp_path / "project"
    project.mkdir()
    pyproject = write_pyproject(
        project,
        """
[project]
requires-python = ">=3.12"

[tool.max-lint]
paths = ["src", "../shared"]
test-paths = ["tests"]
exclude = ["generated", "src/vendored/*"]
per-file-ignores = { "src/legacy/*" = ["D100", "D103"] }
""",
    )

    assert load_config(pyproject) == Config(
        paths=["src", "../shared"],
        test_paths=["tests"],
        exclude=["generated", "src/vendored/*"],
        per_file_ignores={"src/legacy/*": ["D100", "D103"]},
        black_target_versions=["py312", "py313", "py314", "py315"],
    )


def test_load_config_defaults_optional_keys(tmp_path: Path) -> None:
    """Without requires-python black gets no target version."""
    pyproject = write_pyproject(tmp_path, '[tool.max-lint]\npaths = ["src"]\n')

    assert load_config(pyproject) == Config(
        paths=["src"],
        test_paths=[],
        exclude=[],
        per_file_ignores={},
        black_target_versions=[],
    )


def test_load_config_without_pyproject_names_the_file(tmp_path: Path) -> None:
    """Point at a directory with no pyproject.toml."""
    with pytest.raises(ConfigError, match="pyproject.toml not found"):
        load_config(tmp_path / "pyproject.toml")


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("[tool.max-lint\n", "is not valid TOML"),
        ("[tool.black]\nline-length = 100\n", r"no \[tool.max-lint\] table"),
        ('[tool]\nmax-lint = ["src"]\n', r"no \[tool.max-lint\] table"),
        ('[tool.max-lint]\npaths = ["src"]\ncoverage-source = ["src"]\n', "unknown key 'coverage-source'"),
        ('[tool.max-lint]\ntest-paths = ["tests"]\n', "missing 'paths'"),
        ('[tool.max-lint]\npaths = "src"\n', "'paths' in .* must be a list of strings"),
        ("[tool.max-lint]\npaths = []\n", "'paths' in .* is empty"),
        ('[tool.max-lint]\npaths = ["src"]\ntest-paths = "tests"\n', "'test-paths' in .* must be a list of strings"),
        ('[tool.max-lint]\npaths = ["src"]\nexclude = ["build", 1]\n', "'exclude' in .* must be a list of strings"),
        ('[tool.max-lint]\npaths = ["src"]\nper-file-ignores = ["D100"]\n', "'per-file-ignores' in .* must be a table"),
        (
            '[tool.max-lint]\npaths = ["src"]\nper-file-ignores = { "a.py" = "D100" }\n',
            "'per-file-ignores' in .* must be a table",
        ),
        ('[tool.max-lint]\npaths = ["src", "lib"]\n', "'paths' in .* lists 'lib', which does not exist"),
        ('[tool.max-lint]\npaths = ["src"]\ntest-paths = ["test"]\n', "'test-paths' in .* lists 'test', which does not exist"),
    ],
)
def test_load_config_rejects_invalid_settings(tmp_path: Path, text: str, message: str) -> None:
    """Each message names the offending key or table."""
    pyproject = write_pyproject(tmp_path, text)

    with pytest.raises(ConfigError, match=message):
        load_config(pyproject)
