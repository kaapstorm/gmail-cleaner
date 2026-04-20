# Spec: Filter management commands

## Motivation

The tool's goal is to let Claude curate a user's Gmail so only important
and actionable mail lands in the inbox. Claude already has `export-inbox`
to produce a JSONL snapshot of current inbox contents, but has no way to
act on what it learns: it cannot inspect, add, or remove Gmail filters.

This spec adds CRUD primitives for Gmail filters so Claude can read
existing filters, propose changes based on an inbox export, and apply
them through the same CLI.

The `normalize-filters` entry on the roadmap is superseded by this work.

## Scope

Three new commands:

- `gmc list-filters [--id ID]`
- `gmc create-filter <path>`
- `gmc delete-filter <id> [<id>...]`

No `edit-filter`. Gmail treats edit as delete-then-create (the filter ID
changes), and Claude can orchestrate the two explicit calls. One wrapper
command would only hide the non-atomicity.

No `apply`/reconcile command. A declarative diff layer adds complexity
without benefit when Claude is the primary caller.

Out of scope:

- LLM-based suggestion logic. Claude runs that in its own context,
  reading `export-inbox` output and `list-filters` output, then emitting
  a JSON file for `create-filter`.
- Filter schema validation beyond what Gmail's API already enforces.
- Any UI beyond the CLI.

Also in scope as a follow-up cleanup: normalize `export-inbox` to use
`-` as the stdout sentinel instead of `--`.

## Command behavior

### `list-filters`

```
gmc list-filters [--id ID]
```

Prints Gmail filter resources to stdout as JSONL: one filter per line,
each line a compact JSON object with the full filter (`id`, `criteria`,
`action`) as returned by the Gmail API. Matches the format used by
`export-inbox`.

- With no `--id`, lists all filters. An empty result is empty output
  (zero lines).
- With `--id ID`, emits a single line for that filter. If the ID does
  not exist, exits non-zero with an error on stderr.

### `create-filter`

```
gmc create-filter <path>
```

Reads JSONL from `<path>`, or from stdin if `<path>` is `-`: one filter
object per line. Blank lines are ignored. Input filters MUST NOT
include an `id` field — Gmail assigns IDs on creation.

Creates each filter sequentially via the Gmail API. Prints the created
filters (each with its new `id`) to stdout as JSONL, one per line,
matching the `list-filters` format for clean round-tripping.

If the API rejects an element mid-batch, the command prints the
already-created filters (one JSONL line each) to stdout, prints the
error to stderr, and exits non-zero. No rollback is attempted: Gmail filter creation is not
transactional, and partial state is recoverable by the caller via
`list-filters` + `delete-filter`.

### `delete-filter`

```
gmc delete-filter <id> [<id>...]
```

Deletes one or more filters by ID. For each ID:

- Prints `deleted <id>` to stderr on success.
- Prints `not found <id>` to stderr if the API returns 404.
- Continues on 404; re-raises on any other error.

Exit code is 0 if every ID was either deleted or already missing; it is
non-zero only on unexpected errors.

## File format

All filter I/O uses JSONL — one filter object per line — matching
`export-inbox`. No YAML; no new dependency. Claude is the primary
editor of these files and JSONL round-trips cleanly between
`list-filters` and `create-filter`.

## Module structure

The existing codebase separates concerns as follows:

- `gmail_cleaner/gmail.py` — low-level Gmail API wrappers that take a
  `Service` handle. Private by default (underscore prefix).
- `gmail_cleaner/cleanup.py` — higher-level operations that take
  `Credentials`, build the service internally, and orchestrate multiple
  wrappers into a cohesive task. Return `NamedTuple` results.
- `gmail_cleaner/commands/*.py` — CLI layer. Parses args, loads creds,
  calls a higher-level operation, writes output. Never touches
  `Service`.

Currently `_list_filters` and `_delete_filter` live in `cleanup.py` as
private helpers used by `delete_label_completely`. That is the wrong
home: they are generic API wrappers, not cleanup-specific.

Changes:

1. **`gmail_cleaner/gmail.py`** — promote `_list_filters` and
   `_delete_filter` here. Add `_create_filter(service, filter_dict) ->
   dict` and `_get_filter(service, filter_id) -> dict`.
2. **`gmail_cleaner/filters.py`** (new) — higher-level operations:
   - `list_filters(creds, filter_id=None) -> list[dict]`
   - `create_filters(creds, filter_dicts: list[dict]) -> list[dict]`
     (returns created filters with IDs; on API error, raises after the
     partial result is recoverable — see Error handling)
   - `delete_filters(creds, filter_ids: list[str]) -> DeleteResult`
     where `DeleteResult` is a `NamedTuple(deleted: int, missing:
     list[str])`.
3. **`gmail_cleaner/cleanup.py`** — replace its private helpers with
   imports from `gmail.py`. Move the commit that does this separately
   from any behavior change.
4. **`gmail_cleaner/commands/list_filters.py`**,
   **`create_filter.py`**, **`delete_filter.py`** — new thin CLI
   modules, following the pattern of existing commands.
5. **`gmail_cleaner/cli.py`** — register the three new subcommands.

## Error handling

- **`list-filters`**: not-found on `--id` exits non-zero with a clear
  stderr message. Transport errors propagate via the existing
  `_with_retry` path in `gmail.py`.
- **`create-filter`**: on API error mid-batch, the `filters.py` function
  raises a custom exception carrying `(created: list[dict], error:
  Exception)`. The command prints already-created filters to stdout,
  prints the error to stderr, exits non-zero. This lets Claude see
  exactly what was committed before the failure.
- **`delete-filter`**: 404 is expected and tolerated (reported as
  `missing`). Any other `HttpError` propagates.

## Testing

Follow the existing pattern in `tests/`:

- **`tests/test_filters.py`** — unit tests for
  `filters.list_filters/create_filters/delete_filters`. Mock the Gmail
  service using the existing fixture approach (check `tests/fixtures.py`
  and reuse). Parametrize create-filter tests over single-line and
  multi-line JSONL input to dedupe shape-equivalent cases.
- **`tests/commands/test_list_filters.py`**,
  **`test_create_filter.py`**, **`test_delete_filter.py`** — CLI tests:
  invoke the Typer app, assert stdout content (parsed line-by-line as
  JSONL), stderr content, and exit codes. Cover:
  - `list-filters` empty, populated, and `--id` hit/miss.
  - `create-filter` single-line, multi-line, stdin (`-`), blank-line
    tolerance, and mid-batch failure.
  - `delete-filter` single, multiple, all-missing, mixed success/miss.
- **`tests/test_cleanup.py`** — existing tests should still pass after
  the `_list_filters`/`_delete_filter` promotion; adjust imports only.

## Follow-up: `export-inbox` stdout sentinel

Bring `export-inbox` in line with the `-` convention used by
`create-filter`:

- `gmail_cleaner/commands/export_inbox.py`: change `STDOUT_MARKER =
  '--'` to `'-'`, update the `help=` text for the `output` argument,
  and delete the multi-line comment explaining the Click `--`
  semantics (no longer relevant).
- `README.md`: replace the `gmc export-inbox -- -- | jq …` example
  with `gmc export-inbox - | jq …`; update the accompanying prose.
- `tests/commands/test_export_inbox.py`: update stdout-sentinel
  cases from `'--'` to `'-'`.

This is a breaking change for the CLI, but the project is pre-release
with a single user — no compatibility shim.

## Non-goals

- No automatic suggestion engine. Claude does the reasoning.
- No rollback on partial `create-filter` failure.
- No declarative `apply` / reconcile command.
- No filter-schema validation beyond what Gmail enforces server-side.
