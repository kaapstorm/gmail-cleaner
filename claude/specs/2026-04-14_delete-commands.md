# Design Spec: `delete-label` and `delete-query` Commands

## Overview

Two new destructive commands for permanently deleting Gmail messages.
Both share a common batch-delete mechanism with retry logic and
interactive confirmation. The Gmail API layer exposes a small public
surface (two functions per command) that internally orchestrates
service construction, pagination, and batched deletion.


## Gmail API Layer (`gmail.py`)

### Public functions

All public functions accept `creds: Credentials` (matching the
existing module style — e.g. `find_old_labels`, `search_messages`).
Each public call constructs the service internally so command code
never deals with `service` objects.

#### `scan_for_messages(creds, query) -> tuple[int, bool]`

Fetch the first page of `users.messages.list()` (with
`maxResults=500`) and return:

1. `estimate`: Gmail's `resultSizeEstimate` from the first page. This
   is Google's approximate count and is suitable only for display
   ("About N…"), never for control flow.
2. `has_results`: an authoritative boolean derived from the first
   page (`bool(messages) or 'nextPageToken' in response`). This rules
   out the case where `resultSizeEstimate` reports 0 but messages
   actually exist.

One `build_service` call, one list API call.

#### `delete_messages_matching(creds, query, *, on_progress) -> int`

Paginate `query` and delete in batches of 500 via
`users.messages.batchDelete()`. Returns the actual total number of
messages deleted.

Internally uses a generator (`_iter_message_ids`) so pagination and
deletion are pipelined: the next page is fetched only when the
current batch is drained into `batchDelete`. Re-fetches the first
page that `scan_for_messages` already saw — one wasted list call per
command, negligible vs. the work that follows.

- `on_progress(deleted_so_far)` is called after each successful batch.
  `delete_messages_matching` is display-agnostic. Callers that want
  to format running progress against an estimate use
  `functools.partial(_format_progress, estimate)` to bind the
  estimate before passing the callback in.
- An empty result set is a no-op (returns 0).
- One `build_service` call.

#### `find_label(creds, label_name) -> tuple[dict, int, bool] | None`

Look up a user label by name and return `(label, estimate,
has_messages)`, or `None` if no label with that name exists.
`estimate` and `has_messages` describe messages whose labels include
the looked-up label, computed by an internal `scan_for_messages` on
`label:{label_id}`.

One `build_service` call (label list + first-page scan share the
service).

#### `delete_label_completely(creds, label, *, on_progress) -> tuple[int, int]`

Delete all messages whose labels include `label`, then delete every
filter that adds `label` (any filter whose `action.addLabelIds`
contains the label ID), then delete the label itself. Returns
`(messages_deleted, filters_deleted)`.

- `on_progress(deleted_so_far)` is forwarded to the internal
  `_delete_message_batches` only during the message-deletion phase.
- One `build_service` call.

### Private helpers

The following are implementation details, kept as module-level
underscore-prefixed functions so they can be mocked in unit tests
without making them part of the public surface:

- `_iter_message_ids(service, query) -> Iterator[str]` — paginating
  generator using `users.messages.list` + `list_next`.
- `_delete_message_batches(service, ids, *, on_progress) -> int` —
  batches an iterable of IDs into groups of 500 and calls
  `users.messages.batchDelete` per batch with retry. Returns count
  deleted.
- `_with_retry(fn, *args, **kwargs)` — generic retry wrapper: 3
  attempts, sleeps of 2.5s and 5s between attempts. Retries on:
    - `HttpError` with `resp.status >= 500`
    - `HttpError` with `resp.status == 429` (rate limit)
    - `OSError` (covers network errors)
    - `TimeoutError`
  All other exceptions propagate immediately.
- `_list_filters(service) -> list[dict]` — wraps
  `users.settings.filters.list`.
- `_delete_filter(service, filter_id)` — wraps
  `users.settings.filters.delete` via `_with_retry`.
- `_delete_label_by_id(service, label_id)` — wraps
  `users.labels.delete` via `_with_retry`.
- `_list_user_labels(service)` — already exists; reused by
  `find_label`.

Existing public functions (`build_service`, `get_user_email`,
`find_old_labels`, `search_messages`, `get_message_headers`) remain
unchanged.


## `delete-label` Command

**File:** `gmail_cleaner/commands/delete_label.py`

### CLI Signature

```python
def delete_label(
    label_name: str = typer.Argument(
        ..., help='Name of the label to delete.',
    ),
    force: bool = typer.Option(
        False, '--force', help='Skip confirmation prompt.',
    ),
) -> None:
```

### Flow

1. Check auth (`load_token`), exit 1 if not logged in.
2. `result = gmail.find_label(creds, label_name)`. If `None`, print
   `Label '{label_name}' not found` and exit 1.
3. Unpack: `label, estimate, has_messages = result`.
4. Unless `--force`, show confirmation prompt:
   ```
   About 1,523 emails whose labels include 'MySpace' will be
   permanently deleted, along with filters for 'MySpace' and
   the 'MySpace' label.
   Proceed? [y/N]
   ```
   Use `typer.confirm(abort=True)`. Prompt always fires (including
   when `has_messages` is False) because filters and the label still
   get deleted.
5. Build progress callback: `on_progress = functools.partial(
   _format_progress, estimate)`.
6. `messages_deleted, filters_deleted = gmail.delete_label_completely(
   creds, label, on_progress=on_progress)`.
7. Print summary to stderr:
   `Deleted {messages_deleted} messages, {filters_deleted} filters, and label '{label_name}'.`


## `delete-query` Command

**File:** `gmail_cleaner/commands/delete_query.py`

### CLI Signature

```python
def delete_query(
    query: str = typer.Argument(
        ..., help='Gmail search query.',
    ),
    force: bool = typer.Option(
        False, '--force', help='Skip confirmation prompt.',
    ),
) -> None:
```

### Flow

1. Check auth (`load_token`), exit 1 if not logged in.
2. `estimate, has_results = gmail.scan_for_messages(creds, query)`.
3. If not `has_results`, print `No matching messages` and exit 0.
4. Unless `--force`, show confirmation prompt:
   ```
   Permanently delete about 1,523 emails matching '<query>'? [y/N]
   ```
   Use `typer.confirm(abort=True)`.
5. `on_progress = functools.partial(_format_progress, estimate)`.
6. `deleted = gmail.delete_messages_matching(creds, query, on_progress=on_progress)`.
7. Print summary to stderr: `Deleted {deleted} messages.`


## CLI Registration (`cli.py`)

Register both commands:

```python
app.command(help='Permanently delete a label, its filters, and all '
                 'emails it labels.')(delete_label)
app.command(help='Permanently delete all emails matching a Gmail '
                 'search query.')(delete_query)
```


## Shared Concerns

### Confirmation

Both commands use `typer.confirm()` with `abort=True`. The `--force`
flag bypasses the prompt. The prompt text includes Gmail's
approximate result count (from `scan_for_messages` / `find_label`),
prefixed with "About" or "about" to signal that the number is not
exact.

### Authoritative Zero-Match Detection

`resultSizeEstimate` is approximate — it can report 0 when results
exist, or > 0 when none do. `scan_for_messages` therefore returns a
separate authoritative `has_results` flag derived from the first
page (`bool(messages) or 'nextPageToken' in response`). `delete-query`
gates the early-exit on this flag rather than the estimate.
`delete-label` does not need an early exit (filters and label still
get deleted even when there are zero messages); its confirmation
prompt always fires.

### Progress Reporting

Both commands share a module-level formatter
`_format_progress(total_estimate, deleted)` in
`gmail_cleaner/commands/_progress.py`. It prints to stderr, e.g.
`Deleted 500 of ~1,523 messages...`. Each command pre-binds its
estimate using `functools.partial(_format_progress, estimate)` and
passes the resulting `on_progress(deleted)` callable to the deletion
function. The deletion function itself is display-agnostic. Final
summary lines use the actual count returned by the deletion
function.

### Lazy Iteration

The internal `_iter_message_ids` is a generator, so pagination and
deletion overlap: the next page is fetched only when the current
batch is drained into `batchDelete` calls. This overlaps list and
delete latency and avoids buffering hundreds of thousands of IDs in
memory.

### Retry

All deletion API calls (`batchDelete`, `filters.delete`,
`labels.delete`) go through `_with_retry`: 3 attempts total with
2.5s and 5s delays between retries. Retried exceptions are
`HttpError` with status >= 500 or status == 429 (rate limit),
`OSError`, and `TimeoutError`. All other exceptions propagate
immediately so programming bugs surface fast.

If all retries fail mid-deletion, the exception propagates. The user
can re-run the command to continue — already-deleted messages won't
be found again.

### Batch Sizes

- Pagination: 500 results per `users.messages.list()` page.
- Deletion: 500 IDs per `batchDelete` call.


## Testing

- Mock the Gmail API service at the gmail.py function level for
  command tests; mock the service object for gmail.py unit tests.
- Use `CliRunner(mix_stderr=False)` and assert against `result.stdout`
  / `result.stderr` explicitly. Errors and progress go to stderr;
  user-facing prompts and "not logged in" go to stdout.
- Use Python 3.10+ parenthesized context managers for stacked
  `with patch(...)` blocks. Where shared, lift to pytest-unmagic
  fixtures.
- A pytest-unmagic `no_sleep` fixture is opted in by retry tests to
  patch `time.sleep` to a no-op.

### Coverage

Required tests beyond happy paths:

- Retry succeeds on second attempt (5xx).
- Retry succeeds on second attempt (429 rate limit).
- Retry exhausted: all three attempts fail, exception propagates.
- Mid-pagination delete failure: batch 1 succeeds, batch 2 fails
  after retries — exception propagates, command surfaces the failure
  but already-deleted batch is gone.
- `_iter_message_ids` is lazy: assert the second `list` call does
  not happen until the generator is consumed past the first page.
- `delete-query` zero-match path: `has_results=False` → "No matching
  messages", exit 0, no confirmation, no deletion call.
- `delete-label` zero-message path: `has_messages=False` →
  confirmation still fires, message-deletion is a no-op, filters and
  label still get deleted.
- `delete-label` no-matching-filters: filter list contains filters
  but none reference the target label → 0 filters deleted, summary
  reflects 0.
- `delete-label` defensive filter shape: a filter without `action`
  or without `addLabelIds` is ignored (no `KeyError`).
- `delete-label` label-not-found path.
- "Not logged in" for both commands.
- Confirmation aborted (both commands).
- `--force` bypasses confirmation (both commands).


## Dependencies

No new runtime dependencies. The earlier `more-itertools` proposal
is dropped: with `has_results` returned authoritatively from
`scan_for_messages`, the `peekable` pattern is unnecessary.


## References

- [Gmail API `batchDelete`](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/batchDelete)
- [Gmail API `messages.list`](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/list)
- [Gmail API filters](https://developers.google.com/workspace/gmail/api/guides/filter_settings)
- [Bulk delete gist](https://gist.github.com/millerdev/0d65dafba0b866dfd81a77da996c6092)
