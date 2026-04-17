import time
from collections.abc import Iterable, Iterator
from typing import Any, Callable, NamedTuple, TypeVar

from googleapiclient.errors import HttpError

from gmail_cleaner.gmail import _list_user_labels, build_service

_RETRY_DELAYS = (2.5, 5.0)
_LIST_PAGE_SIZE = 500
_DELETE_BATCH_SIZE = 500

T = TypeVar('T')


class ScanResult(NamedTuple):
    estimate: int
    has_results: bool


class LabelLookup(NamedTuple):
    label: dict
    estimate: int
    has_messages: bool


class LabelDeletion(NamedTuple):
    messages_deleted: int
    filters_deleted: int


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, (OSError, TimeoutError)):
        return True
    if isinstance(exc, HttpError):
        status = getattr(exc.resp, 'status', None)
        return status == 429 or (status is not None and status >= 500)
    return False


def _with_retry(fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    last_exc: BaseException | None = None
    for delay in (0.0, *_RETRY_DELAYS):
        if delay:
            time.sleep(delay)
        try:
            return fn(*args, **kwargs)
        except (OSError, TimeoutError, HttpError) as exc:
            if not _is_retryable(exc):
                raise
            last_exc = exc
    assert last_exc is not None
    raise last_exc


def _list_messages_kwargs(
    *,
    query: str | None,
    label_ids: list[str] | None,
) -> dict:
    kwargs: dict = {'userId': 'me', 'maxResults': _LIST_PAGE_SIZE}
    if query is not None:
        kwargs['q'] = query
    if label_ids is not None:
        kwargs['labelIds'] = label_ids
    return kwargs


def _iter_message_ids(
    service,
    *,
    query: str | None = None,
    label_ids: list[str] | None = None,
) -> Iterator[str]:
    request = (
        service.users()
        .messages()
        .list(**_list_messages_kwargs(query=query, label_ids=label_ids))
    )
    while request is not None:
        response = request.execute()
        for message in response.get('messages', []):
            yield message['id']
        request = (
            service.users()
            .messages()
            .list_next(previous_request=request, previous_response=response)
        )


def _batch_delete(service, batch: list[str]) -> None:
    (
        service.users()
        .messages()
        .batchDelete(userId='me', body={'ids': batch})
        .execute()
    )


def _delete_message_batches(
    service,
    message_ids: Iterable[str],
    *,
    on_progress: Callable[[int], None],
) -> int:
    deleted = 0
    batch: list[str] = []
    for message_id in message_ids:
        batch.append(message_id)
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


def _list_filters(service) -> list[dict]:
    response = _with_retry(
        lambda: (
            service.users().settings().filters().list(userId='me').execute()
        ),
    )
    return response.get('filter', [])


def _delete_filter(service, filter_id: str) -> None:
    _with_retry(
        lambda: (
            service.users()
            .settings()
            .filters()
            .delete(userId='me', id=filter_id)
            .execute()
        ),
    )


def _delete_label_by_id(service, label_id: str) -> None:
    _with_retry(
        lambda: (
            service.users().labels().delete(userId='me', id=label_id).execute()
        ),
    )


def _peek_query(
    service,
    *,
    query: str | None = None,
    label_ids: list[str] | None = None,
) -> ScanResult:
    response = (
        service.users()
        .messages()
        .list(**_list_messages_kwargs(query=query, label_ids=label_ids))
        .execute()
    )
    estimate = response.get('resultSizeEstimate', 0)
    has_results = bool(response.get('messages')) or 'nextPageToken' in response
    return ScanResult(estimate, has_results)


def scan_for_messages(creds, query: str) -> ScanResult:
    return _peek_query(build_service(creds), query=query)


def find_label(
    creds,
    label_name: str,
) -> LabelLookup | None:
    service = build_service(creds)
    for label in _list_user_labels(service):
        if label['name'] == label_name:
            peek = _peek_query(service, label_ids=[label['id']])
            return LabelLookup(label, peek.estimate, peek.has_results)
    return None


def delete_label_completely(
    creds,
    label: dict,
    *,
    on_progress: Callable[[int], None],
) -> LabelDeletion:
    """Delete every message tagged with ``label``, then its filters, then the label itself.

    The three destructive steps run sequentially and the operation is
    not transactional. If any step raises, the exception propagates
    and earlier steps stay applied: messages already deleted remain
    deleted, filters already deleted remain deleted, and the label
    may still exist. The caller is responsible for surfacing the
    failure and, if desired, re-running the command to finish.

    A ``LabelDeletion`` is only returned on full success; a mid-way
    failure raises instead of returning a partial count.
    """
    service = build_service(creds)
    label_id = label['id']
    messages_deleted = _delete_message_batches(
        service,
        _iter_message_ids(service, label_ids=[label_id]),
        on_progress=on_progress,
    )
    filters = _list_filters(service)
    matching = [
        f
        for f in filters
        if label_id in f.get('action', {}).get('addLabelIds', [])
    ]
    filters_deleted = 0
    for filter_record in matching:
        _delete_filter(service, filter_record['id'])
        filters_deleted += 1
    _delete_label_by_id(service, label_id)
    return LabelDeletion(messages_deleted, filters_deleted)


def delete_messages_matching(
    creds,
    query: str,
    *,
    on_progress: Callable[[int], None],
) -> int:
    service = build_service(creds)
    return _delete_message_batches(
        service,
        _iter_message_ids(service, query=query),
        on_progress=on_progress,
    )
