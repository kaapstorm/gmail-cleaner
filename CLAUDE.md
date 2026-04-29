# Guidelines for Claude Code

## Tests

Tests use [testsweet](https://github.com/kaapstorm/testsweet). Mark each
test function with `@test`; test files don't need a `test_` prefix.

Use `@test_params([...])` to deduplicate tests that have the same
structure.

Use `catch_exceptions()` to assert that a block raises — capture the
exception in the yielded list and check `type(excs[0]) is X`.

For setup/teardown, use plain context managers (`with
tempfile.TemporaryDirectory()`, `with patch(...)`) inline in the test —
testsweet has no fixture system.

## Type hints

Type hints here are documentation. Include them when the type itself
conveys something the name doesn't — e.g. a custom type alias, a
`Union`, or a non-obvious structure. Omit them when the type is clear
from context (e.g. `count: int`, `name: str`). Prioritize a better name
over a type hint.

## Keep it clean

Before editing a Python module, format it with `ruff` and sort imports.
If there are changes, commit them. After your edits, format with ruff
and sort imports again before committing.

Commit moves and renames separate from changes, so that the diff of the
changes is clear.

## Formatting

Items in lists, tuples, dicts, and parameters, that are formatted on
their own line should end with a comma, e.g.
```python
def do_something(
    param1: str, param2: int, param3: bool,
    # ^^^ params on their own line end with `,`
) -> None:
    foo = {
        'one': 1, 'two': 2, 'three': 3,
        # ^^^ items on their own line end with `,`
    }

def do_something_else(param1, param2, param3):  # share a line, no comma
    bar = {'one': 1, 'two': 2, 'three': 3}  # share a line, no comma
```
The reason for this is that `ruff` will break the items onto their own
lines.

## Commands

The project uses a uv virtualenv. Prefix commands with `uv run ...` to
run commands in the virtualenv.

* Python: `uv run python3 ...`
* Run tests: `uv run python -m testsweet [path/to/file.py]`
* Check typing: `uv run mypy gmail_cleaner/ tests/`
* Check linting: `uv run ruff check`
* Sort imports: `uv run ruff check --select I --fix <path/to/file.py>`
* Format: `uv run ruff format <path/to/file.py>`

## Project structure

### Code layers

Three layers, each with a distinct responsibility. Keep new code in
the layer that matches its job; don't collapse them.

| Layer                                              | Responsibility                                                                                                                                                                                     |
|----------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `gmail_cleaner/gmail.py`                           | Thin wrappers over the Gmail API: `build_service`, `with_retry`, paginated iterators (`iter_message_ids`), and per-resource CRUD (`list_filters`, `create_label`, etc.). No business logic, no UX. |
| `gmail_cleaner/{cleanup,export,filters,labels}.py` | Business logic that composes `gmail.py` primitives. Takes `Credentials` + plain args; returns `NamedTuple`s or iterators. No `typer`, no stdout/stderr, no prompts.                                |
| `gmail_cleaner/commands/*.py`                      | Typer CLI entry points. Parse args, load creds, handle `--dry-run`/`--force` UX, print output and progress, then delegate to the logic layer. One file per subcommand.                             |

When adding a new command:
1. Add the primitive to `gmail.py` if the Gmail API call doesn't exist there yet.
2. Add the logic function (returning data, not printing) to the appropriate `*.py` module — or create a new one if it's a distinct concern.
3. Add a `commands/<name>.py` that wires argument parsing and UX to the logic function, and register it in `cli.py`.
4. Add tests for each layer in the matching `tests/` location.

### Specs and plans

| Path                                   | Purpose              |
|----------------------------------------|----------------------|
| `claude/specs/YYYY-MM-DD_spec-name.md` | Design specs         |
| `claude/plans/YYYY-MM-DD_plan-name.md` | Implementation plans |
