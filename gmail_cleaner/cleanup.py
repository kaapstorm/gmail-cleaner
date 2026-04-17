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
        except Exception as exc:
            if not _is_retryable(exc):
                raise
            last_exc = exc
    assert last_exc is not None
    raise last_exc


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


def scan_for_messages(creds, query: str) -> ScanResult:
    service = build_service(creds)
    response = (
        service.users()
        .messages()
        .list(userId='me', q=query, maxResults=_LIST_PAGE_SIZE)
        .execute()
    )
    estimate = response.get('resultSizeEstimate', 0)
    has_results = bool(response.get('messages')) or 'nextPageToken' in response
    return ScanResult(estimate, has_results)


def find_label(
    creds,
    label_name: str,
) -> LabelLookup | None:
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
                bool(response.get('messages')) or 'nextPageToken' in response
            )
            return LabelLookup(label, estimate, has_messages)
    return None


def delete_label_completely(
    creds,
    label: dict,
    *,
    on_progress: Callable[[int], None],
) -> LabelDeletion:
    service = build_service(creds)
    label_id = label['id']
    messages_deleted = _delete_message_batches(
        service,
        _iter_message_ids(service, f'label:{label_id}'),
        on_progress=on_progress,
    )
    filters = _list_filters(service)
    matching = [
        f
        for f in filters
        if label_id in f.get('action', {}).get('addLabelIds', [])
    ]
    for f in matching:
        _delete_filter(service, f['id'])
    _delete_label_by_id(service, label_id)
    return LabelDeletion(messages_deleted, len(matching))


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
