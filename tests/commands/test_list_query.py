from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from gmail_cleaner.cli import app

runner = CliRunner()


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
        # Under cap: exact count.
        (['m1', 'm2', 'm3'], 3, '3 matches'),
        # Cap hit, low estimate: "100+ matches".
        ([f'm{i}' for i in range(100)], 7, '100+ matches'),
        # Cap hit, high estimate: "About N matches".
        ([f'm{i}' for i in range(100)], 543, 'About 543 matches'),
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
    ids = [f'm{i}' for i in range(15)]
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
    assert lines[2] == ('2026-04-13  Alice <alice@example.com>  Hello world')


@pytest.mark.parametrize(
    'bad_date',
    [
        # parsedate_to_datetime raises TypeError (unparseable garbage).
        'not a real date',
        # parsedate_to_datetime raises ValueError (parseable but invalid).
        'Mon, 99 Abc 2026 14:30:00 -0400',
    ],
)
def test_list_query_falls_back_to_raw_date_on_parse_failure(bad_date):
    mock_creds = MagicMock()
    headers = _headers(bad_date, 'a@x', 'Hi')
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
    assert lines[2].startswith(f'{bad_date}  ')
