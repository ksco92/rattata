# max-lint

**One command that runs black, isort, flake8, mypy and pytest with a single shared configuration. Every tool is pinned to an exact version.**

Status (November 2026): max-lint is not yet on PyPI. The `lint` command runs black, isort, flake8 and mypy with the bundled style, the `test` command runs pytest with branch coverage and a 95% floor, and a bare `max-lint` runs both.

## Contents

- [Install](#install)
- [Usage](#usage)
- [Known limitations](#known-limitations)
- [Contributing](#contributing)
- [License](#license)

## Install

Requires Python 3.13 or newer and [uv](https://docs.astral.sh/uv/). max-lint is developed in the `ksco92/rattata` repository:

```sh
git clone https://github.com/ksco92/rattata
cd rattata
uv sync
```

## Usage

A project declares what it owns in a `[tool.max-lint]` table of its `pyproject.toml`. This project:

```toml
# pyproject.toml
[project]
name = "inventory"
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

The table takes these keys:

- `paths` (required): source paths.
- `test-paths`: test paths, exempt from the pydoclint `DOC` codes. These are also the paths pytest runs, so the test step needs at least one.
- `coverage-source`: packages or directories to measure, as pytest-cov's `--cov` takes them; directories are relative to `pyproject.toml`. The test step needs at least one.
- `coverage-omit`: glob patterns of files to leave out of the measurement. A pattern that does not start with `*` is relative to `pyproject.toml`.
- `exclude`: extra flake8-style exclude patterns such as `"src/inventory/generated"`, removed from black, isort and flake8 alike.
- `per-file-ignores`: a table of glob to flake8 codes, such as `{ "src/inventory/legacy.py" = ["D103"] }`. A glob matches a file's path relative to `pyproject.toml`, and `*` also matches `/`.

Every path in `paths` and `test-paths` must exist; paths are relative to `pyproject.toml` and may point outside its directory. Ignored codes add up per file: every `__init__.py` ignores `D104` and `F401`, every file under a test path ignores `DOC`, and every `per-file-ignores` entry whose glob matches adds its codes.

Exit status 2 and a one-line message on stderr mean a configuration error in `pyproject.toml` or its `[tool.max-lint]` table. The message says what to fix. This includes an empty `test-paths` or a missing `coverage-source` when the test step is going to run; a bare `max-lint` reports it before it rewrites any file.

Run the commands from the directory that holds `pyproject.toml`. Until max-lint is published, run it from a checkout with `uv run --project /path/to/rattata max-lint`.

`max-lint lint --check` runs black and isort in their check modes, then flake8 and mypy, and rewrites no files. It stops at the first step that fails:

```console
$ max-lint lint --check
would reformat src/inventory/stock.py
would reformat tests/test_stock.py

Oh no! 💥 💔 💥
2 files would be reformatted, 1 file would be left unchanged.
```

`max-lint lint` rewrites the files with black, then isort, then runs flake8 and mypy:

```console
$ max-lint lint
reformatted tests/test_stock.py
reformatted src/inventory/stock.py

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
$ max-lint lint
All done! ✨ 🍰 ✨
4 files left unchanged.
src/inventory/report.py:12: error: Argument 3 to "restock" has incompatible type "str"; expected "int"  [arg-type]
Found 1 error in 1 file (checked 3 source files)
```

The exit status is 0 when every step passes and 1 when a tool reports a failure.

`max-lint test` runs pytest over `test-paths` and measures `coverage-source` with branch coverage. The terminal report lists the missing lines, and the step fails when total coverage is under 95%. pytest runs from the current directory, which is importable, so a project that is not an installed package can import its own modules in its tests. Delete `src/inventory/report.py` from the example above, which leaves `stock.py` as completed there, and the tests pass:

```console
$ max-lint test
============================= test session starts ==============================
platform <platform> -- Python <python>, pytest-9.2.0, pluggy-<version>
rootdir: <project>
configfile: pyproject.toml
plugins: platformdirs-<version>, cov-7.1.0, socket-0.8.1
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

The output shows `<project>` for the project directory, `<tmp>` for a temporary directory, `<platform>` for the operating system, `<python>` for the Python version, `<python-build>` for the Python version with its release level, `<version>` for the versions of `pluggy` and `platformdirs`, and `<seconds>` for the run time; everything else is as printed. The `Coverage JSON written` line names a report in a temporary directory that max-lint reads to find out whether anything was measured. Coverage writes its data file, `.coverage`, to the project directory.

The coverage settings are fixed: branch coverage on, a floor of 95% compared to two decimals, the missing lines shown, and `pragma: no cover` and `if __name__ == .__main__.:` as the excluded lines. `[tool.coverage.*]`, `.coveragerc`, `.coveragerc.toml` and the coverage sections of `setup.cfg` and `tox.ini` have no effect. The project's `[tool.pytest.ini_options]` is still read, so keys such as `pythonpath` work; pytest runs with `--import-mode=importlib`.

When coverage measures no file that contains a statement, the step exits 1 even though every test passed. With `coverage-omit = ["src/inventory/stock.py"]` added to `[tool.max-lint]`, the only file left in the measurement is the docstring-only `__init__.py`. The output is the same as above except that the `stock.py` row is gone, `TOTAL` counts no statements, and the last line is added:

```console
$ max-lint test
src/inventory/__init__.py       0      0      0      0  100.00%
TOTAL                           0      0      0      0  100.00%
max-lint: coverage measured no files that contain statements; check 'coverage-source' and 'coverage-omit' in [tool.max-lint].
```

`max-lint` with no command runs the lint steps, then the test step, and stops at the first step that fails; `max-lint --check` does the same with black and isort in their check modes. On the example project as it was for the passing test run, the lint tools print their results first, followed by the pytest output shown above:

```console
$ max-lint
All done! ✨ 🍰 ✨
3 files left unchanged.
Success: no issues found in 2 source files
```

The style is bundled and fixed: line length 130 for black and isort (`profile = "black"`), and flake8 with flake8-annotations, flake8-docstrings, flake8-rst-docstrings, flake8-commas, flake8-multiline-containers and pydoclint (Sphinx style). black targets the Python versions allowed by `requires-python`. Settings for these tools in the project (`[tool.black]`, `[tool.isort]`, `.flake8`, `setup.cfg`, `tox.ini`, `.isort.cfg`) have no effect. Docstrings are parsed with the `raw` and `include` directives disabled, so flake8 reports each use as `RST299`.

mypy checks the files under `paths` only, so test code is not type-checked unless a `paths` entry also covers it. It always runs with `disallow_untyped_defs`, `warn_redundant_casts` and `no_implicit_optional`. For everything else it reads the `[tool.mypy]` table and the `[[tool.mypy.overrides]]` entries of the project's `pyproject.toml`, such as `python_version`, `plugins` and per-module `ignore_missing_imports`; a project with no `[tool.mypy]` table works, and no other mypy configuration file (`mypy.ini`, `setup.cfg`) is read:

```toml
[tool.mypy]
python_version = "3.13"

[[tool.mypy.overrides]]
module = ["legacy_sdk.*"]
ignore_missing_imports = true
```

A project that sets one of the three locked settings in `[tool.mypy]` or in an override, under any name mypy accepts for it (`allow_untyped_defs`, for example), gets exit status 2 before any tool runs. mypy resolves third-party imports from the environment max-lint runs in, and writes its cache to `.mypy_cache` in the current directory. A plugin named by module must be importable from that environment because the working directory is not on the import path; a plugin given as a file path works.

`max-lint --help` prints the available commands and `max-lint --version` the installed version.

## Known limitations

- `max-lint test` and a bare `max-lint` run the project's tests, so the project's code, its `conftest.py` files and its pytest configuration execute. Coverage can be changed from inside that code, for example through the coverage API in a `conftest.py`.
- A project's `[tool.mypy]` table is trusted configuration. Plugins named there are loaded and run, and other settings there can make mypy write and read files outside the project and expand environment variables, so `max-lint lint` is not a read-only operation on a repository that has that table.

## Contributing

Run the tests with branch coverage:

```sh
uv run pytest --cov=max_lint --cov-branch --cov-fail-under=95
```

Bugs and proposals go in [GitHub issues](https://github.com/ksco92/rattata/issues).

## License

Apache-2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
