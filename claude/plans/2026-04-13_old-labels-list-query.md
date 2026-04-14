# `old-labels` and `list-query` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the `old-labels` and `list-query` commands per `claude/specs/2026-04-13_old-labels-list-query.md`.

**Architecture:** Four small helpers added to `gmail_cleaner/gmail.py` (one Gmail API call each); two thin command modules under `gmail_cleaner/commands/` that compose them; commands registered in `gmail_cleaner/cli.py`. TDD throughout — write the failing test, run it, implement, run tests, commit.

**Tech Stack:** Python 3.14, Typer, google-api-python-client, pytest + pytest-unmagic, ruff for format/lint.

---

## Conventions

- Run all commands via `uv run ...` (the project uses uv).
- Before committing changes to a Python file, run `uv run ruff format <path>` and `uv run ruff check --select I --fix <path>`. (CLAUDE.md.)
- Multi-line collection items end with a trailing comma. Single-line collections do not. (CLAUDE.md.)
- Use `pytest`'s `parametrize` to deduplicate tests with identical structure. (CLAUDE.md.)
- Mock the Gmail API at the `gmail_cleaner.gmail.build` seam for helper tests; mock the helper seam for command tests. Match the existing `tests/test_gmail.py` style.

---

## Task 1: `gmail.list_user_labels`

**Files:**
- Modify: `gmail_cleaner/gmail.py`
- Modify: `tests/test_gmail.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_gmail.py`:

```python
def test_list_user_labels_filters_to_user_type_and_sorts_by_name():
    mock_creds = MagicMock()
    mock_service = MagicMock()
    mock_service.users().labels().list().execute.return_value = {
        'labels': [
            {'id': 'Label_2', 'name': 'Zebra', 'type': 'user'},
            {'id': 'INBOX', 'name': 'INBOX', 'type': 'system'},
            {'id': 'Label_1', 'name': 'Apple', 'type': 'user'},
        ],
    }
    with patch('gmail_cleaner.gmail.build', return_value=mock_service):
        result = gmail.list_user_labels(mock_creds)
    assert [label['name'] for label in result] == ['Apple', 'Zebra']
    assert all(label['type'] == 'user' for label in result)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_gmail.py::test_list_user_labels_filters_to_user_type_and_sorts_by_name -v`
Expected: FAIL with `AttributeError: module 'gmail_cleaner.gmail' has no attribute 'list_user_labels'`.

- [ ] **Step 3: Implement**

Append to `gmail_cleaner/gmail.py`:

```python
def list_user_labels(creds: Credentials) -> list[dict]:
    service = build_service(creds)
    response = service.users().labels().list(userId='me').execute()
    user_labels = [
        label for label in response.get('labels', [])
        if label.get('type') == 'user'
    ]
    return sorted(user_labels, key=lambda label: label['name'])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_gmail.py -v`
Expected: PASS (all tests in file).

- [ ] **Step 5: Format and commit**

```bash
uv run ruff format gmail_cleaner/gmail.py tests/test_gmail.py
uv run ruff check --select I --fix gmail_cleaner/gmail.py tests/test_gmail.py
git add gmail_cleaner/gmail.py tests/test_gmail.py
git commit -m "feat: add list_user_labels helper"
```

---

## Task 2: `gmail.label_has_recent_message`

**Files:**
- Modify: `gmail_cleaner/gmail.py`
- Modify: `tests/test_gmail.py`

- [ ] **Step 1: Write the failing parametrized test**

Append to `tests/test_gmail.py`:

```python
import pytest


@pytest.mark.parametrize(
    'response, expected',
    [
        ({'messages': [{'id': 'm1'}]}, True),
        ({'messages': []}, False),
        ({}, False),
    ],
)
def test_label_has_recent_message(response, expected):
    mock_creds = MagicMock()
    mock_service = MagicMock()
    mock_service.users().messages().list().execute.return_value = response
    with patch('gmail_cleaner.gmail.build', return_value=mock_service):
        result = gmail.label_has_recent_message(
            mock_creds, 'Label_1', '2y',
        )
    assert result is expected


def test_label_has_recent_message_passes_label_id_and_age():
    mock_creds = MagicMock()
    mock_service = MagicMock()
    mock_service.users().messages().list().execute.return_value = {
        'messages': [{'id': 'm1'}],
    }
    with patch('gmail_cleaner.gmail.build', return_value=mock_service):
        gmail.label_has_recent_message(mock_creds, 'Label_1', '30d')
    # The final call to messages().list should have the right args.
    mock_service.users().messages().list.assert_called_with(
        userId='me',
        labelIds=['Label_1'],
        q='newer_than:30d',
        maxResults=1,
    )
```

Add `import pytest` at the top of the file if it's not already there.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_gmail.py -v -k label_has_recent_message`
Expected: FAIL with missing attribute.

- [ ] **Step 3: Implement**

Append to `gmail_cleaner/gmail.py`:

```python
def label_has_recent_message(
    creds: Credentials, label_id: str, age: str,
) -> bool:
    service = build_service(creds)
    response = service.users().messages().list(
        userId='me',
        labelIds=[label_id],
        q=f'newer_than:{age}',
        maxResults=1,
    ).execute()
    return bool(response.get('messages'))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_gmail.py -v`
Expected: all PASS.

- [ ] **Step 5: Format and commit**

```bash
uv run ruff format gmail_cleaner/gmail.py tests/test_gmail.py
uv run ruff check --select I --fix gmail_cleaner/gmail.py tests/test_gmail.py
git add gmail_cleaner/gmail.py tests/test_gmail.py
git commit -m "feat: add label_has_recent_message helper"
```

---

## Task 3: `gmail.search_messages`

**Files:**
- Modify: `gmail_cleaner/gmail.py`
- Modify: `tests/test_gmail.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_gmail.py`:

```python
def test_search_messages_returns_ids_and_estimate():
    mock_creds = MagicMock()
    mock_service = MagicMock()
    mock_service.users().messages().list().execute.return_value = {
        'messages': [{'id': 'm1'}, {'id': 'm2'}],
        'resultSizeEstimate': 42,
    }
    with patch('gmail_cleaner.gmail.build', return_value=mock_service):
        ids, estimate = gmail.search_messages(
            mock_creds, 'in:inbox', max_results=10,
        )
    assert ids == ['m1', 'm2']
    assert estimate == 42


def test_search_messages_handles_empty_response():
    mock_creds = MagicMock()
    mock_service = MagicMock()
    mock_service.users().messages().list().execute.return_value = {
        'resultSizeEstimate': 0,
    }
    with patch('gmail_cleaner.gmail.build', return_value=mock_service):
        ids, estimate = gmail.search_messages(
            mock_creds, 'in:inbox', max_results=10,
        )
    assert ids == []
    assert estimate == 0


def test_search_messages_passes_query_and_max_results():
    mock_creds = MagicMock()
    mock_service = MagicMock()
    mock_service.users().messages().list().execute.return_value = {
        'resultSizeEstimate': 0,
    }
    with patch('gmail_cleaner.gmail.build', return_value=mock_service):
        gmail.search_messages(mock_creds, 'older_than:1y', max_results=100)
    mock_service.users().messages().list.assert_called_with(
        userId='me', q='older_than:1y', maxResults=100,
    )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_gmail.py -v -k search_messages`
Expected: FAIL with missing attribute.

- [ ] **Step 3: Implement**

Append to `gmail_cleaner/gmail.py`:

```python
def search_messages(
    creds: Credentials, query: str, *, max_results: int,
) -> tuple[list[str], int]:
    service = build_service(creds)
    response = service.users().messages().list(
        userId='me', q=query, maxResults=max_results,
    ).execute()
    ids = [m['id'] for m in response.get('messages', [])]
    estimate = response.get('resultSizeEstimate', 0)
    return ids, estimate
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_gmail.py -v`
Expected: all PASS.

- [ ] **Step 5: Format and commit**

```bash
uv run ruff format gmail_cleaner/gmail.py tests/test_gmail.py
uv run ruff check --select I --fix gmail_cleaner/gmail.py tests/test_gmail.py
git add gmail_cleaner/gmail.py tests/test_gmail.py
git commit -m "feat: add search_messages helper"
```

---

## Task 4: `gmail.get_message_headers`

**Files:**
- Modify: `gmail_cleaner/gmail.py`
- Modify: `tests/test_gmail.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_gmail.py`:

```python
def test_get_message_headers_extracts_three_headers():
    mock_creds = MagicMock()
    mock_service = MagicMock()
    mock_service.users().messages().get().execute.return_value = {
        'payload': {
            'headers': [
                {'name': 'Date', 'value': 'Mon, 13 Apr 2026 14:30:00 -0400'},
                {'name': 'From', 'value': 'Alice <alice@example.com>'},
                {'name': 'Subject', 'value': 'Hi there'},
                {'name': 'X-Other', 'value': 'irrelevant'},
            ],
        },
    }
    with patch('gmail_cleaner.gmail.build', return_value=mock_service):
        headers = gmail.get_message_headers(mock_creds, 'm1')
    assert headers == {
        'Date': 'Mon, 13 Apr 2026 14:30:00 -0400',
        'From': 'Alice <alice@example.com>',
        'Subject': 'Hi there',
    }


def test_get_message_headers_missing_headers_default_to_empty_string():
    mock_creds = MagicMock()
    mock_service = MagicMock()
    mock_service.users().messages().get().execute.return_value = {
        'payload': {'headers': []},
    }
    with patch('gmail_cleaner.gmail.build', return_value=mock_service):
        headers = gmail.get_message_headers(mock_creds, 'm1')
    assert headers == {'Date': '', 'From': '', 'Subject': ''}


def test_get_message_headers_uses_metadata_format():
    mock_creds = MagicMock()
    mock_service = MagicMock()
    mock_service.users().messages().get().execute.return_value = {
        'payload': {'headers': []},
    }
    with patch('gmail_cleaner.gmail.build', return_value=mock_service):
        gmail.get_message_headers(mock_creds, 'm1')
    mock_service.users().messages().get.assert_called_with(
        userId='me',
        id='m1',
        format='metadata',
        metadataHeaders=['Date', 'From', 'Subject'],
    )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_gmail.py -v -k get_message_headers`
Expected: FAIL with missing attribute.

- [ ] **Step 3: Implement**

Append to `gmail_cleaner/gmail.py`:

```python
_WANTED_HEADERS = ('Date', 'From', 'Subject')


def get_message_headers(
    creds: Credentials, message_id: str,
) -> dict[str, str]:
    service = build_service(creds)
    response = service.users().messages().get(
        userId='me',
        id=message_id,
        format='metadata',
        metadataHeaders=list(_WANTED_HEADERS),
    ).execute()
    found = {
        header['name']: header['value']
        for header in response.get('payload', {}).get('headers', [])
        if header['name'] in _WANTED_HEADERS
    }
    return {name: found.get(name, '') for name in _WANTED_HEADERS}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_gmail.py -v`
Expected: all PASS.

- [ ] **Step 5: Format and commit**

```bash
uv run ruff format gmail_cleaner/gmail.py tests/test_gmail.py
uv run ruff check --select I --fix gmail_cleaner/gmail.py tests/test_gmail.py
git add gmail_cleaner/gmail.py tests/test_gmail.py
git commit -m "feat: add get_message_headers helper"
```

---

## Task 5: `old-labels` command

**Files:**
- Create: `gmail_cleaner/commands/old_labels.py`
- Modify: `gmail_cleaner/cli.py`
- Create: `tests/commands/test_old_labels.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/commands/test_old_labels.py`:

```python
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from gmail_cleaner.cli import app

runner = CliRunner(mix_stderr=False)


def test_old_labels_not_logged_in_exits_with_error():
    with patch('gmail_cleaner.auth.load_token', return_value=None):
        result = runner.invoke(app, ['old-labels'])
    assert result.exit_code == 1
    assert 'Not logged in' in result.stdout


def test_old_labels_bad_age_exits_with_usage_error():
    mock_creds = MagicMock()
    with patch('gmail_cleaner.auth.load_token', return_value=mock_creds):
        result = runner.invoke(app, ['old-labels', '--age', 'forever'])
    assert result.exit_code == 2
    assert 'must look like' in result.stderr.lower()


def test_old_labels_lists_only_labels_with_no_recent_messages():
    mock_creds = MagicMock()
    labels = [
        {'id': 'L1', 'name': 'Apple', 'type': 'user'},
        {'id': 'L2', 'name': 'Banana', 'type': 'user'},
        {'id': 'L3', 'name': 'Cherry', 'type': 'user'},
    ]
    # Apple and Cherry have no recent messages; Banana does.
    has_recent = {'L1': False, 'L2': True, 'L3': False}
    with patch('gmail_cleaner.auth.load_token', return_value=mock_creds):
        with patch(
            'gmail_cleaner.commands.old_labels.gmail.list_user_labels',
            return_value=labels,
        ):
            with patch(
                'gmail_cleaner.commands.old_labels.gmail.label_has_recent_message',
                side_effect=lambda _c, label_id, _a: has_recent[label_id],
            ):
                result = runner.invoke(app, ['old-labels'])
    assert result.exit_code == 0
    assert result.stdout.splitlines() == ['Apple', 'Cherry']
    assert '2 of 3 labels have no messages newer than 2y' in result.stderr


def test_old_labels_summary_uses_custom_age():
    mock_creds = MagicMock()
    with patch('gmail_cleaner.auth.load_token', return_value=mock_creds):
        with patch(
            'gmail_cleaner.commands.old_labels.gmail.list_user_labels',
            return_value=[],
        ):
            result = runner.invoke(app, ['old-labels', '--age', '6m'])
    assert result.exit_code == 0
    assert '0 of 0 labels have no messages newer than 6m' in result.stderr
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/commands/test_old_labels.py -v`
Expected: FAIL — `old-labels` command does not exist (Typer prints usage error).

- [ ] **Step 3: Implement the command module**

Create `gmail_cleaner/commands/old_labels.py`:

```python
import re

import typer

from gmail_cleaner import auth, gmail


_AGE_RE = re.compile(r'^\d+[dmy]$')


def _validate_age(value: str) -> str:
    if not _AGE_RE.match(value):
        raise typer.BadParameter('must look like 30d, 6m, or 2y')
    return value


def old_labels(
    age: str = typer.Option(
        '2y',
        help=(
            'Maximum age of the most recent message for a label to be '
            'considered old. Format: <number><d|m|y>.'
        ),
        callback=_validate_age,
    ),
) -> None:
    creds = auth.load_token()
    if creds is None:
        typer.echo('Not logged in')
        raise typer.Exit(1)

    labels = gmail.list_user_labels(creds)
    old = [
        label for label in labels
        if not gmail.label_has_recent_message(creds, label['id'], age)
    ]
    for label in old:
        typer.echo(label['name'])
    typer.echo(
        f'{len(old)} of {len(labels)} labels have no messages '
        f'newer than {age}',
        err=True,
    )
```

- [ ] **Step 4: Register the command**

Modify `gmail_cleaner/cli.py` — add the import and registration:

```python
import typer

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
```

(Typer converts `old_labels` to the CLI name `old-labels` automatically.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/commands/test_old_labels.py -v`
Expected: all PASS.

Then run the full suite:

Run: `uv run pytest -v`
Expected: all PASS (no regressions).

- [ ] **Step 6: Format and commit**

```bash
uv run ruff format gmail_cleaner/commands/old_labels.py gmail_cleaner/cli.py tests/commands/test_old_labels.py
uv run ruff check --select I --fix gmail_cleaner/commands/old_labels.py gmail_cleaner/cli.py tests/commands/test_old_labels.py
git add gmail_cleaner/commands/old_labels.py gmail_cleaner/cli.py tests/commands/test_old_labels.py
git commit -m "feat: implement old-labels command"
```

---

## Task 6: `list-query` command

**Files:**
- Create: `gmail_cleaner/commands/list_query.py`
- Modify: `gmail_cleaner/cli.py`
- Create: `tests/commands/test_list_query.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/commands/test_list_query.py`:

```python
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from gmail_cleaner.cli import app

runner = CliRunner(mix_stderr=False)


def _headers(date, sender, subject):
    return {'Date': date, 'From': sender, 'Subject': subject}


def test_list_query_not_logged_in_exits_with_error():
    with patch('gmail_cleaner.auth.load_token', return_value=None):
        result = runner.invoke(app, ['list-query', 'in:inbox'])
    assert result.exit_code == 1
    assert 'Not logged in' in result.stdout


def test_list_query_zero_matches():
    mock_creds = MagicMock()
    with patch('gmail_cleaner.auth.load_token', return_value=mock_creds):
        with patch(
            'gmail_cleaner.commands.list_query.gmail.search_messages',
            return_value=([], 0),
        ):
            result = runner.invoke(app, ['list-query', 'in:inbox'])
    assert result.exit_code == 0
    assert result.stdout.splitlines()[0] == '0 matches'


@pytest.mark.parametrize(
    'ids, estimate, expected_count_line',
    [
        # Under cap → exact count.
        (['m1', 'm2', 'm3'], 3, '3 matches'),
        # Cap hit, low estimate → "100+ matches".
        (['m{}'.format(i) for i in range(100)], 7, '100+ matches'),
        # Cap hit, high estimate → "About N matches".
        (['m{}'.format(i) for i in range(100)], 543, 'About 543 matches'),
    ],
)
def test_list_query_count_line(ids, estimate, expected_count_line):
    mock_creds = MagicMock()
    headers = _headers('Mon, 13 Apr 2026 14:30:00 -0400', 'a@x', 'Hi')
    with patch('gmail_cleaner.auth.load_token', return_value=mock_creds):
        with patch(
            'gmail_cleaner.commands.list_query.gmail.search_messages',
            return_value=(ids, estimate),
        ):
            with patch(
                'gmail_cleaner.commands.list_query.gmail.get_message_headers',
                return_value=headers,
            ):
                result = runner.invoke(app, ['list-query', 'in:inbox'])
    assert result.exit_code == 0
    assert result.stdout.splitlines()[0] == expected_count_line


def test_list_query_prints_first_ten_messages_only():
    mock_creds = MagicMock()
    ids = ['m{}'.format(i) for i in range(15)]
    headers = _headers('Mon, 13 Apr 2026 14:30:00 -0400', 'a@x', 'Hi')
    with patch('gmail_cleaner.auth.load_token', return_value=mock_creds):
        with patch(
            'gmail_cleaner.commands.list_query.gmail.search_messages',
            return_value=(ids, 15),
        ):
            with patch(
                'gmail_cleaner.commands.list_query.gmail.get_message_headers',
                return_value=headers,
            ) as get_headers:
                result = runner.invoke(app, ['list-query', 'in:inbox'])
    assert result.exit_code == 0
    # 1 count line + 1 blank line + 10 message lines = 12.
    assert len(result.stdout.splitlines()) == 12
    assert get_headers.call_count == 10


def test_list_query_formats_message_line():
    mock_creds = MagicMock()
    headers = _headers(
        'Mon, 13 Apr 2026 14:30:00 -0400',
        'Alice <alice@example.com>',
        'Hello world',
    )
    with patch('gmail_cleaner.auth.load_token', return_value=mock_creds):
        with patch(
            'gmail_cleaner.commands.list_query.gmail.search_messages',
            return_value=(['m1'], 1),
        ):
            with patch(
                'gmail_cleaner.commands.list_query.gmail.get_message_headers',
                return_value=headers,
            ):
                result = runner.invoke(app, ['list-query', 'in:inbox'])
    lines = result.stdout.splitlines()
    # Lines: [count, '', message]
    assert lines[2] == (
        '2026-04-13  Alice <alice@example.com>  Hello world'
    )


def test_list_query_falls_back_to_raw_date_on_parse_failure():
    mock_creds = MagicMock()
    headers = _headers('not a real date', 'a@x', 'Hi')
    with patch('gmail_cleaner.auth.load_token', return_value=mock_creds):
        with patch(
            'gmail_cleaner.commands.list_query.gmail.search_messages',
            return_value=(['m1'], 1),
        ):
            with patch(
                'gmail_cleaner.commands.list_query.gmail.get_message_headers',
                return_value=headers,
            ):
                result = runner.invoke(app, ['list-query', 'in:inbox'])
    lines = result.stdout.splitlines()
    assert lines[2].startswith('not a real date  ')
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/commands/test_list_query.py -v`
Expected: FAIL — `list-query` command does not exist.

- [ ] **Step 3: Implement the command module**

Create `gmail_cleaner/commands/list_query.py`:

```python
from email.utils import parsedate_to_datetime

import typer

from gmail_cleaner import auth, gmail


COUNT_CAP = 100
PREVIEW_LIMIT = 10


def _format_count(num_returned: int, estimate: int) -> str:
    if num_returned < COUNT_CAP:
        return f'{num_returned} matches'
    if estimate < COUNT_CAP:
        return f'{COUNT_CAP}+ matches'
    return f'About {estimate} matches'


def _format_date(raw: str) -> str:
    try:
        dt = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return raw
    if dt is None:
        return raw
    return dt.strftime('%Y-%m-%d')


def list_query(
    query: str = typer.Argument(
        ...,
        help='A Gmail search query, e.g. "in:MySpace older_than:2y".',
    ),
) -> None:
    creds = auth.load_token()
    if creds is None:
        typer.echo('Not logged in')
        raise typer.Exit(1)

    ids, estimate = gmail.search_messages(
        creds, query, max_results=COUNT_CAP,
    )
    typer.echo(_format_count(len(ids), estimate))
    typer.echo('')
    for message_id in ids[:PREVIEW_LIMIT]:
        headers = gmail.get_message_headers(creds, message_id)
        date = _format_date(headers['Date'])
        typer.echo(f'{date}  {headers["From"]}  {headers["Subject"]}')
```

- [ ] **Step 4: Register the command**

Modify `gmail_cleaner/cli.py` — add the import and registration:

```python
import typer

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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/commands/test_list_query.py -v`
Expected: all PASS.

Then run the full suite:

Run: `uv run pytest -v`
Expected: all PASS (no regressions).

- [ ] **Step 6: Format and commit**

```bash
uv run ruff format gmail_cleaner/commands/list_query.py gmail_cleaner/cli.py tests/commands/test_list_query.py
uv run ruff check --select I --fix gmail_cleaner/commands/list_query.py gmail_cleaner/cli.py tests/commands/test_list_query.py
git add gmail_cleaner/commands/list_query.py gmail_cleaner/cli.py tests/commands/test_list_query.py
git commit -m "feat: implement list-query command"
```

---

## Final verification

- [ ] Run the full test suite once more: `uv run pytest -v`
- [ ] Run linter: `uv run ruff check`
- [ ] Run mypy on touched files: `uv run mypy gmail_cleaner/gmail.py gmail_cleaner/commands/old_labels.py gmail_cleaner/commands/list_query.py gmail_cleaner/cli.py`
- [ ] Manually exercise the CLI:
  - `uv run gmc --help` shows both new commands.
  - `uv run gmc old-labels --help` and `uv run gmc list-query --help` show help text.
  - `uv run gmc old-labels --age forever` exits with usage error.
