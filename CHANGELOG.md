# Changelog

What each release of max-lint changes in a project that uses it. The bundled style and the tool versions are part of the package, so a release can add findings or rewrite files; read every section between the version a project has and the one it moves to.

## 0.13.0 (2026-11-27)

- For `MXL009` to `MXL012`, a test file is now a file listed in `test-paths` or under a directory listed there, whatever its name. A file named `test_*.py`, `*_test.py` or `conftest.py`, or under a directory named `tests` or `test`, that is outside `test-paths` now gets `MXL009` and loses `MXL010` to `MXL012`; a file under `test-paths` with any other name now gets `MXL010` to `MXL012` and no longer gets `MXL009`. flake8 run directly, without max-lint, treats no file as a test file.

## 0.12.0 (2026-11-27)

- `max-lint test` and a bare `max-lint` run pytest with pytest-socket's `--disable-socket --allow-unix-socket`, so a test that creates a network socket with `socket.socket` now fails with `SocketBlockedError`. `@pytest.mark.enable_socket` lifts the block for one test; `addopts = "--allow-hosts=127.0.0.1"` in `[tool.pytest.ini_options]` lifts it for every test and only makes `connect()` to another host fail.

## 0.11.2 (2026-11-27)

- Nothing changes in what max-lint checks, rewrites or reports.

## 0.11.1 (2026-11-27)

- Nothing changes in what max-lint checks, rewrites or reports.
- The PyPI project page links this changelog.

## 0.11.0 (2026-11-25)

- flake8 runs a bundled `MXL` plugin on every linted file, with these new findings:
  - `MXL001`: an import of a deprecated `typing` alias, such as `List`, `Dict`, `Optional`, `Union` or `Callable`; use the builtin generic, `X | Y` or `collections.abc`.
  - `MXL002`: a module docstring longer than 10 lines.
  - `MXL003`: an `except` clause that names a tuple of exceptions; write one clause per exception.
  - `MXL004`: a bare `except:`, `except Exception:` or `except BaseException:` whose body is only `pass` or `...`.
  - `MXL005`: a file of 20 or more non-blank lines in which comment and docstring prose is more than 40% of them; Sphinx fields, docstring delimiters and doctests are not counted as prose.
  - `MXL006`: `raise NotImplementedError` or `raise NotImplementedError()` without a message.
  - `MXL007`: a block nested more than 4 levels deep inside a function; an `elif` does not add a level.
  - `MXL008`: a comment or docstring that documents an absence, such as `:raises: none` or `# Panics: never`.
  - `MXL009`: a `TODO`, `FIXME`, `XXX` or `HACK` comment outside test files.
  - In test files only: `MXL010` for importing `unittest` or one of its modules other than `unittest.mock`, and for a class whose name starts with `Test`; `MXL011` for a `@patch` decorator, to be replaced with `with patch(...)`; `MXL012` for importing a sibling `test_` module.
- A file counts as a test file for `MXL009` to `MXL012` when its name is `test_*`, `*_test.py` or `conftest.py`, or when a directory in its path relative to the project directory is named `tests` or `test`. `test-paths` does not decide this.
- pydoclint checks private functions, those whose name starts with `_`, like public ones, so their docstrings now need the `:param:`, `:return:` and `:raises:` fields public functions need.
- pydoclint no longer checks yield types.

## 0.10.0 (2026-11-17)

- Coverage leaves `if TYPE_CHECKING:` and `if typing.TYPE_CHECKING:` blocks out of the measurement, so imports made only for the type checker no longer count as missed lines or branches, and the reported coverage can rise.

## 0.9.2 (2026-11-17)

- Nothing changes in what max-lint checks, rewrites or reports.

## 0.9.1 (2026-11-17)

- A file named `-` in the project root, listed in `paths` or `test-paths`, now stops `max-lint lint` and a bare `max-lint` with exit status 2 and a message to rename it, because black and flake8 read `-` as standard input.

## 0.9.0 (2026-11-17)

- New dependency: add-trailing-comma 4.0.0, which brings tokenize-rt.
- `max-lint lint` and a bare `max-lint` add missing trailing commas: they run black, add-trailing-comma, black again and isort. The first run after the upgrade can rewrite files that black alone left as they were.
- A rewrite is kept only when it inserts commas and leaves the file's syntax tree unchanged. A file that declares an encoding other than UTF-8, has a bare carriage return, has a `# fmt: off`, `# fmt: skip` or `# yapf: disable` comment, or cannot be opened for writing is left as it was, and flake8 still reports its missing commas.
- The `--check` modes do not run add-trailing-comma and write nothing; missing commas are reported by flake8 as before.

## 0.8.0 (2026-11-16)

- Files under `test-paths` are type-checked by mypy with the same locked settings as `paths`, so tests can get new mypy errors.
- Files under `test-paths` are no longer exempt from the pydoclint `DOC` codes, so a test function's docstring needs the `:param:`, `:return:` and `:raises:` fields that apply to it, such as one `:param:` per fixture.
- Two directories under `paths` or `test-paths` that each hold a module of the same name without an `__init__.py`, such as `conftest.py` in `tests/unit` and `tests/integration`, make mypy report a duplicate module and the lint run fail; an `__init__.py` in each directory clears it.

## 0.7.0 (2026-11-16)

- mypy always runs with four more settings: `disallow_any_unimported`, `disallow_any_generics`, `disallow_any_explicit` and `warn_return_any`. Expect new errors for an explicit `Any`, a generic such as `list` or `dict` without type arguments, a function that returns `Any` where its annotation promises a type, and an annotation that uses a type from a module mypy cannot analyse.
- A project that sets one of these four, or its opposite such as `allow_any_generics` or `no_warn_return_any`, in `[tool.mypy]` or in an override gets exit status 2 before any tool runs.
- For a library without type information, the README recommends adding its stub package to the project's dev dependencies, such as `boto3-stubs` for boto3, instead of an `ignore_missing_imports` override.

## 0.6.1 (2026-11-16)

- Nothing changes for a project that uses max-lint.

## 0.6.0 (2026-11-16)

- First version on PyPI. Add it to a project with `uv add --dev max-lint`, from a directory whose `pyproject.toml` has a `[project]` table with `name` and `version`, and run it with `uv run max-lint`. Earlier versions were run from a clone of the repository.
