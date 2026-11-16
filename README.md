# max-lint

**One command that runs black, isort, flake8, mypy and pytest with a single shared configuration. Every tool is pinned to an exact version.**

Status (November 2026): max-lint is not yet on PyPI. The `lint` command runs black, isort and flake8 with the bundled style; the mypy and pytest steps are not implemented yet.

## Install

Requires Python 3.13 or newer and [uv](https://docs.astral.sh/uv/). max-lint is developed in the `ksco92/rattata` repository:

```sh
git clone https://github.com/ksco92/rattata
cd rattata
uv sync
```

## Usage

A project declares what it owns in a `[tool.max-lint]` table of its `pyproject.toml`:

```toml
[project]
requires-python = ">=3.13"

[tool.max-lint]
paths = ["src", "../examples/quickstart"]
test-paths = ["tests"]
exclude = ["src/inventory/generated"]
per-file-ignores = { "src/inventory/legacy.py" = ["D103"] }
```

- `paths` (required): source paths. Paths are relative to `pyproject.toml` and may point outside its directory.
- `test-paths`: test paths, exempt from the pydoclint `DOC` codes.
- `exclude`: extra flake8-style exclude patterns, removed from black, isort and flake8 alike.
- `per-file-ignores`: path glob to a list of flake8 codes, added to the bundled `*/__init__.py: D104, F401`.

A missing table or `paths`, a value of the wrong type or an unknown key exits with status 2 and a one-line message naming the key.

Run the commands from the directory that holds `pyproject.toml`. Until max-lint is published, run it from a checkout with `uv run --project /path/to/rattata max-lint lint`.

`max-lint lint --check` runs black and isort in their check modes, then flake8, and writes nothing. It stops at the first step that fails:

```console
$ max-lint lint --check
would reformat src/inventory/stock.py
would reformat tests/test_stock.py

Oh no! 💥 💔 💥
2 files would be reformatted, 2 files would be left unchanged.
```

`max-lint lint` rewrites the files with black, then isort, then runs flake8:

```console
$ max-lint lint
reformatted src/inventory/stock.py
reformatted tests/test_stock.py

All done! ✨ 🍰 ✨
2 files reformatted, 2 files left unchanged.
src/inventory/stock.py:4:1: DOC101 Function `restock`: Docstring contains fewer arguments than in function signature.
src/inventory/stock.py:4:1: DOC103 Function `restock`: Docstring arguments are different from function arguments. (Or could be other formatting issues: https://jsh9.github.io/pydoclint/violation_codes.html#notes-on-doc103 ). Arguments in the function signature but not in the docstring: [count: int, item: str].
```

The exit status is 0 when every step passes and 1 when a tool reports a failure.

The style is bundled and fixed: line length 130 for black, isort (`profile = "black"`) and flake8, with flake8-annotations, flake8-docstrings, flake8-rst-docstrings, flake8-commas, flake8-multiline-containers and pydoclint (Sphinx style). black targets the Python versions allowed by `requires-python`. Settings for these tools in the project (`[tool.black]`, `[tool.isort]`, `.flake8`, `setup.cfg`, `tox.ini`, `.isort.cfg`) have no effect.

`max-lint --help` prints the available commands and `max-lint --version` the installed version.

## Contributing

Run the tests with branch coverage:

```sh
uv run pytest --cov=max_lint --cov-branch --cov-fail-under=95
```

Bugs and proposals go in [GitHub issues](https://github.com/ksco92/rattata/issues).

## License

Apache-2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
