from collections.abc import Iterable
from typing import Callable, NamedTuple

from google.oauth2.credentials import Credentials

from gmail_cleaner import gmail
from gmail_cleaner.gmail import Service, _list_messages_kwargs, iter_message_ids

_DELETE_BATCH_SIZE = 1000


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


class Preview(NamedTuple):
    total: int
    sample_ids: list[str]


class LabelPreview(NamedTuple):
    total: int
    sample_ids: list[str]
    filters: list[dict]


def preview_query(
    creds: Credentials,
    *,
    query: str | None = None,
    label_ids: list[str] | None = None,
    sample_size: int = 10,
) -> Preview:
    """Paginate the full result set for an accurate count plus the first N ids.

    Unlike ``scan_for_messages``, which reads a single page and trusts
    Gmail's ``resultSizeEstimate``, this walks every page so the count
    is exact. Callers use it for dry-run output where accuracy
    outweighs latency.
    """
    service = gmail.build_service(creds)
    sample_ids: list[str] = []
    total = 0
    for message_id in iter_message_ids(
        service,
        query=query,
        label_ids=label_ids,
    ):
        if len(sample_ids) < sample_size:
            sample_ids.append(message_id)
        total += 1
    return Preview(total, sample_ids)


def preview_label(
    creds: Credentials,
    label: dict,
    *,
    sample_size: int = 10,
) -> LabelPreview:
    """Dry-run counterpart to ``delete_label_completely``.

    Paginates all messages tagged with ``label`` for an accurate
    count, captures the first ``sample_size`` ids, and returns the
    filter records whose ``addLabelIds`` action targets this label.
    Makes no destructive API calls.
    """
    service = gmail.build_service(creds)
    label_id = label['id']
    sample_ids: list[str] = []
    total = 0
    for message_id in iter_message_ids(service, label_ids=[label_id]):
        if len(sample_ids) < sample_size:
            sample_ids.append(message_id)
        total += 1
    filters = gmail.list_filters(service)
    matching = [
        f
        for f in filters
        if label_id in f.get('action', {}).get('addLabelIds', [])
    ]
    return LabelPreview(total, sample_ids, matching)


def _batch_delete(service: Service, batch: list[str]) -> None:
    (
        service.users()
        .messages()
        .batchDelete(userId='me', body={'ids': batch})
        .execute()
    )


def _delete_message_batches(
    service: Service,
    message_ids: Iterable[str],
    *,
    on_progress: Callable[[int], None],
) -> int:
    deleted = 0
    batch: list[str] = []
    for message_id in message_ids:
        batch.append(message_id)
        if len(batch) >= _DELETE_BATCH_SIZE:
            gmail.with_retry(_batch_delete, service, batch)
            deleted += len(batch)
            on_progress(deleted)
            batch = []
    if batch:
        gmail.with_retry(_batch_delete, service, batch)
        deleted += len(batch)
        on_progress(deleted)
    return deleted


def _delete_label_by_id(service: Service, label_id: str) -> None:
    gmail.with_retry(
        service.users().labels().delete(userId='me', id=label_id).execute,
    )


def _peek_query(
    service: Service,
    *,
    query: str | None = None,
    label_ids: list[str] | None = None,
) -> ScanResult:
    response = gmail.with_retry(
        service.users()
        .messages()
        .list(**_list_messages_kwargs(query=query, label_ids=label_ids))
        .execute,
    )
    estimate = response.get('resultSizeEstimate', 0)
    has_results = bool(response.get('messages')) or 'nextPageToken' in response
    return ScanResult(estimate, has_results)


def scan_for_messages(creds: Credentials, query: str) -> ScanResult:
    return _peek_query(gmail.build_service(creds), query=query)


def find_label(
    creds: Credentials,
    label_name: str,
) -> LabelLookup | None:
    service = gmail.build_service(creds)
    for label in gmail.list_user_labels(service):
        if label['name'] == label_name:
            peek = _peek_query(service, label_ids=[label['id']])
            return LabelLookup(label, peek.estimate, peek.has_results)
    return None


def delete_label_completely(
    creds: Credentials,
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
    service = gmail.build_service(creds)
    label_id = label['id']
    messages_deleted = _delete_message_batches(
        service,
        iter_message_ids(service, label_ids=[label_id]),
        on_progress=on_progress,
    )
    filters = gmail.list_filters(service)
    matching = [
        f
        for f in filters
        if label_id in f.get('action', {}).get('addLabelIds', [])
    ]
    filters_deleted = 0
    for filter_record in matching:
        gmail.delete_filter(service, filter_record['id'])
        filters_deleted += 1
    _delete_label_by_id(service, label_id)
    return LabelDeletion(messages_deleted, filters_deleted)


def delete_messages_matching(
    creds: Credentials,
    query: str,
    *,
    on_progress: Callable[[int], None],
) -> int:
    service = gmail.build_service(creds)
    return _delete_message_batches(
        service,
        iter_message_ids(service, query=query),
        on_progress=on_progress,
    )
