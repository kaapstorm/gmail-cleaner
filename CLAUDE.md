# Guidelines for Claude Code

## Tests

Tests use pytest and
[pytest-unmagic](https://github.com/kaapstorm/pytest-unmagic/tree/nh/docs_5/)

## Commands

The project uses a uv virtualenv. Prefix commands with `uv run ...` to
run commands in the virtualenv.

* Python: `uv run python3 ...`
* Run tests: `uv run pytest [path/to/file.py::TestClass::test_method]`
* Check typing: `uv run mypy [path/to/file.py`
* Check linting: `uv run ruff check`
* Sort imports: `uv run ruff check --select I --fix <path/to/file.py>`
* Format: `uv run ruff format <path/to/file.py>`

## Project structure

### Agent documentation

| Path                                   | Purpose              |
|----------------------------------------|----------------------|
| `claude/specs/YYYY-MM-DD_spec-name.md` | Design specs         |
| `claude/plans/YYYY-MM-DD_plan-name.md` | Implementation plans |
