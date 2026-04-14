# delete-label & delete-query Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add two destructive commands (`delete-label`,
`delete-query`) that permanently delete Gmail messages with
confirmation, batch processing, and retry logic.

**Architecture:** Four new public Gmail-layer functions, all
accepting `creds`. Two helpers per command (scan-then-delete shape).
Generator pipelining lives in private internal helpers.

**Tech Stack:** Python 3.14, Typer, google-api-python-client,
pytest + pytest-unmagic.

**Spec:** `claude/specs/2026-04-14_delete-commands.md`

---

## Task 0: Reset previous work

The previous attempt added `search_all_message_ids` (commit
`37e4499`). The redesigned API replaces this with `scan_for_messages`
+ `delete_messages_matching` plus internal helpers. Drop the old
commit and re-execute against the new design. Also squash the two
fixup commits left on the branch.

- [ ] **Step 1: Verify the branch is local-only**

```bash
git log --oneline @{upstream}..HEAD 2>/dev/null || git log --oneline -10
```

If the branch has not been pushed (no upstream), continue. If it has
been pushed, **stop and ask the user** before rewriting history.

- [ ] **Step 2: Interactive rebase to squash fixups and drop old Task 1**

```bash
git rebase -i --autosquash 2cc3fb8
```

In the editor:

- The two `fixup!` lines should be auto-marked `fixup` by
  `--autosquash`. Leave them as-is so they squash into the spec and
  plan commits.
- Change the line for `37e4499` (`feat: add search_all_message_ids
  to gmail module`) from `pick` to `drop`.

Save and exit. Resolve any conflicts (none expected).

- [ ] **Step 3: Verify state**

```bash
git log --oneline -5
```

Expect to see: spec commit, plan commit, then `2cc3fb8` and earlier.
The `search_all_message_ids` commit and both fixups are gone (the
fixups are now folded into the spec/plan commits).

```bash
uv run pytest
```

Expect: all existing tests pass; no `search_all_message_ids` tests
remain.

---

## Task 1: Internal helper `_with_retry`

**Files:**
- Modify: `gmail_cleaner/gmail.py`
- Modify: `tests/test_gmail.py`

This is the foundation for all delete operations. Generic retry
wrapper used by `_delete_message_batches`, `_delete_filter`, and
`_delete_label_by_id`.

- [ ] **Step 1: Add `no_sleep` fixture**

In `tests/test_gmail.py` (or a shared `tests/conftest.py` if you
prefer cross-file reuse), add a pytest-unmagic fixture that
monkeypatches `time.sleep` to a no-op. Opt-in per test via `@use`.

```python
import time as _time

from pytest_unmagic import fixture, use


@fixture
def no_sleep(monkeypatch):
    monkeypatch.setattr('gmail_cleaner.gmail.time.sleep', lambda _s: None)
    yield
```

- [ ] **Step 2: Write failing test — succeeds first try**

```python
def test_with_retry_returns_value_on_first_success():
    result = gmail._with_retry(lambda: 'ok')
    assert result == 'ok'
```

- [ ] **Step 3: Implement minimal `_with_retry`**

Add to `gmail_cleaner/gmail.py`:

```python
import time
from googleapiclient.errors import HttpError

_RETRY_DELAYS = (2.5, 5.0)


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, (OSError, TimeoutError)):
        return True
    if isinstance(exc, HttpError):
        status = getattr(exc.resp, 'status', None)
        return status == 429 or (status is not None and status >= 500)
    return False


def _with_retry(fn, *args, **kwargs):
    last_exc: BaseException | None = None
    for attempt, delay in enumerate((0.0, *_RETRY_DELAYS)):
        if delay:
            time.sleep(delay)
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            if not _is_retryable(exc):
                raise
            last_exc = exc
    assert last_exc is not None
    raise last_exc
```

- [ ] **Step 4: Run test**

```bash
uv run pytest tests/test_gmail.py::test_with_retry_returns_value_on_first_success -v
```
Expected: PASS.

- [ ] **Step 5: Write failing test — retries on 5xx then succeeds**

```python
from unittest.mock import MagicMock

@use(no_sleep)
def test_with_retry_retries_on_5xx():
    fn = MagicMock(side_effect=[
        HttpError(MagicMock(status=503), b''),
        'ok',
    ])
    assert gmail._with_retry(fn) == 'ok'
    assert fn.call_count == 2
```

- [ ] **Step 6: Run test, expect PASS** (impl already supports it).

- [ ] **Step 7: Write failing test — retries on 429**

```python
@use(no_sleep)
def test_with_retry_retries_on_429():
    fn = MagicMock(side_effect=[
        HttpError(MagicMock(status=429), b''),
        'ok',
    ])
    assert gmail._with_retry(fn) == 'ok'
```

- [ ] **Step 8: Write failing test — does NOT retry on 4xx (other than 429)**

```python
def test_with_retry_does_not_retry_on_403():
    err = HttpError(MagicMock(status=403), b'')
    fn = MagicMock(side_effect=err)
    with pytest.raises(HttpError):
        gmail._with_retry(fn)
    assert fn.call_count == 1
```

- [ ] **Step 9: Write failing test — does NOT retry on programming errors**

```python
def test_with_retry_does_not_retry_on_value_error():
    fn = MagicMock(side_effect=ValueError('bug'))
    with pytest.raises(ValueError):
        gmail._with_retry(fn)
    assert fn.call_count == 1
```

- [ ] **Step 10: Write failing test — exhausts retries**

```python
@use(no_sleep)
def test_with_retry_raises_after_all_attempts_fail():
    err = HttpError(MagicMock(status=500), b'')
    fn = MagicMock(side_effect=err)
    with pytest.raises(HttpError):
        gmail._with_retry(fn)
    assert fn.call_count == 3
```

- [ ] **Step 11: Run all `_with_retry` tests, fix any wiring**

```bash
uv run pytest tests/test_gmail.py -k with_retry -v
```

- [ ] **Step 12: Format, lint, mypy**

```bash
uv run ruff check --select I --fix gmail_cleaner/gmail.py tests/test_gmail.py
uv run ruff format gmail_cleaner/gmail.py tests/test_gmail.py
uv run pytest
uv run mypy gmail_cleaner/gmail.py
```

- [ ] **Step 13: Commit**

```bash
git add gmail_cleaner/gmail.py tests/test_gmail.py
git commit -m "feat: add _with_retry helper to gmail module"
```

---

## Task 2: Internal helper `_iter_message_ids`

**Files:**
- Modify: `gmail_cleaner/gmail.py`
- Modify: `tests/test_gmail.py`

Pagination generator used by `delete_messages_matching` and
`delete_label_completely`. Critical: the `while request is not None`
loop terminates only when `list_next` returns `None`. Tests **must**
configure `list_next.return_value = None` (or use `side_effect=[...,
None]`) — otherwise `MagicMock.list_next()` returns another
`MagicMock`, the loop is infinite, the process hangs at 100% CPU
and can freeze the machine.

- [ ] **Step 1: Failing test — single page**

```python
def test_iter_message_ids_single_page():
    mock_service = MagicMock()
    mock_service.users().messages().list().execute.return_value = {
        'messages': [{'id': 'm1'}, {'id': 'm2'}],
    }
    mock_service.users().messages().list_next.return_value = None
    assert list(gmail._iter_message_ids(mock_service, 'in:inbox')) == ['m1', 'm2']
```

- [ ] **Step 2: Implement `_iter_message_ids`**

```python
from collections.abc import Iterator

_LIST_PAGE_SIZE = 500


def _iter_message_ids(service, query: str) -> Iterator[str]:
    request = (
        service.users()
        .messages()
        .list(userId='me', q=query, maxResults=_LIST_PAGE_SIZE)
    )
    while request is not None:
        response = request.execute()
        for m in response.get('messages', []):
            yield m['id']
        request = (
            service.users()
            .messages()
            .list_next(previous_request=request, previous_response=response)
        )
```

- [ ] **Step 3: Run, expect PASS.**

- [ ] **Step 4: Failing test — pagination**

```python
def test_iter_message_ids_paginates():
    mock_service = MagicMock()
    page1 = {'messages': [{'id': 'm1'}], 'nextPageToken': 'tok'}
    page2 = {'messages': [{'id': 'm2'}]}

    first_request = MagicMock()
    first_request.execute.return_value = page1
    mock_service.users().messages().list.return_value = first_request

    second_request = MagicMock()
    second_request.execute.return_value = page2
    mock_service.users().messages().list_next.side_effect = [
        second_request, None,
    ]

    assert list(gmail._iter_message_ids(mock_service, 'in:inbox')) == ['m1', 'm2']
```

- [ ] **Step 5: Run, expect PASS.**

- [ ] **Step 6: Failing test — empty response**

```python
def test_iter_message_ids_empty():
    mock_service = MagicMock()
    mock_service.users().messages().list().execute.return_value = {}
    mock_service.users().messages().list_next.return_value = None
    assert list(gmail._iter_message_ids(mock_service, 'in:inbox')) == []
```

- [ ] **Step 7: Failing test — laziness (regression-prevention)**

```python
def test_iter_message_ids_is_lazy():
    mock_service = MagicMock()
    page1 = {'messages': [{'id': 'm1'}], 'nextPageToken': 'tok'}
    page2 = {'messages': [{'id': 'm2'}]}
    first_request = MagicMock()
    first_request.execute.return_value = page1
    mock_service.users().messages().list.return_value = first_request
    second_request = MagicMock()
    second_request.execute.return_value = page2
    mock_service.users().messages().list_next.side_effect = [
        second_request, None,
    ]

    it = gmail._iter_message_ids(mock_service, 'in:inbox')
    # Drain only first page.
    assert next(it) == 'm1'
    # Second page must not have been fetched yet.
    assert second_request.execute.call_count == 0
    # Now drain the rest.
    assert list(it) == ['m2']
    assert second_request.execute.call_count == 1
```

- [ ] **Step 8: Run all `_iter_message_ids` tests**

```bash
uv run pytest tests/test_gmail.py -k iter_message_ids -v
```

- [ ] **Step 9: Format, lint, mypy, full suite, commit**

```bash
uv run ruff check --select I --fix gmail_cleaner/gmail.py tests/test_gmail.py
uv run ruff format gmail_cleaner/gmail.py tests/test_gmail.py
uv run pytest
uv run mypy gmail_cleaner/gmail.py
git add gmail_cleaner/gmail.py tests/test_gmail.py
git commit -m "feat: add _iter_message_ids generator to gmail module"
```

---

## Task 3: Internal helper `_delete_message_batches`

**Files:**
- Modify: `gmail_cleaner/gmail.py`
- Modify: `tests/test_gmail.py`

Consumes an iterable of IDs in batches of 500, calls `batchDelete`
for each batch via `_with_retry`, invokes `on_progress(deleted)`
after each batch. Returns total deleted.

- [ ] **Step 1: Failing test — batches in groups of 500**

```python
def test_delete_message_batches_groups_by_500():
    mock_service = MagicMock()
    ids = [f'm{i}' for i in range(750)]
    progress = []
    total = gmail._delete_message_batches(
        mock_service, ids, on_progress=progress.append,
    )
    batch_delete = mock_service.users().messages().batchDelete
    assert batch_delete.call_count == 2
    assert len(batch_delete.call_args_list[0].kwargs['body']['ids']) == 500
    assert len(batch_delete.call_args_list[1].kwargs['body']['ids']) == 250
    assert progress == [500, 750]
    assert total == 750
```

- [ ] **Step 2: Implement**

```python
from collections.abc import Callable, Iterable

_DELETE_BATCH_SIZE = 500


def _delete_message_batches(
    service,
    message_ids: Iterable[str],
    *,
    on_progress: Callable[[int], None],
) -> int:
    deleted = 0
    batch: list[str] = []
    for mid in message_ids:
        batch.append(mid)
        if len(batch) >= _DELETE_BATCH_SIZE:
            _with_retry(_batch_delete, service, batch)
            deleted += len(batch)
            on_progress(deleted)
            batch = []
    if batch:
        _with_retry(_batch_delete, service, batch)
        deleted += len(batch)
        on_progress(deleted)
    return deleted


def _batch_delete(service, batch: list[str]) -> None:
    (
        service.users()
        .messages()
        .batchDelete(userId='me', body={'ids': batch})
        .execute()
    )
```

- [ ] **Step 3: Run, expect PASS.**

- [ ] **Step 4: Failing test — empty iterable is no-op**

```python
def test_delete_message_batches_empty_is_noop():
    mock_service = MagicMock()
    progress = []
    total = gmail._delete_message_batches(
        mock_service, iter([]), on_progress=progress.append,
    )
    mock_service.users().messages().batchDelete.assert_not_called()
    assert progress == []
    assert total == 0
```

- [ ] **Step 5: Failing test — works with a generator (lazy consumption)**

```python
def test_delete_message_batches_consumes_generator():
    def gen():
        yield from (f'm{i}' for i in range(3))
    mock_service = MagicMock()
    total = gmail._delete_message_batches(
        mock_service, gen(), on_progress=lambda _d: None,
    )
    assert total == 3
    assert mock_service.users().messages().batchDelete.call_count == 1
```

- [ ] **Step 6: Failing test — retries on 5xx mid-stream**

```python
@use(no_sleep)
def test_delete_message_batches_retries_failed_batch():
    mock_service = MagicMock()
    err = HttpError(MagicMock(status=500), b'')
    mock_service.users().messages().batchDelete().execute.side_effect = [
        err, None,
    ]
    total = gmail._delete_message_batches(
        mock_service, ['m1'], on_progress=lambda _d: None,
    )
    assert total == 1
    assert mock_service.users().messages().batchDelete().execute.call_count == 2
```

- [ ] **Step 7: Failing test — propagates after retries exhausted (mid-pagination)**

```python
@use(no_sleep)
def test_delete_message_batches_propagates_after_retries():
    mock_service = MagicMock()
    err = HttpError(MagicMock(status=500), b'')
    mock_service.users().messages().batchDelete().execute.side_effect = err
    with pytest.raises(HttpError):
        gmail._delete_message_batches(
            mock_service,
            (f'm{i}' for i in range(600)),  # forces 2 batches
            on_progress=lambda _d: None,
        )
```

- [ ] **Step 8: Run all, format, lint, mypy, commit**

```bash
uv run pytest tests/test_gmail.py -k delete_message_batches -v
uv run ruff check --select I --fix gmail_cleaner/gmail.py tests/test_gmail.py
uv run ruff format gmail_cleaner/gmail.py tests/test_gmail.py
uv run pytest
uv run mypy gmail_cleaner/gmail.py
git add gmail_cleaner/gmail.py tests/test_gmail.py
git commit -m "feat: add _delete_message_batches helper to gmail module"
```

---

## Task 4: Public functions for delete-query (`scan_for_messages`, `delete_messages_matching`)

**Files:**
- Modify: `gmail_cleaner/gmail.py`
- Modify: `tests/test_gmail.py`

- [ ] **Step 1: Failing test — `scan_for_messages` happy path**

```python
def test_scan_for_messages_returns_estimate_and_has_results():
    creds = MagicMock()
    mock_service = MagicMock()
    mock_service.users().messages().list().execute.return_value = {
        'messages': [{'id': 'm1'}],
        'resultSizeEstimate': 42,
        'nextPageToken': 'tok',
    }
    with patch('gmail_cleaner.gmail.build_service', return_value=mock_service):
        estimate, has_results = gmail.scan_for_messages(creds, 'in:inbox')
    assert estimate == 42
    assert has_results is True
```

- [ ] **Step 2: Failing test — empty first page, no nextPageToken → has_results=False**

```python
def test_scan_for_messages_empty_first_page_no_token():
    creds = MagicMock()
    mock_service = MagicMock()
    mock_service.users().messages().list().execute.return_value = {
        'resultSizeEstimate': 0,
    }
    with patch('gmail_cleaner.gmail.build_service', return_value=mock_service):
        estimate, has_results = gmail.scan_for_messages(creds, 'in:inbox')
    assert estimate == 0
    assert has_results is False
```

- [ ] **Step 3: Failing test — empty first page but has nextPageToken → has_results=True**

This is the surprising edge case where the first page has no items
but there are more pages.

```python
def test_scan_for_messages_empty_first_page_with_token():
    creds = MagicMock()
    mock_service = MagicMock()
    mock_service.users().messages().list().execute.return_value = {
        'resultSizeEstimate': 5,
        'nextPageToken': 'tok',
    }
    with patch('gmail_cleaner.gmail.build_service', return_value=mock_service):
        estimate, has_results = gmail.scan_for_messages(creds, 'in:inbox')
    assert estimate == 5
    assert has_results is True
```

- [ ] **Step 4: Failing test — has messages but estimate=0 (estimate lies)**

```python
def test_scan_for_messages_messages_present_estimate_zero():
    creds = MagicMock()
    mock_service = MagicMock()
    mock_service.users().messages().list().execute.return_value = {
        'messages': [{'id': 'm1'}],
        'resultSizeEstimate': 0,
    }
    with patch('gmail_cleaner.gmail.build_service', return_value=mock_service):
        estimate, has_results = gmail.scan_for_messages(creds, 'in:inbox')
    assert estimate == 0
    assert has_results is True  # authoritative — estimate not trusted
```

- [ ] **Step 5: Implement `scan_for_messages`**

```python
def scan_for_messages(creds, query: str) -> tuple[int, bool]:
    service = build_service(creds)
    response = (
        service.users()
        .messages()
        .list(userId='me', q=query, maxResults=_LIST_PAGE_SIZE)
        .execute()
    )
    estimate = response.get('resultSizeEstimate', 0)
    has_results = bool(response.get('messages')) or 'nextPageToken' in response
    return estimate, has_results
```

- [ ] **Step 6: Run all `scan_for_messages` tests, expect PASS.**

- [ ] **Step 7: Failing test — `delete_messages_matching` paginates and deletes**

```python
def test_delete_messages_matching_paginates_and_deletes():
    creds = MagicMock()
    mock_service = MagicMock()
    mock_service.users().messages().list().execute.return_value = {
        'messages': [{'id': f'm{i}'} for i in range(3)],
    }
    mock_service.users().messages().list_next.return_value = None
    progress = []
    with patch('gmail_cleaner.gmail.build_service', return_value=mock_service):
        deleted = gmail.delete_messages_matching(
            creds, 'in:inbox', on_progress=progress.append,
        )
    assert deleted == 3
    assert progress == [3]
    mock_service.users().messages().batchDelete.assert_called_once()
```

- [ ] **Step 8: Failing test — empty result is a no-op (returns 0, no deletes)**

```python
def test_delete_messages_matching_empty():
    creds = MagicMock()
    mock_service = MagicMock()
    mock_service.users().messages().list().execute.return_value = {}
    mock_service.users().messages().list_next.return_value = None
    with patch('gmail_cleaner.gmail.build_service', return_value=mock_service):
        deleted = gmail.delete_messages_matching(
            creds, 'in:inbox', on_progress=lambda _d: None,
        )
    assert deleted == 0
    mock_service.users().messages().batchDelete.assert_not_called()
```

- [ ] **Step 9: Implement `delete_messages_matching`**

```python
def delete_messages_matching(
    creds,
    query: str,
    *,
    on_progress: Callable[[int], None],
) -> int:
    service = build_service(creds)
    return _delete_message_batches(
        service,
        _iter_message_ids(service, query),
        on_progress=on_progress,
    )
```

- [ ] **Step 10: Run, format, lint, mypy, commit**

```bash
uv run pytest tests/test_gmail.py -k 'scan_for_messages or delete_messages_matching' -v
uv run ruff check --select I --fix gmail_cleaner/gmail.py tests/test_gmail.py
uv run ruff format gmail_cleaner/gmail.py tests/test_gmail.py
uv run pytest
uv run mypy gmail_cleaner/gmail.py
git add gmail_cleaner/gmail.py tests/test_gmail.py
git commit -m "feat: add scan_for_messages and delete_messages_matching"
```

---

## Task 5: Internal filter/label primitives

**Files:**
- Modify: `gmail_cleaner/gmail.py`
- Modify: `tests/test_gmail.py`

Three small helpers used by `delete_label_completely`. All wrap a
single API call via `_with_retry`.

- [ ] **Step 1: Failing tests for `_list_filters`**

```python
def test_list_filters_returns_filter_list():
    mock_service = MagicMock()
    filters = [
        {'id': 'f1', 'action': {'addLabelIds': ['L1']}},
        {'id': 'f2', 'action': {'addLabelIds': ['L2']}},
    ]
    mock_service.users().settings().filters().list().execute.return_value = {
        'filter': filters,
    }
    assert gmail._list_filters(mock_service) == filters


def test_list_filters_empty_response():
    mock_service = MagicMock()
    mock_service.users().settings().filters().list().execute.return_value = {}
    assert gmail._list_filters(mock_service) == []
```

- [ ] **Step 2: Implement `_list_filters`**

```python
def _list_filters(service) -> list[dict]:
    response = _with_retry(
        lambda: service.users().settings().filters().list(userId='me').execute(),
    )
    return response.get('filter', [])
```

- [ ] **Step 3: Failing test for `_delete_filter` (with retry)**

```python
def test_delete_filter_calls_api():
    mock_service = MagicMock()
    gmail._delete_filter(mock_service, 'f1')
    mock_service.users().settings().filters().delete.assert_called_with(
        userId='me', id='f1',
    )


@use(no_sleep)
def test_delete_filter_retries_on_5xx():
    mock_service = MagicMock()
    err = HttpError(MagicMock(status=500), b'')
    mock_service.users().settings().filters().delete().execute.side_effect = [
        err, None,
    ]
    gmail._delete_filter(mock_service, 'f1')
    assert mock_service.users().settings().filters().delete().execute.call_count == 2
```

- [ ] **Step 4: Implement `_delete_filter`**

```python
def _delete_filter(service, filter_id: str) -> None:
    _with_retry(
        lambda: service.users().settings().filters().delete(
            userId='me', id=filter_id,
        ).execute(),
    )
```

- [ ] **Step 5: Failing test + impl for `_delete_label_by_id`**

```python
def test_delete_label_by_id_calls_api():
    mock_service = MagicMock()
    gmail._delete_label_by_id(mock_service, 'Label_1')
    mock_service.users().labels().delete.assert_called_with(
        userId='me', id='Label_1',
    )
```

```python
def _delete_label_by_id(service, label_id: str) -> None:
    _with_retry(
        lambda: service.users().labels().delete(
            userId='me', id=label_id,
        ).execute(),
    )
```

- [ ] **Step 6: Run all, format, lint, mypy, commit**

```bash
uv run pytest tests/test_gmail.py -k 'list_filters or delete_filter or delete_label_by_id' -v
uv run ruff check --select I --fix gmail_cleaner/gmail.py tests/test_gmail.py
uv run ruff format gmail_cleaner/gmail.py tests/test_gmail.py
uv run pytest
uv run mypy gmail_cleaner/gmail.py
git add gmail_cleaner/gmail.py tests/test_gmail.py
git commit -m "feat: add filter and label deletion primitives"
```

---

## Task 6: Public functions for delete-label (`find_label`, `delete_label_completely`)

**Files:**
- Modify: `gmail_cleaner/gmail.py`
- Modify: `tests/test_gmail.py`

- [ ] **Step 1: Failing test — `find_label` returns None when not found**

```python
def test_find_label_returns_none_when_not_found():
    creds = MagicMock()
    mock_service = MagicMock()
    with (
        patch('gmail_cleaner.gmail.build_service', return_value=mock_service),
        patch('gmail_cleaner.gmail._list_user_labels', return_value=[
            {'id': 'L1', 'name': 'Other', 'type': 'user'},
        ]),
    ):
        assert gmail.find_label(creds, 'MySpace') is None
```

- [ ] **Step 2: Failing test — `find_label` returns label, estimate, has_messages**

```python
def test_find_label_returns_label_estimate_and_has_messages():
    creds = MagicMock()
    mock_service = MagicMock()
    label = {'id': 'L1', 'name': 'MySpace', 'type': 'user'}
    mock_service.users().messages().list().execute.return_value = {
        'messages': [{'id': 'm1'}],
        'resultSizeEstimate': 7,
    }
    with (
        patch('gmail_cleaner.gmail.build_service', return_value=mock_service),
        patch('gmail_cleaner.gmail._list_user_labels', return_value=[label]),
    ):
        result = gmail.find_label(creds, 'MySpace')
    assert result is not None
    found_label, estimate, has_messages = result
    assert found_label == label
    assert estimate == 7
    assert has_messages is True
```

- [ ] **Step 3: Implement `find_label`**

```python
def find_label(
    creds, label_name: str,
) -> tuple[dict, int, bool] | None:
    service = build_service(creds)
    for label in _list_user_labels(service):
        if label['name'] == label_name:
            response = (
                service.users()
                .messages()
                .list(
                    userId='me',
                    q=f'label:{label["id"]}',
                    maxResults=_LIST_PAGE_SIZE,
                )
                .execute()
            )
            estimate = response.get('resultSizeEstimate', 0)
            has_messages = (
                bool(response.get('messages'))
                or 'nextPageToken' in response
            )
            return label, estimate, has_messages
    return None
```

- [ ] **Step 4: Run, expect PASS.**

- [ ] **Step 5: Failing test — `delete_label_completely` happy path**

```python
def test_delete_label_completely_deletes_messages_filters_and_label():
    creds = MagicMock()
    mock_service = MagicMock()
    label = {'id': 'L1', 'name': 'MySpace', 'type': 'user'}
    mock_service.users().messages().list().execute.return_value = {
        'messages': [{'id': 'm1'}, {'id': 'm2'}],
    }
    mock_service.users().messages().list_next.return_value = None
    filters = [
        {'id': 'f1', 'action': {'addLabelIds': ['L1']}},
        {'id': 'f2', 'action': {'addLabelIds': ['L2']}},
        {'id': 'f3', 'action': {'addLabelIds': ['L1', 'L2']}},
    ]
    with (
        patch('gmail_cleaner.gmail.build_service', return_value=mock_service),
        patch('gmail_cleaner.gmail._list_filters', return_value=filters),
        patch('gmail_cleaner.gmail._delete_filter') as del_filter,
        patch('gmail_cleaner.gmail._delete_label_by_id') as del_label,
    ):
        msgs, fs = gmail.delete_label_completely(
            creds, label, on_progress=lambda _d: None,
        )
    assert msgs == 2
    assert fs == 2  # f1 and f3 reference L1
    assert del_filter.call_count == 2
    del_label.assert_called_once_with(mock_service, 'L1')
```

- [ ] **Step 6: Failing test — defensive filter shape**

```python
def test_delete_label_completely_handles_filters_without_action():
    creds = MagicMock()
    mock_service = MagicMock()
    label = {'id': 'L1', 'name': 'X', 'type': 'user'}
    mock_service.users().messages().list().execute.return_value = {}
    mock_service.users().messages().list_next.return_value = None
    filters = [
        {'id': 'f1'},  # no action
        {'id': 'f2', 'action': {}},  # no addLabelIds
        {'id': 'f3', 'action': {'addLabelIds': ['L1']}},
    ]
    with (
        patch('gmail_cleaner.gmail.build_service', return_value=mock_service),
        patch('gmail_cleaner.gmail._list_filters', return_value=filters),
        patch('gmail_cleaner.gmail._delete_filter') as del_filter,
        patch('gmail_cleaner.gmail._delete_label_by_id'),
    ):
        msgs, fs = gmail.delete_label_completely(
            creds, label, on_progress=lambda _d: None,
        )
    assert fs == 1
    del_filter.assert_called_once_with(mock_service, 'f3')
```

- [ ] **Step 7: Failing test — zero matching filters**

```python
def test_delete_label_completely_zero_matching_filters():
    creds = MagicMock()
    mock_service = MagicMock()
    label = {'id': 'L1', 'name': 'X', 'type': 'user'}
    mock_service.users().messages().list().execute.return_value = {}
    mock_service.users().messages().list_next.return_value = None
    with (
        patch('gmail_cleaner.gmail.build_service', return_value=mock_service),
        patch('gmail_cleaner.gmail._list_filters', return_value=[
            {'id': 'f2', 'action': {'addLabelIds': ['L2']}},
        ]),
        patch('gmail_cleaner.gmail._delete_filter') as del_filter,
        patch('gmail_cleaner.gmail._delete_label_by_id'),
    ):
        _, fs = gmail.delete_label_completely(
            creds, label, on_progress=lambda _d: None,
        )
    assert fs == 0
    del_filter.assert_not_called()
```

- [ ] **Step 8: Failing test — zero messages still deletes filters and label**

```python
def test_delete_label_completely_zero_messages_still_cleans_up():
    creds = MagicMock()
    mock_service = MagicMock()
    label = {'id': 'L1', 'name': 'X', 'type': 'user'}
    mock_service.users().messages().list().execute.return_value = {}
    mock_service.users().messages().list_next.return_value = None
    with (
        patch('gmail_cleaner.gmail.build_service', return_value=mock_service),
        patch('gmail_cleaner.gmail._list_filters', return_value=[]),
        patch('gmail_cleaner.gmail._delete_label_by_id') as del_label,
    ):
        msgs, fs = gmail.delete_label_completely(
            creds, label, on_progress=lambda _d: None,
        )
    assert msgs == 0
    assert fs == 0
    del_label.assert_called_once_with(mock_service, 'L1')
```

- [ ] **Step 9: Implement `delete_label_completely`**

```python
def delete_label_completely(
    creds,
    label: dict,
    *,
    on_progress: Callable[[int], None],
) -> tuple[int, int]:
    service = build_service(creds)
    label_id = label['id']
    messages_deleted = _delete_message_batches(
        service,
        _iter_message_ids(service, f'label:{label_id}'),
        on_progress=on_progress,
    )
    filters = _list_filters(service)
    matching = [
        f for f in filters
        if label_id in f.get('action', {}).get('addLabelIds', [])
    ]
    for f in matching:
        _delete_filter(service, f['id'])
    _delete_label_by_id(service, label_id)
    return messages_deleted, len(matching)
```

- [ ] **Step 10: Run all, format, lint, mypy, commit**

```bash
uv run pytest tests/test_gmail.py -k 'find_label or delete_label_completely' -v
uv run ruff check --select I --fix gmail_cleaner/gmail.py tests/test_gmail.py
uv run ruff format gmail_cleaner/gmail.py tests/test_gmail.py
uv run pytest
uv run mypy gmail_cleaner/gmail.py
git add gmail_cleaner/gmail.py tests/test_gmail.py
git commit -m "feat: add find_label and delete_label_completely"
```

---

## Task 7: Shared progress formatter

**Files:**
- Create: `gmail_cleaner/commands/_progress.py`
- Create: `tests/commands/test_progress.py`

- [ ] **Step 1: Failing test**

```python
import io
from contextlib import redirect_stderr

from gmail_cleaner.commands._progress import format_progress


def test_format_progress_writes_running_count_to_stderr():
    buf = io.StringIO()
    with redirect_stderr(buf):
        format_progress(1523, 500)
    assert 'Deleted 500 of ~1,523 messages' in buf.getvalue()
```

- [ ] **Step 2: Implement**

```python
import sys


def format_progress(total_estimate: int, deleted: int) -> None:
    print(
        f'Deleted {deleted:,} of ~{total_estimate:,} messages...',
        file=sys.stderr,
    )
```

- [ ] **Step 3: Run, format, lint, mypy, commit**

```bash
uv run pytest tests/commands/test_progress.py -v
uv run ruff check --select I --fix gmail_cleaner/commands/_progress.py tests/commands/test_progress.py
uv run ruff format gmail_cleaner/commands/_progress.py tests/commands/test_progress.py
uv run pytest
uv run mypy gmail_cleaner/commands/_progress.py
git add gmail_cleaner/commands/_progress.py tests/commands/test_progress.py
git commit -m "feat: add shared progress formatter for delete commands"
```

---

## Task 8: `delete-query` command

**Files:**
- Create: `gmail_cleaner/commands/delete_query.py`
- Create: `tests/commands/test_delete_query.py`
- Modify: `gmail_cleaner/cli.py`

- [ ] **Step 1: Failing test — not logged in**

```python
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from gmail_cleaner.cli import app

runner = CliRunner(mix_stderr=False)


def test_delete_query_not_logged_in_exits_with_error():
    with patch('gmail_cleaner.auth.load_token', return_value=None):
        result = runner.invoke(app, ['delete-query', 'in:inbox'])
    assert result.exit_code == 1
    assert 'Not logged in' in result.stdout
```

- [ ] **Step 2: Create minimal command + register in cli.py**

```python
# gmail_cleaner/commands/delete_query.py
import functools

import typer

from gmail_cleaner import auth, gmail
from gmail_cleaner.commands._progress import format_progress


def delete_query(
    query: str = typer.Argument(
        ...,
        help='A Gmail search query, e.g. "in:MySpace older_than:2y".',
    ),
    force: bool = typer.Option(
        False, '--force', help='Skip confirmation prompt.',
    ),
) -> None:
    creds = auth.load_token()
    if creds is None:
        typer.echo('Not logged in')
        raise typer.Exit(1)
```

```python
# gmail_cleaner/cli.py — add:
from gmail_cleaner.commands.delete_query import delete_query

app.command(
    help='Permanently delete all emails matching a Gmail query.',
)(delete_query)
```

- [ ] **Step 3: Failing test — no matching messages**

```python
def test_delete_query_no_matches_exits_cleanly():
    creds = MagicMock()
    with (
        patch('gmail_cleaner.auth.load_token', return_value=creds),
        patch(
            'gmail_cleaner.commands.delete_query.gmail.scan_for_messages',
            return_value=(0, False),
        ),
        patch(
            'gmail_cleaner.commands.delete_query.gmail.delete_messages_matching',
        ) as del_match,
    ):
        result = runner.invoke(app, ['delete-query', 'in:inbox'])
    assert result.exit_code == 0
    assert 'No matching messages' in result.stdout
    del_match.assert_not_called()
```

- [ ] **Step 4: Failing test — confirmation aborted**

```python
def test_delete_query_aborted_by_user():
    creds = MagicMock()
    with (
        patch('gmail_cleaner.auth.load_token', return_value=creds),
        patch(
            'gmail_cleaner.commands.delete_query.gmail.scan_for_messages',
            return_value=(3, True),
        ),
        patch(
            'gmail_cleaner.commands.delete_query.gmail.delete_messages_matching',
        ) as del_match,
    ):
        result = runner.invoke(app, ['delete-query', 'in:inbox'], input='n\n')
    assert result.exit_code == 1
    del_match.assert_not_called()
```

- [ ] **Step 5: Failing test — successful deletion**

```python
def test_delete_query_deletes():
    creds = MagicMock()
    with (
        patch('gmail_cleaner.auth.load_token', return_value=creds),
        patch(
            'gmail_cleaner.commands.delete_query.gmail.scan_for_messages',
            return_value=(3, True),
        ),
        patch(
            'gmail_cleaner.commands.delete_query.gmail.delete_messages_matching',
            return_value=3,
        ) as del_match,
    ):
        result = runner.invoke(app, ['delete-query', 'in:inbox'], input='y\n')
    assert result.exit_code == 0
    del_match.assert_called_once()
    assert 'Deleted 3 messages' in result.stderr
```

- [ ] **Step 6: Failing test — `--force` skips prompt**

```python
def test_delete_query_force_skips_confirmation():
    creds = MagicMock()
    with (
        patch('gmail_cleaner.auth.load_token', return_value=creds),
        patch(
            'gmail_cleaner.commands.delete_query.gmail.scan_for_messages',
            return_value=(1, True),
        ),
        patch(
            'gmail_cleaner.commands.delete_query.gmail.delete_messages_matching',
            return_value=1,
        ) as del_match,
    ):
        result = runner.invoke(
            app, ['delete-query', '--force', 'in:inbox'],
        )
    assert result.exit_code == 0
    del_match.assert_called_once()
```

- [ ] **Step 7: Implement full command**

```python
import functools

import typer

from gmail_cleaner import auth, gmail
from gmail_cleaner.commands._progress import format_progress


def delete_query(
    query: str = typer.Argument(
        ...,
        help='A Gmail search query, e.g. "in:MySpace older_than:2y".',
    ),
    force: bool = typer.Option(
        False, '--force', help='Skip confirmation prompt.',
    ),
) -> None:
    creds = auth.load_token()
    if creds is None:
        typer.echo('Not logged in')
        raise typer.Exit(1)

    estimate, has_results = gmail.scan_for_messages(creds, query)
    if not has_results:
        typer.echo('No matching messages')
        return

    if not force:
        typer.confirm(
            f'Permanently delete about {estimate:,} emails matching '
            f"'{query}'?",
            abort=True,
        )

    on_progress = functools.partial(format_progress, estimate)
    deleted = gmail.delete_messages_matching(
        creds, query, on_progress=on_progress,
    )
    typer.echo(f'Deleted {deleted:,} messages.', err=True)
```

- [ ] **Step 8: Run all, format, lint, mypy, commit**

```bash
uv run pytest tests/commands/test_delete_query.py -v
uv run ruff check --select I --fix gmail_cleaner/commands/delete_query.py tests/commands/test_delete_query.py gmail_cleaner/cli.py
uv run ruff format gmail_cleaner/commands/delete_query.py tests/commands/test_delete_query.py gmail_cleaner/cli.py
uv run pytest
uv run mypy gmail_cleaner/commands/delete_query.py
git add gmail_cleaner/commands/delete_query.py tests/commands/test_delete_query.py gmail_cleaner/cli.py
git commit -m "feat: implement delete-query command"
```

---

## Task 9: `delete-label` command

**Files:**
- Create: `gmail_cleaner/commands/delete_label.py`
- Create: `tests/commands/test_delete_label.py`
- Modify: `gmail_cleaner/cli.py`

- [ ] **Step 1: Failing test — not logged in**

```python
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from gmail_cleaner.cli import app

runner = CliRunner(mix_stderr=False)


def test_delete_label_not_logged_in_exits_with_error():
    with patch('gmail_cleaner.auth.load_token', return_value=None):
        result = runner.invoke(app, ['delete-label', 'MySpace'])
    assert result.exit_code == 1
    assert 'Not logged in' in result.stdout
```

- [ ] **Step 2: Minimal command + register in cli.py**

```python
# gmail_cleaner/commands/delete_label.py
import functools

import typer

from gmail_cleaner import auth, gmail
from gmail_cleaner.commands._progress import format_progress


def delete_label(
    label_name: str = typer.Argument(
        ..., help='Name of the label to delete.',
    ),
    force: bool = typer.Option(
        False, '--force', help='Skip confirmation prompt.',
    ),
) -> None:
    creds = auth.load_token()
    if creds is None:
        typer.echo('Not logged in')
        raise typer.Exit(1)
```

```python
# gmail_cleaner/cli.py — add:
from gmail_cleaner.commands.delete_label import delete_label

app.command(
    help='Permanently delete a label, its filters, and all emails it '
         'labels.',
)(delete_label)
```

- [ ] **Step 3: Failing test — label not found**

```python
def test_delete_label_not_found_exits_with_error():
    creds = MagicMock()
    with (
        patch('gmail_cleaner.auth.load_token', return_value=creds),
        patch(
            'gmail_cleaner.commands.delete_label.gmail.find_label',
            return_value=None,
        ),
    ):
        result = runner.invoke(app, ['delete-label', 'MySpace'])
    assert result.exit_code == 1
    assert "Label 'MySpace' not found" in result.stdout
```

- [ ] **Step 4: Failing test — confirmation aborted**

```python
def test_delete_label_aborted_by_user():
    creds = MagicMock()
    label = {'id': 'L1', 'name': 'MySpace', 'type': 'user'}
    with (
        patch('gmail_cleaner.auth.load_token', return_value=creds),
        patch(
            'gmail_cleaner.commands.delete_label.gmail.find_label',
            return_value=(label, 5, True),
        ),
        patch(
            'gmail_cleaner.commands.delete_label.gmail.delete_label_completely',
        ) as del_complete,
    ):
        result = runner.invoke(
            app, ['delete-label', 'MySpace'], input='n\n',
        )
    assert result.exit_code == 1
    del_complete.assert_not_called()
```

- [ ] **Step 5: Failing test — successful deletion**

```python
def test_delete_label_deletes_messages_filters_and_label():
    creds = MagicMock()
    label = {'id': 'L1', 'name': 'MySpace', 'type': 'user'}
    with (
        patch('gmail_cleaner.auth.load_token', return_value=creds),
        patch(
            'gmail_cleaner.commands.delete_label.gmail.find_label',
            return_value=(label, 1523, True),
        ),
        patch(
            'gmail_cleaner.commands.delete_label.gmail.delete_label_completely',
            return_value=(1523, 2),
        ) as del_complete,
    ):
        result = runner.invoke(
            app, ['delete-label', '--force', 'MySpace'],
        )
    assert result.exit_code == 0
    del_complete.assert_called_once()
    assert "Deleted 1,523 messages, 2 filters, and label 'MySpace'" in result.stderr
```

- [ ] **Step 6: Failing test — zero messages still proceeds and confirms**

```python
def test_delete_label_zero_messages_still_proceeds():
    creds = MagicMock()
    label = {'id': 'L1', 'name': 'X', 'type': 'user'}
    with (
        patch('gmail_cleaner.auth.load_token', return_value=creds),
        patch(
            'gmail_cleaner.commands.delete_label.gmail.find_label',
            return_value=(label, 0, False),
        ),
        patch(
            'gmail_cleaner.commands.delete_label.gmail.delete_label_completely',
            return_value=(0, 0),
        ) as del_complete,
    ):
        result = runner.invoke(app, ['delete-label', '--force', 'X'])
    assert result.exit_code == 0
    del_complete.assert_called_once()
    assert "Deleted 0 messages, 0 filters" in result.stderr
```

- [ ] **Step 7: Implement full command**

```python
import functools

import typer

from gmail_cleaner import auth, gmail
from gmail_cleaner.commands._progress import format_progress


def delete_label(
    label_name: str = typer.Argument(
        ..., help='Name of the label to delete.',
    ),
    force: bool = typer.Option(
        False, '--force', help='Skip confirmation prompt.',
    ),
) -> None:
    creds = auth.load_token()
    if creds is None:
        typer.echo('Not logged in')
        raise typer.Exit(1)

    result = gmail.find_label(creds, label_name)
    if result is None:
        typer.echo(f"Label '{label_name}' not found")
        raise typer.Exit(1)
    label, estimate, _has_messages = result

    if not force:
        typer.confirm(
            f'About {estimate:,} emails whose labels include '
            f"'{label_name}' will be permanently deleted, along with "
            f"filters for '{label_name}' and the '{label_name}' label."
            f'\nProceed?',
            abort=True,
        )

    on_progress = functools.partial(format_progress, estimate)
    msgs, fs = gmail.delete_label_completely(
        creds, label, on_progress=on_progress,
    )
    typer.echo(
        f"Deleted {msgs:,} messages, {fs} filters, "
        f"and label '{label_name}'.",
        err=True,
    )
```

- [ ] **Step 8: Run all, format, lint, mypy, commit**

```bash
uv run pytest tests/commands/test_delete_label.py -v
uv run ruff check --select I --fix gmail_cleaner/commands/delete_label.py tests/commands/test_delete_label.py gmail_cleaner/cli.py
uv run ruff format gmail_cleaner/commands/delete_label.py tests/commands/test_delete_label.py gmail_cleaner/cli.py
uv run pytest
uv run mypy gmail_cleaner/commands/delete_label.py
git add gmail_cleaner/commands/delete_label.py tests/commands/test_delete_label.py gmail_cleaner/cli.py
git commit -m "feat: implement delete-label command"
```

---

## Task 10: Update roadmap

**Files:**
- Modify: `docs/roadmap.md`

- [ ] **Step 1: Check off the entry**

Change:

```markdown
* [ ] Implement `delete-label` and `delete-query` commands.
```

To:

```markdown
* [x] Implement `delete-label` and `delete-query` commands.
```

- [ ] **Step 2: Commit**

```bash
git add docs/roadmap.md
git commit -m "docs: check off delete-label and delete-query in roadmap"
```
