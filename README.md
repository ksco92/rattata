# max-lint

**One command that runs black, isort, flake8, mypy and pytest with a single shared configuration. Every tool is pinned to an exact version.**

Status (November 2026): max-lint is not yet on PyPI. The `lint` command runs black, isort and flake8 with the bundled style; the mypy and pytest steps are not implemented yet.

## Contents

- [Install](#install)
- [Usage](#usage)
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
- `test-paths`: test paths, exempt from the pydoclint `DOC` codes.
- `exclude`: extra flake8-style exclude patterns such as `"src/inventory/generated"`, removed from black, isort and flake8 alike.
- `per-file-ignores`: a table of glob to flake8 codes, such as `{ "src/inventory/legacy.py" = ["D103"] }`. A glob matches a file's path relative to `pyproject.toml`, and `*` also matches `/`.

Every path in `paths` and `test-paths` must exist; paths are relative to `pyproject.toml` and may point outside its directory. Ignored codes add up per file: every `__init__.py` ignores `D104` and `F401`, every file under a test path ignores `DOC`, and every `per-file-ignores` entry whose glob matches adds its codes.

Exit status 2 and a one-line message on stderr mean a configuration error in `pyproject.toml` or its `[tool.max-lint]` table. The message says what to fix.

Run the commands from the directory that holds `pyproject.toml`. Until max-lint is published, run it from a checkout with `uv run --project /path/to/rattata max-lint lint`.

`max-lint lint --check` runs black and isort in their check modes, then flake8, and writes nothing. It stops at the first step that fails:

```console
$ max-lint lint --check
would reformat src/inventory/stock.py
would reformat tests/test_stock.py

Oh no! 💥 💔 💥
2 files would be reformatted, 1 file would be left unchanged.
```

`max-lint lint` rewrites the files with black, then isort, then runs flake8:

```console
$ max-lint lint
reformatted tests/test_stock.py
reformatted src/inventory/stock.py

All done! ✨ 🍰 ✨
2 files reformatted, 1 file left unchanged.
src/inventory/stock.py:4:1: DOC101 Function `restock`: Docstring contains fewer arguments than in function signature.
src/inventory/stock.py:4:1: DOC103 Function `restock`: Docstring arguments are different from function arguments. (Or could be other formatting issues: https://jsh9.github.io/pydoclint/violation_codes.html#notes-on-doc103 ). Arguments in the function signature but not in the docstring: [count: int, item: str].
```

The exit status is 0 when every step passes and 1 when a tool reports a failure.

The style is bundled and fixed: line length 130 for black and isort (`profile = "black"`), and flake8 with flake8-annotations, flake8-docstrings, flake8-rst-docstrings, flake8-commas, flake8-multiline-containers and pydoclint (Sphinx style). black targets the Python versions allowed by `requires-python`. Settings for these tools in the project (`[tool.black]`, `[tool.isort]`, `.flake8`, `setup.cfg`, `tox.ini`, `.isort.cfg`) have no effect. Docstrings are parsed with the `raw` and `include` directives disabled, so flake8 reports each use as `RST299`.

`max-lint --help` prints the available commands and `max-lint --version` the installed version.

## Contributing

Run the tests with branch coverage:

```sh
uv run pytest --cov=max_lint --cov-branch --cov-fail-under=95
```

Bugs and proposals go in [GitHub issues](https://github.com/ksco92/rattata/issues).

## License

Apache-2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
