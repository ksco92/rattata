# Contributing

Bugs and proposals go in [GitHub issues](https://github.com/ksco92/rattata/issues).

## Set up

Requires Python 3.13 or newer and [uv](https://docs.astral.sh/uv/):

```sh
git clone https://github.com/ksco92/rattata
cd rattata
uv sync
```

## Check a change

The repository is checked by max-lint itself, configured by the `[tool.max-lint]` table in `pyproject.toml`.

```sh
uv run max-lint
uv run max-lint --check
```

`uv run max-lint` formats the files with black and isort, runs flake8, mypy and the tests with branch coverage, and fails under 95% coverage. `uv run max-lint --check` rewrites nothing and is what CI runs on Python 3.13 and 3.14; use `uv run --python 3.13 max-lint --check` to run it on one version.

## Rules

- The bundled style is not relaxed to make a change pass. Fix what the run reports in the code instead of adding `per-file-ignores`, `exclude`, `coverage-omit`, `# noqa`, `# type: ignore` or `# pragma: no cover`, and do not change a setting under `src/max_lint/style/` to get a change through.
- A change that alters behaviour comes with tests, and `uv run max-lint --check` passes before it is proposed.
