# max-lint

[![ci](https://github.com/ksco92/rattata/actions/workflows/ci.yml/badge.svg)](https://github.com/ksco92/rattata/actions/workflows/ci.yml)
[![PyPI version](https://img.shields.io/pypi/v/max-lint)](https://pypi.org/project/max-lint/)

**One command that runs black, isort, flake8, mypy and pytest with a single shared configuration. Every tool is pinned to an exact version.**

Status (November 2026): max-lint is published on PyPI. The `lint` command runs the formatters and linters with the bundled style, the `test` command runs pytest with branch coverage and a coverage floor, and a bare `max-lint` runs both.

## Contents

- [Install](#install)
- [Usage](#usage)
- [Configuration](#configuration)
- [Bundled style](#bundled-style)
- [Project mypy and pytest settings](#project-mypy-and-pytest-settings)
- [Commands and exit codes](#commands-and-exit-codes)
- [Known limitations](#known-limitations)
- [Contributing](#contributing)
- [License](#license)

## Install

Requires Python 3.13 or newer and [uv](https://docs.astral.sh/uv/). Add max-lint to a project as a development dependency, from a directory whose `pyproject.toml` has a `[project]` table with `name` and `version`:

```sh
uv add --dev max-lint
```

## Usage

A project declares what it owns in a `[tool.max-lint]` table of its `pyproject.toml`. Run the commands with `uv run` from the directory that holds `pyproject.toml`. This project, with max-lint added as above:

```toml
# pyproject.toml
[project]
name = "inventory"
version = "0.1.0"
requires-python = ">=3.13"

[tool.max-lint]
paths = ["src"]
test-paths = ["tests"]
coverage-source = ["src/inventory"]

[tool.pytest.ini_options]
pythonpath = ["src"]
```

```python
# src/inventory/__init__.py
"""Inventory tracking."""
```

```python
# src/inventory/stock.py
"""Stock levels per item."""


def restock(levels: dict[str, int], item: str, count: int) -> dict[str, int]:
    """
    Return a copy of ``levels`` with ``count`` more of ``item``.

    :param levels: current stock per item.
    :return: the updated stock.
    """
    return {**levels, item: levels.get(item, 0)+count}
```

```python
# tests/test_stock.py
"""Tests for stock levels."""

from inventory.stock import restock


def test_restock_adds_to_existing_item() -> None:
    """Restocking an item adds to its count."""
    assert restock({'apple': 1}, 'apple', 2) == {'apple': 3}
```

`max-lint lint --check` on the example; black lists its files in no fixed order:

```console
$ uv run max-lint lint --check
would reformat src/inventory/stock.py
would reformat tests/test_stock.py

Oh no! 💥 💔 💥
2 files would be reformatted, 1 file would be left unchanged.
```

`max-lint lint` rewrites the files and then reports what is left:

```console
$ uv run max-lint lint
reformatted src/inventory/stock.py
reformatted tests/test_stock.py

All done! ✨ 🍰 ✨
2 files reformatted, 1 file left unchanged.
src/inventory/stock.py:4:1: DOC101 Function `restock`: Docstring contains fewer arguments than in function signature.
src/inventory/stock.py:4:1: DOC103 Function `restock`: Docstring arguments are different from function arguments. (Or could be other formatting issues: https://jsh9.github.io/pydoclint/violation_codes.html#notes-on-doc103 ). Arguments in the function signature but not in the docstring: [count: int, item: str].
```

Once flake8 passes, mypy runs last. With `src/inventory/__init__.py` and `tests/test_stock.py` as the previous command left them, a completed `restock` docstring in `src/inventory/stock.py`:

```python
# src/inventory/stock.py
"""Stock levels per item."""


def restock(levels: dict[str, int], item: str, count: int) -> dict[str, int]:
    """
    Return a copy of ``levels`` with ``count`` more of ``item``.

    :param levels: current stock per item.
    :param item: the item to restock.
    :param count: how many to add.
    :return: the updated stock.
    """
    return {**levels, item: levels.get(item, 0) + count}
```

and a new module that passes a string where `restock` expects an int:

```python
# src/inventory/report.py
"""Stock report."""

from inventory.stock import restock


def weekly_delivery() -> dict[str, int]:
    """
    Return the stock after the weekly delivery.

    :return: the updated stock.
    """
    return restock({"apple": 1}, "apple", "3")
```

the same command ends in mypy:

```console
$ uv run max-lint lint
All done! ✨ 🍰 ✨
4 files left unchanged.
src/inventory/report.py:12: error: Argument 3 to "restock" has incompatible type "str"; expected "int"  [arg-type]
Found 1 error in 1 file (checked 4 source files)
```

`max-lint test` runs pytest over `test-paths` and measures `coverage-source` with branch coverage. Delete `src/inventory/report.py` from the example above, which leaves `stock.py` as completed there, and the tests pass:

```console
$ uv run max-lint test
============================= test session starts ==============================
platform <platform> -- Python <python>, pytest-<version>, pluggy-<version>
rootdir: <project>
configfile: pyproject.toml
plugins: platformdirs-<version>, cov-<version>, socket-<version>
collected 1 item

tests/test_stock.py .                                                    [100%]

================================ tests coverage ================================
_______________ coverage: platform <platform>, python <python-build> _______________

Name                        Stmts   Miss Branch BrPart    Cover   Missing
-------------------------------------------------------------------------
src/inventory/__init__.py       0      0      0      0  100.00%
src/inventory/stock.py          2      0      0      0  100.00%
-------------------------------------------------------------------------
TOTAL                           2      0      0      0  100.00%
Coverage JSON written to file <tmp>/coverage.json
Required test coverage of 95% reached. Total coverage: 100.00%
============================== 1 passed in <seconds>s ===============================
```

The output shows `<project>` for the project directory, `<tmp>` for a temporary directory, `<platform>` for the operating system, `<python>` for the Python version, `<python-build>` for the Python version with its release level, `<version>` for the version of the package named before it, and `<seconds>` for the run time. Coverage writes its data file, `.coverage`, to the project directory.

A bare `max-lint` on the example project as it was for the passing test run prints the lint tools' results first, followed by the pytest output shown above:

```console
$ uv run max-lint
All done! ✨ 🍰 ✨
3 files left unchanged.
Success: no issues found in 3 source files
```

## Configuration

The `[tool.max-lint]` table takes these keys and no others:

| Key | Type | Required | Meaning |
| --- | --- | --- | --- |
| `paths` | list of strings | yes | Source paths to format, lint and type-check; a file named `-` in the project root, listed here or in `test-paths`, stops `max-lint lint` and a bare `max-lint` with exit status 2, because black and flake8 read `-` as standard input. |
| `test-paths` | list of strings | no | Test paths: formatted, linted and type-checked like `paths`, and run by pytest, so the test step needs at least one. |
| `coverage-source` | list of strings | no | Packages or directories to measure, as pytest-cov's `--cov` takes them; the test step needs at least one. |
| `coverage-omit` | list of strings | no | Glob patterns of files to leave out of the measurement; one not starting with `*` is relative to `pyproject.toml`. |
| `exclude` | list of strings | no | Extra flake8-style exclude patterns such as `"src/inventory/generated"`, removed from every lint step alike. |
| `per-file-ignores` | table of glob to list of strings | no | Flake8 codes to ignore per file, such as `{ "src/inventory/legacy.py" = ["D103"] }`; a glob matches a file's path relative to `pyproject.toml`, and `*` also matches `/`. |

Every path in `paths` and `test-paths` must exist; paths are relative to `pyproject.toml` and may point outside its directory. Ignored codes add up per file: `D104` and `F401` for every `__init__.py`, and the codes of every `per-file-ignores` entry whose glob matches.

## Bundled style

The tools are add-trailing-comma, black, isort, flake8, mypy, pytest, pytest-cov, pytest-socket and coverage, each pinned to an exact version in [pyproject.toml](https://github.com/ksco92/rattata/blob/main/pyproject.toml). The flake8 plugins are flake8-annotations, flake8-docstrings, flake8-rst-docstrings, flake8-commas, flake8-multiline-containers and pydoclint.

- add-trailing-comma adds missing trailing commas in write mode; it has no settings, and no project file changes what it does.
- black and isort use line length 130, and isort uses `profile = "black"`. black targets the Python versions allowed by `requires-python`.
- flake8 selects `ANN401` in addition to its defaults and ignores `E203` and `E501`. pydoclint checks Sphinx-style docstrings without argument types in the docstring and skips private functions and return types.
- Docstrings are parsed with the `raw` and `include` directives disabled, so flake8 reports each use as `RST299`.
- mypy always runs with `disallow_untyped_defs`, `warn_redundant_casts`, `no_implicit_optional`, `disallow_any_unimported`, `disallow_any_generics`, `disallow_any_explicit` and `warn_return_any`.
- Coverage is branch coverage with a floor of 95% compared to two decimals, the missing lines shown, and `pragma: no cover` and `if __name__ == .__main__.:` as the excluded lines.
- pytest runs with `--import-mode=importlib`, and the current directory is importable, so a project that is not an installed package can import its own modules in its tests.

Settings for these tools in the project (`[tool.black]`, `[tool.isort]`, `.flake8`, `setup.cfg`, `tox.ini`, `.isort.cfg`, `[tool.coverage.*]`, `.coveragerc` and `.coveragerc.toml`) have no effect.

## Project mypy and pytest settings

mypy checks the files under `paths` and `test-paths`, the files the other lint steps check. Apart from the locked settings, it reads the `[tool.mypy]` table and the `[[tool.mypy.overrides]]` entries of the project's `pyproject.toml`, such as `python_version` and `plugins`; a project with no `[tool.mypy]` table works, and no other mypy configuration file (`mypy.ini`, `setup.cfg`) is read:

```toml
[tool.mypy]
python_version = "3.13"
```

A library without type information gets a stub package in the project's dev dependencies, such as `boto3-stubs` for boto3. A project that sets one of the locked settings in `[tool.mypy]` or in an override, under any name mypy accepts for it (`allow_untyped_defs`, for example), gets exit status 2 before any tool runs. mypy resolves third-party imports from the environment max-lint runs in, and writes its cache to `.mypy_cache` in the current directory. A plugin named by module must be importable from that environment because the working directory is not on the import path; a plugin given as a file path works. The project's `[tool.pytest.ini_options]` is read, so keys such as `pythonpath` work.

## Commands and exit codes

- `max-lint` runs the lint steps, then the test step; `max-lint --check` does the same with black and isort in their check modes.
- `max-lint lint` formats with black, adds missing trailing commas with add-trailing-comma, formats with black again and with isort, then runs flake8 and mypy; `max-lint lint --check` rewrites no files, skips add-trailing-comma and reports missing commas through flake8.
- `max-lint test` runs pytest with coverage.
- `max-lint --help` prints the available commands and `max-lint --version` the installed version.

Every command stops at the first step that fails. The exit status is 0 when every step passes and 1 when a tool reports a failure. The test step also exits 1 when coverage measures no file that contains a statement, even if every test passed. With `coverage-omit = ["src/inventory/stock.py"]` added to the example's `[tool.max-lint]`, the only file left in the measurement is the docstring-only `__init__.py`. The output is the same as in the passing run except that the `stock.py` row is gone, `TOTAL` counts no statements, and the last line is added:

```console
$ uv run max-lint test
src/inventory/__init__.py       0      0      0      0  100.00%
TOTAL                           0      0      0      0  100.00%
max-lint: coverage measured no files that contain statements; check 'coverage-source' and 'coverage-omit' in [tool.max-lint].
```

Exit status 2 and a one-line message on stderr mean a configuration error in `pyproject.toml` or its `[tool.max-lint]` table. The message says what to fix. A bare `max-lint` reports a configuration error of the test step before it rewrites any file. A usage error, such as an unknown command or option, also exits 2.

## Known limitations

- `max-lint test` and a bare `max-lint` run the project's tests, so the project's code, its `conftest.py` files and its pytest configuration execute. Coverage can be changed from inside that code, for example through the coverage API in a `conftest.py`.
- A project's `[tool.mypy]` table is trusted configuration. Plugins named there are loaded and run, and other settings there can make mypy write and read files outside the project and expand environment variables, so `max-lint lint` is not a read-only operation on a repository that has that table.
- A `coverage-source` entry that matches nothing only prints a coverage warning and does not fail the run while another entry measures code.
- Two directories under `paths` or `test-paths` that each hold a module of the same name without an `__init__.py`, such as `conftest.py` in `tests/unit` and `tests/integration`, make mypy report a duplicate module and the lint run fail; an `__init__.py` in each directory clears it.
- A file named like a library module that mypy uses, such as `typing_extensions.py` in the project root or a test directory, makes the mypy step fail.
- In an f-string or t-string, a call split over lines inside a replacement field keeps the `C812` for its missing comma, and so does a field whose closing `}` starts a line, including a nested format spec written that way; when add-trailing-comma adds a comma elsewhere in the file, it also rewrites a field holding a split call into that second shape. Put the field on one line.
- When add-trailing-comma's rewrite would change what the file means (a format spec, a field ending in `=`, a t-string) or would do anything but insert commas, such as removing the comma from `with (open("a") as f,):`, write mode leaves the whole file as it was and adds none of its other missing commas, and flake8 reports them. Write that `with` as `with open("a") as f:`, put the field on one line, or write `f"{x = }"` as `f"x = {x!r}"`.
- Write mode adds no trailing commas to a file that declares an encoding other than UTF-8, that has a bare carriage return (a `\r` with no line feed after it, as in old Mac line endings or one stray inside a comment) after black has run, that has a `# fmt: off`, `# fmt: skip` or `# yapf: disable` comment, or that cannot be opened for writing, and flake8 reports the missing commas in those files. In a file with a bare carriage return, replace each one with a line feed and write mode adds the commas. An error while writing a file stops the run with that error and can leave the file cut short. black stops the run before the comma step on a file it cannot decode, on a file it cannot read, and on a read-only file it would reformat.
- `max-lint --check test` accepts `--check` without effect: the tests run and no formatting is checked.

## Contributing

Setup, the checks a change must pass and the rules for the bundled style are in [CONTRIBUTING.md](https://github.com/ksco92/rattata/blob/main/CONTRIBUTING.md).
max-lint is maintained by Rodrigo Carvajal; bugs and proposals go in [GitHub issues](https://github.com/ksco92/rattata/issues).

## License

Apache-2.0. See [LICENSE](https://github.com/ksco92/rattata/blob/main/LICENSE) and [NOTICE](https://github.com/ksco92/rattata/blob/main/NOTICE).
