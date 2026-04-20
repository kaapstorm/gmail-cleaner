# Filter Management Commands Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `list-filters`, `create-filter`, and `delete-filter` CLI commands so Claude can read, add, and remove Gmail filters; as a follow-up, normalize `export-inbox`'s stdout sentinel to `-`.

**Architecture:** Three-layer pattern already used in the codebase: low-level `Service`-taking wrappers in `gmail.py`, higher-level `Credentials`-taking operations in a new `filters.py`, and thin CLI modules under `commands/`. All filter I/O uses JSONL — one filter object per line — to round-trip cleanly with `export-inbox`.

**Tech Stack:** Python 3.14, Typer CLI, `google-api-python-client`, pytest + unmagic, ruff for format/lint.

**Spec:** `claude/specs/2026-04-19_filter-commands.md`

---

## Conventions

- Run every command through `uv run` (project uses a uv virtualenv).
- After editing a Python module, run `uv run ruff check --select I --fix <file>` and `uv run ruff format <file>` before committing.
- Commit moves separately from content changes so diffs stay readable.
- All tests use pytest + unmagic; follow existing patterns in `tests/` and `tests/commands/`.

---

## Task 1: Move `_list_filters` and `_delete_filter` from `cleanup.py` to `gmail.py`

Pure move, no behavior change. Establishes the right home before adding new wrappers.

**Files:**
- Modify: `gmail_cleaner/gmail.py`
- Modify: `gmail_cleaner/cleanup.py`
- Modify: `tests/test_cleanup.py`
- Modify: `tests/test_gmail.py`

- [ ] **Step 1: Cut `_list_filters` and `_delete_filter` from `cleanup.py`**

Remove lines defining these two functions in `gmail_cleaner/cleanup.py` (currently near lines 168–182).

- [ ] **Step 2: Paste them into `gmail.py`**

Append to `gmail_cleaner/gmail.py`:

```python
def _list_filters(service: Service) -> list[dict]:
    response = _with_retry(
        service.users().settings().filters().list(userId='me').execute,
    )
    return response.get('filter', [])


def _delete_filter(service: Service, filter_id: str) -> None:
    _with_retry(
        service.users()
        .settings()
        .filters()
        .delete(userId='me', id=filter_id)
        .execute,
    )
```

- [ ] **Step 3: Re-import them in `cleanup.py`**

Update the existing import block in `gmail_cleaner/cleanup.py` to pull them from `gmail`:

```python
from gmail_cleaner.gmail import (
    Service,
    _delete_filter,
    _list_filters,
    _list_user_labels,
    _with_retry,
    build_service,
)
```

(Keep the function references in `cleanup.py` as `_list_filters(...)`/`_delete_filter(...)` — nothing changes at call sites.)

- [ ] **Step 4: Move the four existing tests**

Cut these tests out of `tests/test_cleanup.py` (currently `test_list_filters_returns_filter_list`, `test_list_filters_empty_response`, `test_delete_filter_calls_api`, `test_delete_filter_retries_on_5xx`) and paste into `tests/test_gmail.py`. Replace `cleanup._list_filters` / `cleanup._delete_filter` with `gmail._list_filters` / `gmail._delete_filter`.

The `test_delete_filter_retries_on_5xx` test uses a `no_sleep` fixture. `test_gmail.py` already defines `no_sleep`; `test_cleanup.py` has its own copy. Use the `test_gmail.py` one and delete the import line if nothing else in `test_cleanup.py` needs it.

Keep the existing patches in `test_cleanup.py` that mock these functions (e.g. `patch('gmail_cleaner.cleanup._list_filters', ...)`). Those patch targets remain valid because `cleanup.py` re-imports the names — `cleanup._list_filters` still resolves to the same callable.

- [ ] **Step 5: Format, lint, run tests**

```bash
uv run ruff check --select I --fix gmail_cleaner/gmail.py gmail_cleaner/cleanup.py tests/test_gmail.py tests/test_cleanup.py
uv run ruff format gmail_cleaner/gmail.py gmail_cleaner/cleanup.py tests/test_gmail.py tests/test_cleanup.py
uv run ruff check
uv run pytest
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add gmail_cleaner/gmail.py gmail_cleaner/cleanup.py tests/test_gmail.py tests/test_cleanup.py
git commit -m "refactor: move filter helpers from cleanup to gmail module"
```

---

## Task 2: Add `_create_filter` and `_get_filter` wrappers to `gmail.py`

**Files:**
- Modify: `gmail_cleaner/gmail.py`
- Modify: `tests/test_gmail.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_gmail.py`:

```python
def test_create_filter_calls_api_and_returns_created():
    mock_service = MagicMock()
    created = {'id': 'f9', 'criteria': {'from': 'x@y'}, 'action': {}}
    mock_service.users().settings().filters().create().execute.return_value = (
        created
    )
    body = {'criteria': {'from': 'x@y'}, 'action': {}}
    assert gmail._create_filter(mock_service, body) == created
    mock_service.users().settings().filters().create.assert_called_with(
        userId='me', body=body,
    )


def test_get_filter_calls_api_and_returns_filter():
    mock_service = MagicMock()
    filt = {'id': 'f9', 'criteria': {}, 'action': {}}
    mock_service.users().settings().filters().get().execute.return_value = filt
    assert gmail._get_filter(mock_service, 'f9') == filt
    mock_service.users().settings().filters().get.assert_called_with(
        userId='me', id='f9',
    )
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
uv run pytest tests/test_gmail.py::test_create_filter_calls_api_and_returns_created tests/test_gmail.py::test_get_filter_calls_api_and_returns_filter -v
```

Expected: FAIL with `AttributeError: module 'gmail_cleaner.gmail' has no attribute '_create_filter'` / `_get_filter`.

- [ ] **Step 3: Implement**

Append to `gmail_cleaner/gmail.py`:

```python
def _create_filter(service: Service, filter_dict: dict) -> dict:
    return _with_retry(
        service.users()
        .settings()
        .filters()
        .create(userId='me', body=filter_dict)
        .execute,
    )


def _get_filter(service: Service, filter_id: str) -> dict:
    return _with_retry(
        service.users()
        .settings()
        .filters()
        .get(userId='me', id=filter_id)
        .execute,
    )
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_gmail.py -v
```

Expected: PASS.

- [ ] **Step 5: Format, lint, commit**

```bash
uv run ruff check --select I --fix gmail_cleaner/gmail.py tests/test_gmail.py
uv run ruff format gmail_cleaner/gmail.py tests/test_gmail.py
uv run ruff check
git add gmail_cleaner/gmail.py tests/test_gmail.py
git commit -m "Add _create_filter and _get_filter wrappers"
```

---

## Task 3: Create `filters.py` with `list_filters` operation

**Files:**
- Create: `gmail_cleaner/filters.py`
- Create: `tests/test_filters.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_filters.py`:

```python
from unittest.mock import MagicMock, patch

import pytest
from googleapiclient.errors import HttpError

from gmail_cleaner import filters


def test_list_filters_returns_all_filters():
    creds = MagicMock()
    service = MagicMock()
    all_filters = [{'id': 'f1'}, {'id': 'f2'}]
    with (
        patch('gmail_cleaner.filters.build_service', return_value=service),
        patch(
            'gmail_cleaner.filters._list_filters',
            return_value=all_filters,
        ) as mock_list,
    ):
        assert filters.list_filters(creds) == all_filters
    mock_list.assert_called_once_with(service)


def test_list_filters_by_id_returns_single_filter_in_list():
    creds = MagicMock()
    service = MagicMock()
    one = {'id': 'f1', 'criteria': {}, 'action': {}}
    with (
        patch('gmail_cleaner.filters.build_service', return_value=service),
        patch(
            'gmail_cleaner.filters._get_filter', return_value=one,
        ) as mock_get,
    ):
        assert filters.list_filters(creds, filter_id='f1') == [one]
    mock_get.assert_called_once_with(service, 'f1')


def test_list_filters_by_id_missing_raises_filter_not_found():
    creds = MagicMock()
    service = MagicMock()
    err = HttpError(MagicMock(status=404), b'')
    with (
        patch('gmail_cleaner.filters.build_service', return_value=service),
        patch('gmail_cleaner.filters._get_filter', side_effect=err),
        pytest.raises(filters.FilterNotFound) as exc_info,
    ):
        filters.list_filters(creds, filter_id='missing')
    assert 'missing' in str(exc_info.value)
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
uv run pytest tests/test_filters.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'gmail_cleaner.filters'`.

- [ ] **Step 3: Implement**

Create `gmail_cleaner/filters.py`:

```python
from google.oauth2.credentials import Credentials
from googleapiclient.errors import HttpError

from gmail_cleaner.gmail import (
    _get_filter,
    _list_filters,
    build_service,
)


class FilterNotFound(Exception):
    """Raised when a filter ID is not found in Gmail."""


def list_filters(
    creds: Credentials,
    filter_id: str | None = None,
) -> list[dict]:
    service = build_service(creds)
    if filter_id is None:
        return _list_filters(service)
    try:
        return [_get_filter(service, filter_id)]
    except HttpError as exc:
        if getattr(exc.resp, 'status', None) == 404:
            raise FilterNotFound(filter_id) from exc
        raise
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_filters.py -v
```

Expected: PASS.

- [ ] **Step 5: Format, lint, commit**

```bash
uv run ruff check --select I --fix gmail_cleaner/filters.py tests/test_filters.py
uv run ruff format gmail_cleaner/filters.py tests/test_filters.py
uv run ruff check
git add gmail_cleaner/filters.py tests/test_filters.py
git commit -m "Add filters.list_filters operation"
```

---

## Task 4: Add `filters.create_filters` with partial-progress error

**Files:**
- Modify: `gmail_cleaner/filters.py`
- Modify: `tests/test_filters.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_filters.py`:

```python
def test_create_filters_creates_each_and_returns_created_list():
    creds = MagicMock()
    service = MagicMock()
    inputs = [
        {'criteria': {'from': 'a@x'}, 'action': {'addLabelIds': ['L1']}},
        {'criteria': {'from': 'b@x'}, 'action': {'addLabelIds': ['L2']}},
    ]
    outputs = [{'id': 'f1', **inputs[0]}, {'id': 'f2', **inputs[1]}]
    with (
        patch('gmail_cleaner.filters.build_service', return_value=service),
        patch(
            'gmail_cleaner.filters._create_filter', side_effect=outputs,
        ) as mock_create,
    ):
        assert filters.create_filters(creds, inputs) == outputs
    assert mock_create.call_count == 2


def test_create_filters_midbatch_failure_reports_partial():
    creds = MagicMock()
    service = MagicMock()
    good = {'id': 'f1', 'criteria': {'from': 'a@x'}, 'action': {}}
    err = HttpError(MagicMock(status=400), b'bad filter')
    inputs = [{'criteria': {'from': 'a@x'}, 'action': {}}, {'bogus': True}]
    with (
        patch('gmail_cleaner.filters.build_service', return_value=service),
        patch(
            'gmail_cleaner.filters._create_filter', side_effect=[good, err],
        ),
        pytest.raises(filters.CreateFiltersError) as exc_info,
    ):
        filters.create_filters(creds, inputs)
    assert exc_info.value.created == [good]
    assert exc_info.value.__cause__ is err


def test_create_filters_empty_input_returns_empty_list():
    creds = MagicMock()
    with patch(
        'gmail_cleaner.filters.build_service', return_value=MagicMock(),
    ):
        assert filters.create_filters(creds, []) == []
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
uv run pytest tests/test_filters.py -v
```

Expected: FAIL — `create_filters` / `CreateFiltersError` don't exist.

- [ ] **Step 3: Implement**

Add to `gmail_cleaner/filters.py`:

```python
from gmail_cleaner.gmail import (
    _create_filter,
    _get_filter,
    _list_filters,
    build_service,
)


class CreateFiltersError(Exception):
    """Raised when a batch create fails mid-way.

    Carries the filters that were created before the failure so the
    caller can report them and decide how to proceed. The triggering
    API error is preserved as ``__cause__``.
    """

    def __init__(self, created: list[dict]) -> None:
        super().__init__(f'create failed after {len(created)} filter(s)')
        self.created = created


def create_filters(
    creds: Credentials,
    filter_dicts: list[dict],
) -> list[dict]:
    service = build_service(creds)
    created: list[dict] = []
    for filter_dict in filter_dicts:
        try:
            created.append(_create_filter(service, filter_dict))
        except HttpError as exc:
            raise CreateFiltersError(created) from exc
    return created
```

Merge the `_create_filter` import into the existing `from gmail_cleaner.gmail import ...` block (don't duplicate).

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_filters.py -v
```

Expected: PASS.

- [ ] **Step 5: Format, lint, commit**

```bash
uv run ruff check --select I --fix gmail_cleaner/filters.py tests/test_filters.py
uv run ruff format gmail_cleaner/filters.py tests/test_filters.py
uv run ruff check
git add gmail_cleaner/filters.py tests/test_filters.py
git commit -m "Add filters.create_filters with partial-progress error"
```

---

## Task 5: Add `filters.delete_filters` with `DeleteResult`

**Files:**
- Modify: `gmail_cleaner/filters.py`
- Modify: `tests/test_filters.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_filters.py`:

```python
def test_delete_filters_deletes_all_given_ids():
    creds = MagicMock()
    service = MagicMock()
    with (
        patch('gmail_cleaner.filters.build_service', return_value=service),
        patch('gmail_cleaner.filters._delete_filter') as mock_del,
    ):
        result = filters.delete_filters(creds, ['f1', 'f2'])
    assert result == filters.DeleteResult(deleted=2, missing=[])
    assert mock_del.call_count == 2


def test_delete_filters_404_is_recorded_as_missing():
    creds = MagicMock()
    service = MagicMock()
    err = HttpError(MagicMock(status=404), b'')
    with (
        patch('gmail_cleaner.filters.build_service', return_value=service),
        patch(
            'gmail_cleaner.filters._delete_filter',
            side_effect=[None, err, None],
        ),
    ):
        result = filters.delete_filters(creds, ['f1', 'missing', 'f3'])
    assert result == filters.DeleteResult(deleted=2, missing=['missing'])


def test_delete_filters_non_404_http_error_propagates():
    creds = MagicMock()
    service = MagicMock()
    err = HttpError(MagicMock(status=500), b'')
    with (
        patch('gmail_cleaner.filters.build_service', return_value=service),
        patch('gmail_cleaner.filters._delete_filter', side_effect=err),
        pytest.raises(HttpError),
    ):
        filters.delete_filters(creds, ['f1'])
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
uv run pytest tests/test_filters.py -v
```

Expected: FAIL — `delete_filters` / `DeleteResult` don't exist.

- [ ] **Step 3: Implement**

Add to `gmail_cleaner/filters.py`:

```python
from typing import NamedTuple

from gmail_cleaner.gmail import (
    _create_filter,
    _delete_filter,
    _get_filter,
    _list_filters,
    build_service,
)


class DeleteResult(NamedTuple):
    deleted: int
    missing: list[str]


def delete_filters(
    creds: Credentials,
    filter_ids: list[str],
) -> DeleteResult:
    service = build_service(creds)
    deleted = 0
    missing: list[str] = []
    for filter_id in filter_ids:
        try:
            _delete_filter(service, filter_id)
            deleted += 1
        except HttpError as exc:
            if getattr(exc.resp, 'status', None) == 404:
                missing.append(filter_id)
                continue
            raise
    return DeleteResult(deleted=deleted, missing=missing)
```

Merge the `_delete_filter` import into the existing import block.

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_filters.py -v
```

Expected: PASS.

- [ ] **Step 5: Format, lint, commit**

```bash
uv run ruff check --select I --fix gmail_cleaner/filters.py tests/test_filters.py
uv run ruff format gmail_cleaner/filters.py tests/test_filters.py
uv run ruff check
git add gmail_cleaner/filters.py tests/test_filters.py
git commit -m "Add filters.delete_filters with DeleteResult"
```

---

## Task 6: `list-filters` CLI command

**Files:**
- Create: `gmail_cleaner/commands/list_filters.py`
- Create: `tests/commands/test_list_filters.py`
- Modify: `gmail_cleaner/cli.py`

- [ ] **Step 1: Write failing CLI tests**

Create `tests/commands/test_list_filters.py`:

```python
import json
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from gmail_cleaner import filters
from gmail_cleaner.cli import app

runner = CliRunner()


def test_list_filters_not_logged_in_exits_with_error():
    with patch('gmail_cleaner.auth.load_token', return_value=None):
        result = runner.invoke(app, ['list-filters'])
    assert result.exit_code == 1
    assert 'Not logged in' in result.stdout


def test_list_filters_prints_jsonl_one_per_line():
    creds = MagicMock()
    records = [
        {'id': 'f1', 'criteria': {'from': 'a@x'}, 'action': {}},
        {'id': 'f2', 'criteria': {'from': 'b@x'}, 'action': {}},
    ]
    with (
        patch('gmail_cleaner.auth.load_token', return_value=creds),
        patch(
            'gmail_cleaner.commands.list_filters.filters.list_filters',
            return_value=records,
        ),
    ):
        result = runner.invoke(app, ['list-filters'])
    assert result.exit_code == 0
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert [json.loads(line) for line in lines] == records


def test_list_filters_empty_prints_nothing():
    creds = MagicMock()
    with (
        patch('gmail_cleaner.auth.load_token', return_value=creds),
        patch(
            'gmail_cleaner.commands.list_filters.filters.list_filters',
            return_value=[],
        ),
    ):
        result = runner.invoke(app, ['list-filters'])
    assert result.exit_code == 0
    assert result.stdout == ''


def test_list_filters_by_id_prints_single_line():
    creds = MagicMock()
    one = {'id': 'f1', 'criteria': {}, 'action': {}}
    with (
        patch('gmail_cleaner.auth.load_token', return_value=creds),
        patch(
            'gmail_cleaner.commands.list_filters.filters.list_filters',
            return_value=[one],
        ) as mock_list,
    ):
        result = runner.invoke(app, ['list-filters', '--id', 'f1'])
    assert result.exit_code == 0
    mock_list.assert_called_once_with(creds, filter_id='f1')
    assert json.loads(result.stdout.strip()) == one


def test_list_filters_by_id_missing_exits_nonzero():
    creds = MagicMock()
    with (
        patch('gmail_cleaner.auth.load_token', return_value=creds),
        patch(
            'gmail_cleaner.commands.list_filters.filters.list_filters',
            side_effect=filters.FilterNotFound('missing'),
        ),
    ):
        result = runner.invoke(app, ['list-filters', '--id', 'missing'])
    assert result.exit_code == 1
    assert 'missing' in (result.stderr or result.stdout)
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
uv run pytest tests/commands/test_list_filters.py -v
```

Expected: FAIL — command not registered.

- [ ] **Step 3: Implement the command**

Create `gmail_cleaner/commands/list_filters.py`:

```python
import json
import sys

import typer

from gmail_cleaner import auth, filters


def list_filters(
    id: str = typer.Option(
        None,
        '--id',
        help='Return the filter with this ID instead of listing all.',
    ),
) -> None:
    creds = auth.load_token()
    if creds is None:
        typer.echo('Not logged in')
        raise typer.Exit(1)

    try:
        records = filters.list_filters(creds, filter_id=id)
    except filters.FilterNotFound as exc:
        typer.echo(f'Filter not found: {exc}', err=True)
        raise typer.Exit(1) from exc

    for record in records:
        sys.stdout.write(json.dumps(record))
        sys.stdout.write('\n')
```

- [ ] **Step 4: Register the command in `cli.py`**

Add to `gmail_cleaner/cli.py`:

```python
from gmail_cleaner.commands.list_filters import list_filters
```

And append:

```python
app.command(help='List Gmail filters as JSONL.')(list_filters)
```

- [ ] **Step 5: Run tests**

```bash
uv run pytest tests/commands/test_list_filters.py -v
```

Expected: PASS. If `result.stderr` raises because `CliRunner` doesn't separate streams by default, construct the runner with `CliRunner(mix_stderr=False)` at module top — but check other `test_*` files first to match project style; current tests don't separate streams, so the fallback `result.stdout` check will already cover it.

- [ ] **Step 6: Format, lint, commit**

```bash
uv run ruff check --select I --fix gmail_cleaner/commands/list_filters.py gmail_cleaner/cli.py tests/commands/test_list_filters.py
uv run ruff format gmail_cleaner/commands/list_filters.py gmail_cleaner/cli.py tests/commands/test_list_filters.py
uv run ruff check
uv run pytest
git add gmail_cleaner/commands/list_filters.py gmail_cleaner/cli.py tests/commands/test_list_filters.py
git commit -m "Add list-filters command"
```

---

## Task 7: `create-filter` CLI command

**Files:**
- Create: `gmail_cleaner/commands/create_filter.py`
- Create: `tests/commands/test_create_filter.py`
- Modify: `gmail_cleaner/cli.py`

- [ ] **Step 1: Write failing CLI tests**

Create `tests/commands/test_create_filter.py`:

```python
import json
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner
from unmagic import use

from gmail_cleaner import filters
from gmail_cleaner.cli import app
from tests.fixtures import tmp_dir

runner = CliRunner()


def _write_jsonl(path, records):
    with path.open('w', encoding='utf-8') as handle:
        for record in records:
            handle.write(json.dumps(record))
            handle.write('\n')


def test_create_filter_not_logged_in_exits_with_error():
    with patch('gmail_cleaner.auth.load_token', return_value=None):
        result = runner.invoke(app, ['create-filter', '-'])
    assert result.exit_code == 1
    assert 'Not logged in' in result.stdout


@use(tmp_dir)
def test_create_filter_reads_jsonl_from_file_and_prints_created():
    creds = MagicMock()
    path = tmp_dir() / 'filters.jsonl'
    inputs = [
        {'criteria': {'from': 'a@x'}, 'action': {'addLabelIds': ['L1']}},
        {'criteria': {'from': 'b@x'}, 'action': {'addLabelIds': ['L2']}},
    ]
    outputs = [{'id': 'f1', **inputs[0]}, {'id': 'f2', **inputs[1]}]
    _write_jsonl(path, inputs)
    with (
        patch('gmail_cleaner.auth.load_token', return_value=creds),
        patch(
            'gmail_cleaner.commands.create_filter.filters.create_filters',
            return_value=outputs,
        ) as mock_create,
    ):
        result = runner.invoke(app, ['create-filter', str(path)])
    assert result.exit_code == 0
    mock_create.assert_called_once_with(creds, inputs)
    printed = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
    assert printed == outputs


def test_create_filter_reads_jsonl_from_stdin():
    creds = MagicMock()
    inputs = [{'criteria': {'from': 'a@x'}, 'action': {}}]
    outputs = [{'id': 'f1', **inputs[0]}]
    stdin_text = json.dumps(inputs[0]) + '\n'
    with (
        patch('gmail_cleaner.auth.load_token', return_value=creds),
        patch(
            'gmail_cleaner.commands.create_filter.filters.create_filters',
            return_value=outputs,
        ) as mock_create,
    ):
        result = runner.invoke(app, ['create-filter', '-'], input=stdin_text)
    assert result.exit_code == 0
    mock_create.assert_called_once_with(creds, inputs)
    assert json.loads(result.stdout.strip()) == outputs[0]


@use(tmp_dir)
def test_create_filter_ignores_blank_lines():
    creds = MagicMock()
    path = tmp_dir() / 'filters.jsonl'
    inputs = [{'criteria': {'from': 'a@x'}, 'action': {}}]
    outputs = [{'id': 'f1', **inputs[0]}]
    with path.open('w', encoding='utf-8') as handle:
        handle.write('\n')
        handle.write(json.dumps(inputs[0]) + '\n')
        handle.write('   \n')
    with (
        patch('gmail_cleaner.auth.load_token', return_value=creds),
        patch(
            'gmail_cleaner.commands.create_filter.filters.create_filters',
            return_value=outputs,
        ) as mock_create,
    ):
        result = runner.invoke(app, ['create-filter', str(path)])
    assert result.exit_code == 0
    mock_create.assert_called_once_with(creds, inputs)


@use(tmp_dir)
def test_create_filter_midbatch_failure_prints_created_and_exits_nonzero():
    creds = MagicMock()
    path = tmp_dir() / 'filters.jsonl'
    inputs = [
        {'criteria': {'from': 'a@x'}, 'action': {}},
        {'bogus': True},
    ]
    _write_jsonl(path, inputs)
    good = {'id': 'f1', **inputs[0]}
    err = filters.CreateFiltersError([good])
    with (
        patch('gmail_cleaner.auth.load_token', return_value=creds),
        patch(
            'gmail_cleaner.commands.create_filter.filters.create_filters',
            side_effect=err,
        ),
    ):
        result = runner.invoke(app, ['create-filter', str(path)])
    assert result.exit_code == 1
    printed = [
        json.loads(line) for line in result.stdout.splitlines() if line.strip()
    ]
    assert printed == [good]
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
uv run pytest tests/commands/test_create_filter.py -v
```

Expected: FAIL — command not registered.

- [ ] **Step 3: Implement the command**

Create `gmail_cleaner/commands/create_filter.py`:

```python
import json
import sys
from pathlib import Path

import typer

from gmail_cleaner import auth, filters

STDIN_MARKER = '-'


def _iter_input_lines(source: str):
    if source == STDIN_MARKER:
        for line in sys.stdin:
            yield line
        return
    with Path(source).open('r', encoding='utf-8') as handle:
        for line in handle:
            yield line


def _parse_jsonl(source: str) -> list[dict]:
    records: list[dict] = []
    for line in _iter_input_lines(source):
        if not line.strip():
            continue
        records.append(json.loads(line))
    return records


def _print_created(created: list[dict]) -> None:
    for record in created:
        sys.stdout.write(json.dumps(record))
        sys.stdout.write('\n')


def create_filter(
    path: str = typer.Argument(
        ...,
        help='Path to JSONL file of filters, or "-" for stdin.',
    ),
) -> None:
    creds = auth.load_token()
    if creds is None:
        typer.echo('Not logged in')
        raise typer.Exit(1)

    filter_dicts = _parse_jsonl(path)
    try:
        created = filters.create_filters(creds, filter_dicts)
    except filters.CreateFiltersError as exc:
        _print_created(exc.created)
        typer.echo(f'create-filter failed: {exc.__cause__}', err=True)
        raise typer.Exit(1) from exc

    _print_created(created)
```

- [ ] **Step 4: Register in `cli.py`**

Add import and registration:

```python
from gmail_cleaner.commands.create_filter import create_filter
```

```python
app.command(help='Create Gmail filters from a JSONL file (or stdin via "-").')(
    create_filter,
)
```

- [ ] **Step 5: Run tests**

```bash
uv run pytest tests/commands/test_create_filter.py -v
```

Expected: PASS.

- [ ] **Step 6: Format, lint, commit**

```bash
uv run ruff check --select I --fix gmail_cleaner/commands/create_filter.py gmail_cleaner/cli.py tests/commands/test_create_filter.py
uv run ruff format gmail_cleaner/commands/create_filter.py gmail_cleaner/cli.py tests/commands/test_create_filter.py
uv run ruff check
uv run pytest
git add gmail_cleaner/commands/create_filter.py gmail_cleaner/cli.py tests/commands/test_create_filter.py
git commit -m "Add create-filter command"
```

---

## Task 8: `delete-filter` CLI command

**Files:**
- Create: `gmail_cleaner/commands/delete_filter.py`
- Create: `tests/commands/test_delete_filter.py`
- Modify: `gmail_cleaner/cli.py`

- [ ] **Step 1: Write failing CLI tests**

Create `tests/commands/test_delete_filter.py`:

```python
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from gmail_cleaner import filters
from gmail_cleaner.cli import app

runner = CliRunner()


def test_delete_filter_not_logged_in_exits_with_error():
    with patch('gmail_cleaner.auth.load_token', return_value=None):
        result = runner.invoke(app, ['delete-filter', 'f1'])
    assert result.exit_code == 1
    assert 'Not logged in' in result.stdout


def test_delete_filter_deletes_single_id():
    creds = MagicMock()
    with (
        patch('gmail_cleaner.auth.load_token', return_value=creds),
        patch(
            'gmail_cleaner.commands.delete_filter.filters.delete_filters',
            return_value=filters.DeleteResult(deleted=1, missing=[]),
        ) as mock_delete,
    ):
        result = runner.invoke(app, ['delete-filter', 'f1'])
    assert result.exit_code == 0
    mock_delete.assert_called_once_with(creds, ['f1'])
    assert 'deleted f1' in (result.stdout + (result.stderr or ''))


def test_delete_filter_reports_missing_and_exits_zero():
    creds = MagicMock()
    with (
        patch('gmail_cleaner.auth.load_token', return_value=creds),
        patch(
            'gmail_cleaner.commands.delete_filter.filters.delete_filters',
            return_value=filters.DeleteResult(
                deleted=1, missing=['ghost'],
            ),
        ),
    ):
        result = runner.invoke(app, ['delete-filter', 'f1', 'ghost'])
    assert result.exit_code == 0
    combined = result.stdout + (result.stderr or '')
    assert 'deleted f1' in combined
    assert 'not found ghost' in combined


def test_delete_filter_multiple_ids_passes_them_through():
    creds = MagicMock()
    with (
        patch('gmail_cleaner.auth.load_token', return_value=creds),
        patch(
            'gmail_cleaner.commands.delete_filter.filters.delete_filters',
            return_value=filters.DeleteResult(deleted=3, missing=[]),
        ) as mock_delete,
    ):
        result = runner.invoke(app, ['delete-filter', 'f1', 'f2', 'f3'])
    assert result.exit_code == 0
    mock_delete.assert_called_once_with(creds, ['f1', 'f2', 'f3'])
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
uv run pytest tests/commands/test_delete_filter.py -v
```

Expected: FAIL — command not registered.

- [ ] **Step 3: Implement**

Create `gmail_cleaner/commands/delete_filter.py`:

```python
import typer

from gmail_cleaner import auth, filters


def delete_filter(
    filter_ids: list[str] = typer.Argument(
        ...,
        help='One or more filter IDs to delete.',
    ),
) -> None:
    creds = auth.load_token()
    if creds is None:
        typer.echo('Not logged in')
        raise typer.Exit(1)

    # Deduplicate while preserving order, and remember which are missing.
    input_ids = list(filter_ids)
    result = filters.delete_filters(creds, input_ids)
    missing = set(result.missing)
    for filter_id in input_ids:
        if filter_id in missing:
            typer.echo(f'not found {filter_id}', err=True)
        else:
            typer.echo(f'deleted {filter_id}', err=True)
```

- [ ] **Step 4: Register in `cli.py`**

```python
from gmail_cleaner.commands.delete_filter import delete_filter
```

```python
app.command(help='Delete Gmail filters by ID.')(delete_filter)
```

- [ ] **Step 5: Run tests**

```bash
uv run pytest tests/commands/test_delete_filter.py -v
```

Expected: PASS.

- [ ] **Step 6: Format, lint, full suite, commit**

```bash
uv run ruff check --select I --fix gmail_cleaner/commands/delete_filter.py gmail_cleaner/cli.py tests/commands/test_delete_filter.py
uv run ruff format gmail_cleaner/commands/delete_filter.py gmail_cleaner/cli.py tests/commands/test_delete_filter.py
uv run ruff check
uv run pytest
git add gmail_cleaner/commands/delete_filter.py gmail_cleaner/cli.py tests/commands/test_delete_filter.py
git commit -m "Add delete-filter command"
```

---

## Task 9: README — document the three new commands

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update the Commands list**

In `README.md`, in the bulleted Commands list, replace the existing `normalize-filters` bullet with:

```markdown
* **list-filters**: List Gmail filters as JSONL.

* **create-filter**: Create one or more Gmail filters from a JSONL file
  or stdin.

* **delete-filter**: Delete one or more Gmail filters by ID.
```

- [ ] **Step 2: Add per-command sections**

Append to `README.md` (after the existing per-command sections):

````markdown
### list-filters

Prints all filters as JSONL (one JSON object per line). The output is
safe to pipe into a file, edit, and feed back into `create-filter`.

Example:

```shell
gmc list-filters > filters.jsonl
gmc list-filters --id ABCDEF
```

Options:

* **--id**: Return only the filter with this ID.


### create-filter

Reads JSONL of filter objects (one per line) and creates each in Gmail.
Prints the created filters, with their new IDs, as JSONL.

Input objects must not include an `id` field — Gmail assigns IDs.

Examples:

```shell
gmc create-filter filters.jsonl
cat filters.jsonl | gmc create-filter -
```


### delete-filter

Deletes one or more filters by ID. Reports `deleted <id>` or
`not found <id>` per filter on stderr.

Example:

```shell
gmc delete-filter ABCDEF GHIJKL
```
````

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: document list-filters, create-filter, delete-filter"
```

---

## Task 10: Follow-up — migrate `export-inbox` stdout sentinel from `--` to `-`

**Files:**
- Modify: `gmail_cleaner/commands/export_inbox.py`
- Modify: `tests/commands/test_export_inbox.py`
- Modify: `README.md`

- [ ] **Step 1: Update the test for the new sentinel**

Open `tests/commands/test_export_inbox.py`, find every occurrence of the stdout sentinel string `'--'` used as the OUTPUT argument and replace it with `'-'`. Also update any Typer `invoke(app, ['export-inbox', '--', '--'])` calls to `invoke(app, ['export-inbox', '-'])` (the first `--` end-of-options marker is no longer needed because `-` is not a Typer option).

- [ ] **Step 2: Run tests — verify they fail**

```bash
uv run pytest tests/commands/test_export_inbox.py -v
```

Expected: FAIL — the command still matches `--`, not `-`.

- [ ] **Step 3: Update the command**

In `gmail_cleaner/commands/export_inbox.py`:

1. Change `STDOUT_MARKER = '--'` to `STDOUT_MARKER = '-'`.
2. Change the help text on `output` from `'Path to write JSONL output. Use "--" to write to stdout.'` to `'Path to write JSONL output. Use "-" to write to stdout.'`.
3. Delete the multi-line comment (currently lines ~14–22) explaining the Click `--` end-of-options semantics. It's obsolete.

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/commands/test_export_inbox.py -v
uv run pytest
```

Expected: PASS.

- [ ] **Step 5: Update README**

In `README.md` under `### export-inbox`, replace:

```markdown
Use `--` as the output path to write to stdout (the first `--` is
the shell's end-of-options marker, the second is the output
argument):

```shell
gmc export-inbox -- -- | jq '.subject'
```
```

with:

```markdown
Use `-` as the output path to write to stdout:

```shell
gmc export-inbox - | jq '.subject'
```
```

- [ ] **Step 6: Format, lint, commit**

```bash
uv run ruff check --select I --fix gmail_cleaner/commands/export_inbox.py tests/commands/test_export_inbox.py
uv run ruff format gmail_cleaner/commands/export_inbox.py tests/commands/test_export_inbox.py
uv run ruff check
git add gmail_cleaner/commands/export_inbox.py tests/commands/test_export_inbox.py README.md
git commit -m "Use '-' as export-inbox stdout sentinel"
```

---

## Task 11: Update the roadmap

**Files:**
- Modify: `docs/roadmap.md`

- [ ] **Step 1: Check off the filter-commands item**

In `docs/roadmap.md`, change:

```markdown
* [ ] Implement `list-filters`, `create-filter`, and `delete-filter`
  commands.
```

to:

```markdown
* [x] Implement `list-filters`, `create-filter`, and `delete-filter`
  commands.
```

- [ ] **Step 2: Commit**

```bash
git add docs/roadmap.md
git commit -m "docs: mark filter commands complete in roadmap"
```

---

## Final verification

- [ ] **Run the full suite**

```bash
uv run ruff check
uv run pytest
```

Expected: all tests pass, no lint errors.

- [ ] **Sanity-check the CLI registers the new commands**

```bash
uv run gmc --help
```

Expected: `list-filters`, `create-filter`, `delete-filter` appear in the command list.
