# Guidelines for Claude Code

## Tests

Tests use pytest and
[pytest-unmagic](https://github.com/kaapstorm/pytest-unmagic/tree/nh/docs_5/)

Use pytest's parametrized tests to deduplicate tests that have the same
structure.

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
* Run tests: `uv run pytest [path/to/file.py::TestClass::test_method]`
* Check typing: `uv run mypy [path/to/file.py`
* Check linting: `uv run ruff check`
* Sort imports: `uv run ruff check --select I --fix <path/to/file.py>`
* Format: `uv run ruff format <path/to/file.py>`

## Project structure

### Specs and plans

| Path                                   | Purpose              |
|----------------------------------------|----------------------|
| `claude/specs/YYYY-MM-DD_spec-name.md` | Design specs         |
| `claude/plans/YYYY-MM-DD_plan-name.md` | Implementation plans |
