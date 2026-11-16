# max-lint

**One command that runs black, isort, flake8, mypy and pytest with a single shared configuration. Every tool is pinned to an exact version, so the same code gets the same verdict in every repository that uses it.**

Status (November 2026): max-lint is not yet on PyPI. The installable package and its `--version` command exist; the lint, type-check and test steps are not implemented yet.

## Install

Requires Python 3.13 or newer. From a clone of this repository:

```sh
uv sync
```

## Usage

```sh
uv run max-lint --version
uv run max-lint --help
```

## Contributing

Run the tests with branch coverage:

```sh
uv run pytest --cov=max_lint --cov-branch --cov-fail-under=95
```

Bugs and proposals go in [GitHub issues](https://github.com/ksco92/rattata/issues).

## License

Apache-2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
