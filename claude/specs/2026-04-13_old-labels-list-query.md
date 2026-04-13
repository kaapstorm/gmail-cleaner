# Design: `old-labels` and `list-query` commands

## Overview

Implement the next two commands in the roadmap:

- `old-labels` — list user-created labels whose most recent message is
  older than a given age. Output feeds the `delete-label` workflow.
- `list-query` — preview the count and first 10 messages matching a
  Gmail search query. Used to sanity-check a query before passing it to
  `delete-query`.

Both commands build on the credential and Gmail-service foundation
established by `login` / `whoami` / `logout`.


## File structure

```
gmail_cleaner/
  commands/
    old_labels.py
    list_query.py
  gmail.py                 # extended with new helpers
tests/
  commands/
    test_old_labels.py
    test_list_query.py
  test_gmail.py            # extended
```

`cli.py` registers the two new commands. Typer maps the underscored
function names (`old_labels`, `list_query`) to hyphenated CLI commands
(`old-labels`, `list-query`), matching the README.

No new dependencies.


## `gmail.py` additions

Each helper does exactly one Gmail API call. Commands compose them.

```python
def list_user_labels(creds: Credentials) -> list[dict]:
    """Return labels where type == 'user', sorted by name."""

def label_has_recent_message(
    creds: Credentials, label_id: str, age: str
) -> bool:
    """True if any message with this label is newer than `age`.

    Uses labelIds=[label_id] and q=f'newer_than:{age}', maxResults=1.
    Passing the label ID (not name) sidesteps quoting issues for label
    names containing spaces.
    """

def search_messages(
    creds: Credentials, query: str, *, max_results: int
) -> tuple[list[str], int]:
    """One messages.list call. Returns (message_ids, resultSizeEstimate)."""

def get_message_headers(
    creds: Credentials, message_id: str
) -> dict[str, str]:
    """Return the Date, From, and Subject headers for a message.

    Uses format='metadata' with metadataHeaders=['Date', 'From', 'Subject']
    so the API only returns what we need.
    """
```


## Commands

### `old-labels`

**Signature**

```python
def old_labels(
    age: str = typer.Option(
        '2y',
        help='Maximum age of the most recent message for a label to be '
             'considered old. Format: <number><d|m|y>.',
        callback=_validate_age,
    ),
) -> None:
```

**Validation** — `--age` must match `^\d+[dmy]$` (e.g. `30d`, `6m`, `2y`).
On mismatch, raise `typer.BadParameter('must look like 30d, 6m, or 2y')`.
The format mirrors Gmail's `newer_than:` syntax; the value is passed
through unchanged.

**Behaviour**

1. Call `auth.load_token()`. If `None`, print `'Not logged in'` to
   stdout and exit 1.
2. `labels = gmail.list_user_labels(creds)`.
3. For each label, call `gmail.label_has_recent_message(creds, label.id,
   age)`. Collect labels where this is `False`.
4. Print each old label's `name` on its own line to stdout. Order
   follows `list_user_labels`, i.e. by name.
5. Print summary to stderr:
   `'<n> of <total> labels have no messages newer than <age>'`.

**Out of scope (YAGNI)**

- No progress indicator or concurrency. Most mailboxes have well under
  100 user labels; serial calls finish in a few seconds. If this becomes
  a pain we add a thread pool inside this command without changing
  helpers or tests.
- No `--include-system` flag. The use case is finding deletion
  candidates and system labels can't be deleted.


### `list-query`

**Constant**

```python
COUNT_CAP = 100  # max page size we ask for; cap on the exact count
```

**Signature**

```python
def list_query(
    query: str = typer.Argument(
        ..., help='A Gmail search query, e.g. "in:MySpace older_than:2y".'
    ),
) -> None:
```

**Behaviour**

1. Call `auth.load_token()`. If `None`, print `'Not logged in'` to
   stdout and exit 1.
2. `ids, estimate = gmail.search_messages(creds, query,
   max_results=COUNT_CAP)`.
3. Compute the count line:
   - `len(ids) < COUNT_CAP` → `f'{len(ids)} matches'`
   - `len(ids) == COUNT_CAP` and `estimate < COUNT_CAP` →
     `f'{COUNT_CAP}+ matches'` (estimate is clearly wrong; we already
     counted past it)
   - `len(ids) == COUNT_CAP` and `estimate >= COUNT_CAP` →
     `f'About {estimate} matches'`
4. For the first 10 IDs, call `gmail.get_message_headers(creds, mid)`.
5. Print the count line, a blank line, then one line per message:

   ```
   YYYY-MM-DD  <From>  <Subject>
   ```

   Two-space separators. No truncation — the terminal handles wrapping
   and the output stays grep-friendly.

**Date formatting** — Parse the `Date` header with
`email.utils.parsedate_to_datetime` and format as `YYYY-MM-DD`. If
parsing fails or the header is absent, print the raw value (or empty
string). Never crash on a malformed date.

**Out of scope (YAGNI)**

- No `--limit` flag for the message list. Spec says "first 10".
- No machine-readable mode (`--ids`, `--json`).
- No exact-count mode for the long tail. The hybrid count handles the
  preview-before-delete use case well enough.


## Error handling

Same conventions as existing commands:

| Condition                        | Behaviour                                                         |
|----------------------------------|-------------------------------------------------------------------|
| Not logged in                    | Print `'Not logged in'` to stdout, exit 1                         |
| Malformed `--age` (`old-labels`) | `typer.BadParameter` — Typer prints usage + error, exit 2         |
| Empty result set (`list-query`)  | Print `'0 matches'` to stdout, exit 0 (matches `grep` convention) |
| Empty result set (`old-labels`)  | Print summary to stderr only, exit 0                              |
| Network / API error              | Propagate. Typer prints the exception, non-zero exit.             |


## Testing

Tests use `pytest` with `pytest-unmagic`. Gmail API calls are mocked at
the `gmail_cleaner.gmail.build` seam (or the helper seam, for command
tests). No real credentials needed.

| File                              | What is tested                                                                                                                                                                                              |
|-----------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `test_gmail.py` (additions)       | `list_user_labels` filters out non-`user` types; `label_has_recent_message` returns True/False; `search_messages` returns `(ids, estimate)`; `get_message_headers` extracts the three headers               |
| `tests/commands/test_old_labels.py` | Not-logged-in exits 1; malformed `--age` exits 2; mixed labels (some old, some not) prints only old ones to stdout; summary line goes to stderr                                                             |
| `tests/commands/test_list_query.py` | Not-logged-in exits 1; zero matches prints `'0 matches'` and exits 0; under-cap exact count; cap-hit with low estimate (`100+`); cap-hit with high estimate (`About N`); message lines formatted correctly; malformed `Date` header falls back to raw |

The shared `tmp_dir` fixture in `tests/fixtures.py` is not needed by
these tests — they only mock API seams, not the filesystem.
