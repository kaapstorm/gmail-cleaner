# `export-inbox` command — design spec

## Purpose

Dump the current contents of the authenticated user's Gmail Inbox to a
local file in a form suitable for an LLM (or the user) to analyze with
the goal of optimizing filters, labels, and routing decisions. Expect
up to ~2,000 messages per run.

The export contains *per-message metadata and a short content hint*
only — no bodies, no attachment bytes. Filters and label definitions
are out of scope (Gmail's web UI already exports filters).

## CLI surface

```
gmc export-inbox OUTPUT
```

- `OUTPUT` (required, positional): path to write JSONL output. The
  literal value `--` means stdout.
- No other flags in v1. The command always exports every message
  currently in `INBOX`.

Exit codes:

- `0` — success.
- `1` — not logged in (matches existing commands).
- Non-zero — unhandled API error.

## Output format

JSON Lines (`.jsonl`). One JSON object per line, one line per message.
No header/footer record. Written in the order messages are returned
by `users.messages.list` (newest first, per Gmail's default).

### Record schema

```json
{
  "id": "...",
  "thread_id": "...",
  "date": "2026-04-12T09:31:00+00:00",
  "from": "Alice <alice@example.com>",
  "to": ["me@example.com"],
  "cc": [],
  "subject": "Re: lunch",
  "list_id": "<newsletter.example.com>",
  "list_unsubscribe": "<mailto:unsub@example.com>",
  "labels": ["INBOX", "IMPORTANT", "CATEGORY_PERSONAL"],
  "snippet": "Sounds good, see you then...",
  "attachments": [
    {"filename": "menu.pdf", "mime_type": "application/pdf", "size": 48213}
  ]
}
```

Field rules:

- `date` — ISO-8601 string parsed from the `Date` header when possible;
  otherwise the raw header string. `null` if the header is absent.
- `from` — raw `From` header value (no parsing beyond what Gmail
  returns).
- `to`, `cc` — lists of raw address strings. Empty lists when the
  header is absent.
- `subject` — raw `Subject` header value; `null` if absent.
- `list_id`, `list_unsubscribe` — raw header values; `null` if absent.
  These are high-signal for filter design.
- `labels` — the `labelIds` array Gmail returns (includes both user
  labels and system labels such as `INBOX`, `IMPORTANT`,
  `CATEGORY_*`).
- `snippet` — Gmail's server-generated short preview (~150–200 chars,
  HTML-decoded). Always present on `messages.get` responses.
- `attachments` — see "Attachments" below.

### Attachments

Attachment information is fetched using `format=metadata` so no body
bytes are retrieved.

- If `format=metadata` responses include MIME `parts` with
  `filename` / `mimeType` / `body.size`, emit `attachments` as the
  list of `{filename, mime_type, size}` objects shown above. Parts
  whose `filename` is empty are not attachments and are skipped.
- If `format=metadata` strips `parts` but the top-level `payload`
  still indicates attachments (e.g. `payload.mimeType` is
  `multipart/mixed` or similar), emit `"has_attachments": true|false`
  instead of the full list.
- If neither representation reliably indicates attachments, **stop
  and ask the user before switching to `format=full`**. The
  implementation plan must treat this as an explicit decision gate,
  not an automatic fallback.

## Fetching strategy

1. Page through `users.messages.list(userId='me', q='in:inbox')` to
   collect all message IDs. Paginate on `nextPageToken` until
   exhausted.
2. Build a single Gmail `service` once (mirrors
   `gmail.iter_message_headers`), then iterate the IDs sequentially,
   calling `messages.get` with `format=metadata` and
   `metadataHeaders=[Date, From, To, Cc, Subject, List-Id,
   List-Unsubscribe]`.
3. Wrap each API call with the existing `_with_retry` helper to reuse
   the project's retry/backoff policy.
4. Drive a `_progress` indicator (same UX as `delete-query`).
5. Per-message errors that are not retryable are logged to stderr as
   `skipped <id>: <reason>` and iteration continues.

Batching (`BatchHttpRequest`) is intentionally **not** used: it does
not compose with `_with_retry`, adds callback-based error handling,
and would be net-new code. Sequential fetching with the existing
helpers is simpler and fast enough for ~2k messages.

## Module layout

### `gmail_cleaner/gmail.py` — additions

- `iter_inbox_ids(creds: Credentials) -> Iterator[str]` — paginates
  `messages.list(q='in:inbox')` and yields message IDs.
- `fetch_message_export(service: Service, message_id: str) -> dict` —
  returns a record dict conforming to the schema above. Reuses
  `_with_retry`.
- `_extract_attachments(payload: dict) -> list[dict] | bool | None` —
  implements the conditional attachment logic described above.
  Returning `None` signals "representation unknown" and is treated as
  the decision-gate case at call-site.
- `_parse_iso_date(raw: str | None) -> str | None` — tolerant
  parser; returns the raw string on failure, `None` when missing.

### `gmail_cleaner/commands/export_inbox.py` — new module

Thin CLI wrapper:

- Load credentials; exit `1` if not logged in.
- Resolve `OUTPUT`: open the file for writing, or use `sys.stdout`
  when `OUTPUT == '--'`.
- Collect IDs via `iter_inbox_ids`, then iterate with `_progress`
  around `fetch_message_export`, writing one JSON line per record.
- Ensure the output stream is flushed/closed cleanly.

### `gmail_cleaner/cli.py`

Register the new command alongside the existing ones.

## Tests

- `tests/test_gmail.py`:
  - `_extract_attachments` — parametrized over fixture payloads:
    parts with attachments, parts without attachments, no parts but
    `multipart/mixed`, bare `text/plain`, unknown shape (→ `None`).
  - `fetch_message_export` — parametrized happy-path payloads
    covering: all headers present, missing headers, unparseable
    `Date`, HTML-only part, attachment present.
- `tests/commands/test_export_inbox.py`:
  - Happy path with a faked Gmail service: writes N JSONL lines to a
    temp file, each line round-trips through `json.loads`.
  - `OUTPUT == '--'` writes to stdout.
  - Not-logged-in → exit code `1`.
  - Error on one message → that message is skipped, others written,
    warning line on stderr.

All tests use pytest + `pytest-unmagic`; structurally similar cases
are parametrized per the project guidelines.

## Out of scope

- Exporting filters or label definitions (Gmail's web UI already
  offers this, and `normalize-filters` is a separate roadmap item).
- Message bodies, attachment bytes, or thread reconstruction.
- Incremental export / diffing against a previous run.
- Non-inbox mailboxes or label-scoped exports.
