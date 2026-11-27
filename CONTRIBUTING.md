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

What each command does is under [Commands and exit codes](README.md#commands-and-exit-codes) in the README. CI runs `uv run max-lint --check` on Python 3.13 and 3.14; use `uv run --python 3.13 max-lint --check` to run it on one version.

## Rules

- The bundled style is not relaxed to make a change pass. Fix what the run reports in the code instead of adding `per-file-ignores`, `exclude`, `coverage-omit`, `# noqa`, `# type: ignore` or `# pragma: no cover`, and do not change a setting under `src/max_lint/style/` to get a change through.
- Tests are linted and type-checked like the package's own code, so every test function documents its parameters, return and raises.
- A change that alters behaviour comes with tests, and `uv run max-lint --check` passes before it is proposed.

## Release

A change that should be released bumps `version` in `pyproject.toml` and the matching entry in `uv.lock` (`uv lock` updates it). The version must have the form `X.Y.Z`; the publish workflow fails on anything else, such as `1.0.0rc1`. Merging it to `main` publishes that version to PyPI when PyPI does not have it yet; a merge that leaves the version unchanged publishes nothing.

A version bump comes with its section in [CHANGELOG.md](CHANGELOG.md), `## X.Y.Z (YYYY-MM-DD)` with the date of the merge, saying what the upgrade does to a project that uses max-lint; the publish workflow refuses to build a version that has no section. A merge that does not bump the version adds its line under a `## Unreleased` heading at the top of the file, and the next bump renames that heading to its version.

After the upload to PyPI, the publish workflow creates the annotated tag `vX.Y.Z` on the commit it built and the GitHub Release for it, with the version's changelog section as the notes. Tags and GitHub Releases are never created by hand.
