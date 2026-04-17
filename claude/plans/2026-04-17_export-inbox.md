# `export-inbox` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `gmc export-inbox OUTPUT` command that writes one JSON object per inbox message to a JSONL file (or stdout when `OUTPUT` is `--`), to support LLM-assisted filter optimization.

**Architecture:** A new `gmail_cleaner.commands.export_inbox` module provides the CLI wrapper. New helpers live in `gmail_cleaner.gmail`: `iter_inbox_ids` pages through `messages.list`, and `fetch_message_export` retrieves a single message in `format=metadata` and maps it to the export record schema. Fetching is sequential, reuses the existing `_with_retry` helper, and builds one Gmail `service` per run (mirrors `iter_message_headers`). Progress and errors go to stderr.

**Tech Stack:** Python 3, `typer`, `google-api-python-client`, `pytest` + `pytest-unmagic`, `ruff`.

**Spec:** `claude/specs/2026-04-17_export-inbox.md`.

---

## Record schema reference (used throughout)

Every exported record is a single-line JSON object:

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

Rules (see spec for full detail):
- `date`: ISO-8601 from `Date` header if parseable, else the raw string, else `null` when the header is missing.
- `to`, `cc`: list of raw address strings split on `,`; `[]` when header is missing.
- `subject`, `list_id`, `list_unsubscribe`: raw strings; `null` when missing.
- `labels`: the `labelIds` list Gmail returns (includes `INBOX`, `IMPORTANT`, `CATEGORY_*`).
- `snippet`: Gmail's server-generated preview; always present on `messages.get`.
- `attachments`: see Task 2 for the logic — either a list, a `"has_attachments"` bool fallback, or a **stop-and-ask** decision gate.

---

## File structure

| Path                                                | Responsibility                                                       |
|-----------------------------------------------------|----------------------------------------------------------------------|
| `gmail_cleaner/gmail.py` (modify)                   | Add `_parse_iso_date`, `_extract_attachments`, `fetch_message_export`, `iter_inbox_ids`. |
| `gmail_cleaner/commands/export_inbox.py` (create)   | Typer command: resolve creds, open output, drive the fetch loop.     |
| `gmail_cleaner/cli.py` (modify)                     | Register `export_inbox` command.                                     |
| `tests/test_gmail.py` (modify)                      | Unit tests for the four new helpers.                                 |
| `tests/commands/test_export_inbox.py` (create)      | CLI-level tests via `typer.testing.CliRunner`.                       |
| `README.md` (modify)                                | Add usage example for `export-inbox`.                                |
| `docs/roadmap.md` (modify)                          | Tick off the `export-inbox` checkbox.                                |

---

## Housekeeping note

Before modifying any Python file, run:

```bash
uv run ruff check --select I --fix <path>
uv run ruff format <path>
```

If that produces changes, commit them separately (as a "chore: format" or "chore: sort imports" commit) before starting feature work in that file. After edits, run the same pair and commit formatting adjustments separately if they appear.

---

## Task 1: Add `_parse_iso_date` helper

**Files:**
- Modify: `gmail_cleaner/gmail.py` (add helper near the top, next to other helpers)
- Test: `tests/test_gmail.py` (append tests)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_gmail.py`:

```python
@pytest.mark.parametrize(
    'raw, expected',
    [
        (None, None),
        ('', None),
        (
            'Mon, 13 Apr 2026 14:30:00 -0400',
            '2026-04-13T14:30:00-04:00',
        ),
        # Unparseable garbage: falls back to raw string.
        ('not a real date', 'not a real date'),
        # Parseable but invalid month: falls back to raw string.
        ('Mon, 99 Abc 2026 14:30:00 -0400', 'Mon, 99 Abc 2026 14:30:00 -0400'),
    ],
)
def test_parse_iso_date(raw, expected):
    assert gmail._parse_iso_date(raw) == expected
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_gmail.py::test_parse_iso_date -v`
Expected: FAIL — `module 'gmail_cleaner.gmail' has no attribute '_parse_iso_date'`.

- [ ] **Step 3: Implement `_parse_iso_date`**

Add to `gmail_cleaner/gmail.py` (the module already imports `parsedate_to_datetime`):

```python
def _parse_iso_date(raw: str | None) -> str | None:
    if not raw:
        return None
    try:
        parsed = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return raw
    if parsed is None:
        return raw
    return parsed.isoformat()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_gmail.py::test_parse_iso_date -v`
Expected: 5 parametrized cases PASS.

- [ ] **Step 5: Lint and format**

Run:
```bash
uv run ruff check gmail_cleaner/gmail.py tests/test_gmail.py
uv run ruff format gmail_cleaner/gmail.py tests/test_gmail.py
```

- [ ] **Step 6: Commit**

```bash
git add gmail_cleaner/gmail.py tests/test_gmail.py
git commit -m "feat: add _parse_iso_date helper for export-inbox"
```

---

## Task 2: Add `_extract_attachments` helper

Walks `payload.parts` recursively and returns a list of attachment descriptors (parts that have a non-empty `filename`). Returns `None` when Gmail stripped `parts` for a `multipart/*` payload so the caller can fall back to `has_attachments`, and returns `False`/`True` when only presence is known.

**Representation decisions (baked into the helper):**
- `payload.parts` present → return `list[dict]` of attachment parts (possibly empty).
- No `parts`, and `payload.mimeType` does **not** start with `multipart/` → it is a single-part message, so no attachments possible → return `[]`.
- No `parts`, and `payload.mimeType` starts with `multipart/` → representation is indeterminate → return `None`.

The command layer (Task 5) turns `None` into the explicit decision gate: stop and ask the user before switching to `format=full`.

**Files:**
- Modify: `gmail_cleaner/gmail.py`
- Test: `tests/test_gmail.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_gmail.py`:

```python
@pytest.mark.parametrize(
    'payload, expected',
    [
        # Bare text/plain — no attachments possible.
        ({'mimeType': 'text/plain'}, []),
        # Multipart with one attachment and one body part.
        (
            {
                'mimeType': 'multipart/mixed',
                'parts': [
                    {'mimeType': 'text/plain', 'filename': ''},
                    {
                        'mimeType': 'application/pdf',
                        'filename': 'menu.pdf',
                        'body': {'size': 48213},
                    },
                ],
            },
            [
                {
                    'filename': 'menu.pdf',
                    'mime_type': 'application/pdf',
                    'size': 48213,
                },
            ],
        ),
        # Nested multipart/alternative inside multipart/mixed.
        (
            {
                'mimeType': 'multipart/mixed',
                'parts': [
                    {
                        'mimeType': 'multipart/alternative',
                        'filename': '',
                        'parts': [
                            {'mimeType': 'text/plain', 'filename': ''},
                            {'mimeType': 'text/html', 'filename': ''},
                        ],
                    },
                    {
                        'mimeType': 'image/png',
                        'filename': 'pic.png',
                        'body': {'size': 101},
                    },
                ],
            },
            [
                {
                    'filename': 'pic.png',
                    'mime_type': 'image/png',
                    'size': 101,
                },
            ],
        ),
        # Parts present but none have a filename — empty list.
        (
            {
                'mimeType': 'multipart/alternative',
                'parts': [
                    {'mimeType': 'text/plain', 'filename': ''},
                    {'mimeType': 'text/html', 'filename': ''},
                ],
            },
            [],
        ),
    ],
)
def test_extract_attachments(payload, expected):
    assert gmail._extract_attachments(payload) == expected


def test_extract_attachments_indeterminate_returns_none():
    payload = {'mimeType': 'multipart/mixed'}
    assert gmail._extract_attachments(payload) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_gmail.py::test_extract_attachments tests/test_gmail.py::test_extract_attachments_indeterminate_returns_none -v`
Expected: FAIL — `module 'gmail_cleaner.gmail' has no attribute '_extract_attachments'`.

- [ ] **Step 3: Implement `_extract_attachments`**

Add to `gmail_cleaner/gmail.py`:

```python
def _extract_attachments(payload: dict) -> list[dict] | None:
    """Return attachment descriptors, or ``None`` if indeterminate.

    - When ``payload.parts`` is present, walks it recursively and
      returns a list of ``{filename, mime_type, size}`` dicts for
      parts that declare a non-empty ``filename``.
    - When ``parts`` is absent and ``mimeType`` is not ``multipart/*``,
      returns ``[]`` (single-part message, no attachments possible).
    - When ``parts`` is absent and ``mimeType`` is ``multipart/*``,
      the representation is indeterminate and the function returns
      ``None`` so the caller can decide how to proceed.
    """
    mime_type = payload.get('mimeType', '')
    parts = payload.get('parts')
    if parts is None:
        if mime_type.startswith('multipart/'):
            return None
        return []
    attachments: list[dict] = []
    _collect_attachment_parts(parts, attachments)
    return attachments


def _collect_attachment_parts(parts: list[dict], out: list[dict]) -> None:
    for part in parts:
        filename = part.get('filename') or ''
        if filename:
            body = part.get('body', {}) or {}
            out.append(
                {
                    'filename': filename,
                    'mime_type': part.get('mimeType', ''),
                    'size': body.get('size', 0),
                },
            )
        nested = part.get('parts')
        if nested:
            _collect_attachment_parts(nested, out)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_gmail.py::test_extract_attachments tests/test_gmail.py::test_extract_attachments_indeterminate_returns_none -v`
Expected: all cases PASS.

- [ ] **Step 5: Lint and format**

```bash
uv run ruff check gmail_cleaner/gmail.py tests/test_gmail.py
uv run ruff format gmail_cleaner/gmail.py tests/test_gmail.py
```

- [ ] **Step 6: Commit**

```bash
git add gmail_cleaner/gmail.py tests/test_gmail.py
git commit -m "feat: add _extract_attachments helper for export-inbox"
```

---

## Task 3: Add `fetch_message_export`

Fetches a single message with `format=metadata` and maps it to the export record schema. Returns a dict ready to be JSON-serialized by the command layer.

**Files:**
- Modify: `gmail_cleaner/gmail.py`
- Test: `tests/test_gmail.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_gmail.py`:

```python
def _make_message(headers=None, *, labels=None, snippet='...', payload_extra=None):
    payload = {'headers': headers or [], 'mimeType': 'text/plain'}
    if payload_extra:
        payload.update(payload_extra)
    return {
        'id': 'mid',
        'threadId': 'tid',
        'labelIds': labels or [],
        'snippet': snippet,
        'payload': payload,
    }


def test_fetch_message_export_full_record():
    mock_service = MagicMock()
    mock_service.users().messages().get().execute.return_value = _make_message(
        headers=[
            {'name': 'Date', 'value': 'Mon, 13 Apr 2026 14:30:00 -0400'},
            {'name': 'From', 'value': 'Alice <alice@example.com>'},
            {'name': 'To', 'value': 'me@example.com, other@example.com'},
            {'name': 'Cc', 'value': 'cc@example.com'},
            {'name': 'Subject', 'value': 'Re: lunch'},
            {'name': 'List-Id', 'value': '<news.example.com>'},
            {'name': 'List-Unsubscribe', 'value': '<mailto:u@example.com>'},
        ],
        labels=['INBOX', 'IMPORTANT'],
        snippet='Sounds good',
        payload_extra={
            'mimeType': 'multipart/mixed',
            'parts': [
                {'mimeType': 'text/plain', 'filename': ''},
                {
                    'mimeType': 'application/pdf',
                    'filename': 'menu.pdf',
                    'body': {'size': 48213},
                },
            ],
        },
    )
    result = gmail.fetch_message_export(mock_service, 'mid')
    assert result == {
        'id': 'mid',
        'thread_id': 'tid',
        'date': '2026-04-13T14:30:00-04:00',
        'from': 'Alice <alice@example.com>',
        'to': ['me@example.com', 'other@example.com'],
        'cc': ['cc@example.com'],
        'subject': 'Re: lunch',
        'list_id': '<news.example.com>',
        'list_unsubscribe': '<mailto:u@example.com>',
        'labels': ['INBOX', 'IMPORTANT'],
        'snippet': 'Sounds good',
        'attachments': [
            {
                'filename': 'menu.pdf',
                'mime_type': 'application/pdf',
                'size': 48213,
            },
        ],
    }


def test_fetch_message_export_missing_headers_use_sensible_defaults():
    mock_service = MagicMock()
    mock_service.users().messages().get().execute.return_value = _make_message(
        headers=[],
        labels=['INBOX'],
        snippet='hi',
    )
    result = gmail.fetch_message_export(mock_service, 'mid')
    assert result['date'] is None
    assert result['from'] is None
    assert result['to'] == []
    assert result['cc'] == []
    assert result['subject'] is None
    assert result['list_id'] is None
    assert result['list_unsubscribe'] is None
    assert result['attachments'] == []


def test_fetch_message_export_indeterminate_attachments_uses_has_attachments():
    mock_service = MagicMock()
    mock_service.users().messages().get().execute.return_value = _make_message(
        payload_extra={'mimeType': 'multipart/mixed'},
    )
    result = gmail.fetch_message_export(mock_service, 'mid')
    assert 'attachments' not in result
    assert result['has_attachments'] is True


def test_fetch_message_export_uses_metadata_format_and_header_allowlist():
    mock_service = MagicMock()
    mock_service.users().messages().get().execute.return_value = _make_message()
    gmail.fetch_message_export(mock_service, 'mid')
    mock_service.users().messages().get.assert_called_with(
        userId='me',
        id='mid',
        format='metadata',
        metadataHeaders=[
            'Date', 'From', 'To', 'Cc', 'Subject',
            'List-Id', 'List-Unsubscribe',
        ],
    )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_gmail.py -k fetch_message_export -v`
Expected: FAIL — `module 'gmail_cleaner.gmail' has no attribute 'fetch_message_export'`.

- [ ] **Step 3: Implement `fetch_message_export`**

Add to `gmail_cleaner/gmail.py`:

```python
_EXPORT_HEADERS = (
    'Date', 'From', 'To', 'Cc', 'Subject',
    'List-Id', 'List-Unsubscribe',
)


def _split_addresses(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [part.strip() for part in raw.split(',') if part.strip()]


def fetch_message_export(service: Service, message_id: str) -> dict:
    """Fetch a single message and return its export record."""
    response = _with_retry(
        service.users()
        .messages()
        .get(
            userId='me',
            id=message_id,
            format='metadata',
            metadataHeaders=list(_EXPORT_HEADERS),
        )
        .execute,
    )
    payload = response.get('payload', {}) or {}
    headers = {
        header['name']: header['value']
        for header in payload.get('headers', [])
        if header['name'] in _EXPORT_HEADERS
    }
    record: dict = {
        'id': response.get('id', message_id),
        'thread_id': response.get('threadId'),
        'date': _parse_iso_date(headers.get('Date')),
        'from': headers.get('From') or None,
        'to': _split_addresses(headers.get('To')),
        'cc': _split_addresses(headers.get('Cc')),
        'subject': headers.get('Subject') or None,
        'list_id': headers.get('List-Id') or None,
        'list_unsubscribe': headers.get('List-Unsubscribe') or None,
        'labels': list(response.get('labelIds', [])),
        'snippet': response.get('snippet', ''),
    }
    attachments = _extract_attachments(payload)
    if attachments is None:
        record['has_attachments'] = True
    else:
        record['attachments'] = attachments
    return record
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_gmail.py -k fetch_message_export -v`
Expected: 4 tests PASS.

- [ ] **Step 5: Lint and format**

```bash
uv run ruff check gmail_cleaner/gmail.py tests/test_gmail.py
uv run ruff format gmail_cleaner/gmail.py tests/test_gmail.py
```

- [ ] **Step 6: Commit**

```bash
git add gmail_cleaner/gmail.py tests/test_gmail.py
git commit -m "feat: add fetch_message_export for inbox export"
```

---

## Task 4: Add `iter_inbox_ids`

Pages through `messages.list(q='in:inbox')` and yields message IDs. Reuses `_with_retry` and a single built `service`.

**Files:**
- Modify: `gmail_cleaner/gmail.py`
- Test: `tests/test_gmail.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_gmail.py`:

```python
def test_iter_inbox_ids_paginates_until_exhausted():
    mock_creds = MagicMock()
    mock_service = MagicMock()
    mock_service.users().messages().list().execute.side_effect = [
        {'messages': [{'id': 'a'}, {'id': 'b'}], 'nextPageToken': 'p2'},
        {'messages': [{'id': 'c'}]},
    ]
    with patch('gmail_cleaner.gmail.build', return_value=mock_service):
        result = list(gmail.iter_inbox_ids(mock_creds))
    assert result == ['a', 'b', 'c']


def test_iter_inbox_ids_handles_empty_inbox():
    mock_creds = MagicMock()
    mock_service = MagicMock()
    mock_service.users().messages().list().execute.return_value = {}
    with patch('gmail_cleaner.gmail.build', return_value=mock_service):
        result = list(gmail.iter_inbox_ids(mock_creds))
    assert result == []


def test_iter_inbox_ids_passes_query_and_page_token():
    mock_creds = MagicMock()
    mock_service = MagicMock()
    list_mock = mock_service.users().messages().list
    list_mock().execute.side_effect = [
        {'messages': [{'id': 'a'}], 'nextPageToken': 'tok'},
        {'messages': [{'id': 'b'}]},
    ]
    with patch('gmail_cleaner.gmail.build', return_value=mock_service):
        list(gmail.iter_inbox_ids(mock_creds))
    calls = list_mock.call_args_list
    # Filter out the accessor calls (no kwargs) from our two paginated calls.
    paginated = [call for call in calls if call.kwargs]
    assert paginated[0].kwargs == {'userId': 'me', 'q': 'in:inbox'}
    assert paginated[1].kwargs == {
        'userId': 'me', 'q': 'in:inbox', 'pageToken': 'tok',
    }
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_gmail.py -k iter_inbox_ids -v`
Expected: FAIL — `module 'gmail_cleaner.gmail' has no attribute 'iter_inbox_ids'`.

- [ ] **Step 3: Implement `iter_inbox_ids`**

Add to `gmail_cleaner/gmail.py`:

```python
def iter_inbox_ids(creds: Credentials) -> Iterator[str]:
    """Yield the ID of every message currently in INBOX."""
    service = build_service(creds)
    page_token: str | None = None
    while True:
        kwargs: dict[str, Any] = {'userId': 'me', 'q': 'in:inbox'}
        if page_token:
            kwargs['pageToken'] = page_token
        response = _with_retry(
            service.users().messages().list(**kwargs).execute,
        )
        for message in response.get('messages', []) or []:
            yield message['id']
        page_token = response.get('nextPageToken')
        if not page_token:
            return
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_gmail.py -k iter_inbox_ids -v`
Expected: 3 tests PASS.

- [ ] **Step 5: Lint and format**

```bash
uv run ruff check gmail_cleaner/gmail.py tests/test_gmail.py
uv run ruff format gmail_cleaner/gmail.py tests/test_gmail.py
```

- [ ] **Step 6: Commit**

```bash
git add gmail_cleaner/gmail.py tests/test_gmail.py
git commit -m "feat: add iter_inbox_ids paginator"
```

---

## Task 5: Add the `export-inbox` command

CLI wrapper: resolves credentials, opens output (file or stdout when `OUTPUT == '--'`), iterates IDs, writes one JSON line per record, reports progress to stderr.

**Per-message error handling:** Wrap each `fetch_message_export` call in `try/except HttpError`. On failure, write `skipped <id>: <reason>` to stderr and continue. Non-retryable errors from inside `_with_retry` surface as `HttpError` instances.

**Files:**
- Create: `gmail_cleaner/commands/export_inbox.py`
- Create: `tests/commands/test_export_inbox.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/commands/test_export_inbox.py`:

```python
import json
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner
from unmagic import use

from gmail_cleaner.cli import app
from tests.fixtures import tmp_dir

runner = CliRunner()


def _record(mid: str) -> dict:
    return {
        'id': mid,
        'thread_id': f't-{mid}',
        'date': '2026-04-13T14:30:00-04:00',
        'from': 'Alice <alice@example.com>',
        'to': ['me@example.com'],
        'cc': [],
        'subject': f'Subject {mid}',
        'list_id': None,
        'list_unsubscribe': None,
        'labels': ['INBOX'],
        'snippet': 'hi',
        'attachments': [],
    }


def test_export_inbox_not_logged_in_exits_with_error():
    with patch('gmail_cleaner.auth.load_token', return_value=None):
        result = runner.invoke(app, ['export-inbox', '/tmp/out.jsonl'])
    assert result.exit_code == 1
    assert 'Not logged in' in result.stdout


@use(tmp_dir)
def test_export_inbox_writes_jsonl_to_file():
    out = tmp_dir() / 'out.jsonl'
    mock_creds = MagicMock()
    ids = ['a', 'b', 'c']
    with (
        patch('gmail_cleaner.auth.load_token', return_value=mock_creds),
        patch(
            'gmail_cleaner.commands.export_inbox.gmail.iter_inbox_ids',
            return_value=iter(ids),
        ),
        patch(
            'gmail_cleaner.commands.export_inbox.gmail.build_service',
            return_value=MagicMock(),
        ),
        patch(
            'gmail_cleaner.commands.export_inbox.gmail.fetch_message_export',
            side_effect=lambda _svc, mid: _record(mid),
        ),
    ):
        result = runner.invoke(app, ['export-inbox', str(out)])
    assert result.exit_code == 0, result.output
    lines = out.read_text().splitlines()
    assert [json.loads(line)['id'] for line in lines] == ids


def test_export_inbox_writes_to_stdout_when_output_is_dashdash():
    mock_creds = MagicMock()
    ids = ['a', 'b']
    with (
        patch('gmail_cleaner.auth.load_token', return_value=mock_creds),
        patch(
            'gmail_cleaner.commands.export_inbox.gmail.iter_inbox_ids',
            return_value=iter(ids),
        ),
        patch(
            'gmail_cleaner.commands.export_inbox.gmail.build_service',
            return_value=MagicMock(),
        ),
        patch(
            'gmail_cleaner.commands.export_inbox.gmail.fetch_message_export',
            side_effect=lambda _svc, mid: _record(mid),
        ),
    ):
        result = runner.invoke(app, ['export-inbox', '--', '--'])
    assert result.exit_code == 0, result.output
    lines = [line for line in result.stdout.splitlines() if line]
    assert [json.loads(line)['id'] for line in lines] == ids


@use(tmp_dir)
def test_export_inbox_skips_messages_that_error():
    from googleapiclient.errors import HttpError

    out = tmp_dir() / 'out.jsonl'
    mock_creds = MagicMock()
    ids = ['a', 'b', 'c']

    def _fetch(_svc, mid):
        if mid == 'b':
            raise HttpError(MagicMock(status=404), b'')
        return _record(mid)

    with (
        patch('gmail_cleaner.auth.load_token', return_value=mock_creds),
        patch(
            'gmail_cleaner.commands.export_inbox.gmail.iter_inbox_ids',
            return_value=iter(ids),
        ),
        patch(
            'gmail_cleaner.commands.export_inbox.gmail.build_service',
            return_value=MagicMock(),
        ),
        patch(
            'gmail_cleaner.commands.export_inbox.gmail.fetch_message_export',
            side_effect=_fetch,
        ),
    ):
        result = runner.invoke(app, ['export-inbox', str(out)])
    assert result.exit_code == 0, result.output
    lines = out.read_text().splitlines()
    assert [json.loads(line)['id'] for line in lines] == ['a', 'c']
    assert 'skipped b' in result.stderr
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/commands/test_export_inbox.py -v`
Expected: FAIL (command not registered / module doesn't exist).

- [ ] **Step 3: Implement the command**

Create `gmail_cleaner/commands/export_inbox.py`:

```python
import json
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import IO, Iterator

import typer
from googleapiclient.errors import HttpError

from gmail_cleaner import auth, gmail

STDOUT_MARKER = '--'
PROGRESS_EVERY = 50

# Note on the '--' marker: Click (which Typer wraps) treats a bare
# '--' token on the command line as the end-of-options marker, so the
# shell invocation for stdout output is:
#
#     gmc export-inbox -- --
#
# The first '--' ends option parsing; the second is the OUTPUT value
# passed to this command. The README and tests reflect this.


@contextmanager
def _open_output(path: str) -> Iterator[IO[str]]:
    if path == STDOUT_MARKER:
        yield sys.stdout
        return
    with Path(path).open('w', encoding='utf-8') as handle:
        yield handle


def _report(written: int) -> None:
    print(f'Exported {written:,} messages...', file=sys.stderr)


def export_inbox(
    output: str = typer.Argument(
        ...,
        help=(
            'Path to write JSONL output. Use "--" to write to stdout.'
        ),
    ),
) -> None:
    creds = auth.load_token()
    if creds is None:
        typer.echo('Not logged in')
        raise typer.Exit(1)

    service = gmail.build_service(creds)
    written = 0
    with _open_output(output) as handle:
        for message_id in gmail.iter_inbox_ids(creds):
            try:
                record = gmail.fetch_message_export(service, message_id)
            except HttpError as exc:
                print(
                    f'skipped {message_id}: {exc}',
                    file=sys.stderr,
                )
                continue
            handle.write(json.dumps(record))
            handle.write('\n')
            written += 1
            if written % PROGRESS_EVERY == 0:
                _report(written)
    _report(written)
```

- [ ] **Step 4: Register the command**

Modify `gmail_cleaner/cli.py` to add the import and registration. Final file:

```python
import typer

from gmail_cleaner.commands.delete_label import delete_label
from gmail_cleaner.commands.delete_query import delete_query
from gmail_cleaner.commands.export_inbox import export_inbox
from gmail_cleaner.commands.list_query import list_query
from gmail_cleaner.commands.login import login
from gmail_cleaner.commands.logout import logout
from gmail_cleaner.commands.old_labels import old_labels
from gmail_cleaner.commands.whoami import whoami

app = typer.Typer(
    help='Command-line tools for cleaning up a Gmail mailbox.',
    no_args_is_help=True,
)
app.command(help='Authenticate with Google and save credentials.')(login)
app.command(help='Show the email address of the logged-in account.')(whoami)
app.command(help='Remove saved credentials.')(logout)
app.command(
    help='List user labels whose most recent message is older than --age.',
)(old_labels)
app.command(
    help='Show the count and first 10 messages matching a Gmail query.',
)(list_query)
app.command(
    help='Permanently delete all emails matching a Gmail query.',
)(delete_query)
app.command(
    help='Permanently delete a label, its filters, and all emails it labels.',
)(delete_label)
app.command(
    help='Export inbox messages as JSONL for filter-optimization analysis.',
)(export_inbox)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/commands/test_export_inbox.py -v`
Expected: 4 tests PASS.

If `CliRunner` does not separate stderr by default, construct it with `CliRunner(mix_stderr=False)` at the top of the test module and update the `runner = CliRunner()` line accordingly.

- [ ] **Step 6: Run the full test suite**

Run: `uv run pytest`
Expected: all tests pass (green).

- [ ] **Step 7: Lint and format**

```bash
uv run ruff check gmail_cleaner tests
uv run ruff format gmail_cleaner/commands/export_inbox.py gmail_cleaner/cli.py tests/commands/test_export_inbox.py
```

- [ ] **Step 8: Commit**

```bash
git add gmail_cleaner/commands/export_inbox.py gmail_cleaner/cli.py tests/commands/test_export_inbox.py
git commit -m "feat: add export-inbox command"
```

---

## Task 6: Update docs

**Files:**
- Modify: `README.md`
- Modify: `docs/roadmap.md`

- [ ] **Step 1: Expand the README section**

In `README.md`, under the `Commands` list, the `export-inbox` bullet already reads:

```
* **export-inbox**: Export all emails in Inbox.
```

Add a dedicated section after the `### delete-query` section:

````markdown
### export-inbox

Exports one JSON object per inbox message to a JSONL file, suitable
for feeding into an LLM to suggest filter or labelling improvements.

Example

```shell
gmc export-inbox inbox.jsonl
```

Use `--` as the output path to write to stdout (the first `--` is
the shell's end-of-options marker, the second is the output
argument):

```shell
gmc export-inbox -- -- | jq '.subject'
```

The export contains metadata only (headers, labels, Gmail snippet,
attachment filenames/sizes). It does not include message bodies or
attachment bytes.
````

- [ ] **Step 2: Tick the roadmap**

In `docs/roadmap.md`, change:

```
* [ ] Implement `export-inbox` command.
```

to:

```
* [x] Implement `export-inbox` command.
```

- [ ] **Step 3: Commit**

```bash
git add README.md docs/roadmap.md
git commit -m "docs: document export-inbox command and update roadmap"
```

---

## Final verification

- [ ] **Step 1: Full test suite**

Run: `uv run pytest`
Expected: all pass.

- [ ] **Step 2: Type check**

Run: `uv run mypy gmail_cleaner`
Expected: no new errors introduced.

- [ ] **Step 3: Lint check**

Run: `uv run ruff check`
Expected: clean.

- [ ] **Step 4: Manual smoke test (optional, requires credentials)**

Run: `uv run gmc export-inbox /tmp/inbox.jsonl`
Expected: progress lines on stderr; JSONL file written; each line parses as JSON; line count matches inbox size.

If the first several messages come back with `has_attachments` rather than `attachments`, **stop** and check with the user before switching to `format=full` — this is the spec's explicit decision gate.
