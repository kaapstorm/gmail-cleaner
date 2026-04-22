from unittest.mock import MagicMock, patch

import pytest
from googleapiclient.errors import HttpError

from gmail_cleaner import labels


def test_list_labels_returns_user_labels():
    creds = MagicMock()
    service = MagicMock()
    user_labels = [{'id': 'L1', 'name': 'A'}, {'id': 'L2', 'name': 'B'}]
    with (
        patch(
            'gmail_cleaner.labels.gmail.build_service', return_value=service
        ),
        patch(
            'gmail_cleaner.labels.gmail.list_user_labels',
            return_value=user_labels,
        ) as mock_list,
    ):
        assert labels.list_labels(creds) == user_labels
    mock_list.assert_called_once_with(service)


def test_create_labels_creates_each_and_returns_created_list():
    creds = MagicMock()
    service = MagicMock()
    inputs = [{'name': 'A'}, {'name': 'B'}]
    outputs = [{'id': 'L1', **inputs[0]}, {'id': 'L2', **inputs[1]}]
    with (
        patch(
            'gmail_cleaner.labels.gmail.build_service', return_value=service
        ),
        patch(
            'gmail_cleaner.labels.gmail.create_label',
            side_effect=outputs,
        ) as mock_create,
    ):
        assert labels.create_labels(creds, inputs) == outputs
    assert mock_create.call_count == 2


def test_create_labels_midbatch_failure_reports_partial():
    creds = MagicMock()
    service = MagicMock()
    good = {'id': 'L1', 'name': 'A'}
    err = HttpError(MagicMock(status=409), b'label exists')
    inputs = [{'name': 'A'}, {'name': 'A'}]
    with (
        patch(
            'gmail_cleaner.labels.gmail.build_service', return_value=service
        ),
        patch(
            'gmail_cleaner.labels.gmail.create_label',
            side_effect=[good, err],
        ),
        pytest.raises(labels.CreateLabelsError) as exc_info,
    ):
        labels.create_labels(creds, inputs)
    assert exc_info.value.created == [good]
    assert exc_info.value.failed_index == 1
    assert exc_info.value.__cause__ is err


def test_create_labels_empty_input_returns_empty_list():
    creds = MagicMock()
    with patch(
        'gmail_cleaner.labels.gmail.build_service',
        return_value=MagicMock(),
    ):
        assert labels.create_labels(creds, []) == []
