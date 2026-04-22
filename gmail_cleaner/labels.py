from google.oauth2.credentials import Credentials
from googleapiclient.errors import HttpError

from gmail_cleaner import gmail


class CreateLabelsError(Exception):
    """Raised when a batch create fails mid-way.

    Carries the labels that were created before the failure so the
    caller can report them and decide how to proceed. The triggering
    API error is preserved as ``__cause__``.
    """

    def __init__(self, created: list[dict], failed_index: int) -> None:
        super().__init__(
            f'create failed at label index {failed_index} '
            f'after {len(created)} succeeded',
        )
        self.created = created
        self.failed_index = failed_index


def list_labels(creds: Credentials) -> list[dict]:
    service = gmail.build_service(creds)
    return gmail.list_user_labels(service)


def create_labels(
    creds: Credentials,
    label_dicts: list[dict],
) -> list[dict]:
    service = gmail.build_service(creds)
    created: list[dict] = []
    for index, label_dict in enumerate(label_dicts):
        try:
            created.append(gmail.create_label(service, label_dict))
        except HttpError as exc:
            raise CreateLabelsError(created, failed_index=index) from exc
    return created
