import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from google.auth.exceptions import RefreshError, TransportError

import gmail_cleaner.auth as auth
from tests.fixtures import tmp_dir
from unmagic import use


def test_get_credentials_path_default():
    env = {k: v for k, v in os.environ.items() if k != 'XDG_CONFIG_HOME'}
    with patch.dict('os.environ', env, clear=True):
        result = auth.get_credentials_path()
    assert result == Path.home() / '.config' / 'gmail-cleaner' / 'credentials.json'


def test_get_credentials_path_custom_xdg():
    with patch.dict('os.environ', {'XDG_CONFIG_HOME': '/custom/config'}):
        result = auth.get_credentials_path()
    assert result == Path('/custom/config/gmail-cleaner/credentials.json')


def test_get_token_path_default():
    env = {k: v for k, v in os.environ.items() if k != 'XDG_CONFIG_HOME'}
    with patch.dict('os.environ', env, clear=True):
        result = auth.get_token_path()
    assert result == Path.home() / '.config' / 'gmail-cleaner' / 'token.json'


def test_get_token_path_custom_xdg():
    with patch.dict('os.environ', {'XDG_CONFIG_HOME': '/custom/config'}):
        result = auth.get_token_path()
    assert result == Path('/custom/config/gmail-cleaner/token.json')


@use(tmp_dir)
def test_save_token_writes_json():
    d = tmp_dir()
    token_path = d / 'subdir' / 'token.json'
    mock_creds = MagicMock()
    mock_creds.to_json.return_value = '{"token": "abc"}'
    with patch('gmail_cleaner.auth.get_token_path', return_value=token_path):
        auth.save_token(mock_creds)
    assert token_path.exists()
    assert json.loads(token_path.read_text()) == {'token': 'abc'}


@use(tmp_dir)
def test_save_token_sets_owner_only_permissions():
    d = tmp_dir()
    token_path = d / 'token.json'
    mock_creds = MagicMock()
    mock_creds.to_json.return_value = '{}'
    with patch('gmail_cleaner.auth.get_token_path', return_value=token_path):
        auth.save_token(mock_creds)
    # Owner read/write only — no group or other access at any point.
    assert token_path.stat().st_mode & 0o777 == 0o600


@use(tmp_dir)
def test_save_token_tightens_permissions_on_preexisting_file():
    d = tmp_dir()
    token_path = d / 'token.json'
    token_path.write_text('{}')
    token_path.chmod(0o644)
    mock_creds = MagicMock()
    mock_creds.to_json.return_value = '{}'
    with patch('gmail_cleaner.auth.get_token_path', return_value=token_path):
        auth.save_token(mock_creds)
    assert token_path.stat().st_mode & 0o777 == 0o600


@use(tmp_dir)
def test_save_token_creates_parent_dirs():
    d = tmp_dir()
    token_path = d / 'nested' / 'dirs' / 'token.json'
    mock_creds = MagicMock()
    mock_creds.to_json.return_value = '{}'
    with patch('gmail_cleaner.auth.get_token_path', return_value=token_path):
        auth.save_token(mock_creds)
    assert token_path.exists()


@use(tmp_dir)
def test_delete_token_removes_file():
    d = tmp_dir()
    token_path = d / 'token.json'
    token_path.write_text('{}')
    with patch('gmail_cleaner.auth.get_token_path', return_value=token_path):
        auth.delete_token()
    assert not token_path.exists()


@use(tmp_dir)
def test_delete_token_idempotent():
    d = tmp_dir()
    token_path = d / 'token.json'
    # file does not exist — should not raise
    with patch('gmail_cleaner.auth.get_token_path', return_value=token_path):
        auth.delete_token()


@use(tmp_dir)
def test_load_token_returns_none_when_no_file():
    d = tmp_dir()
    token_path = d / 'token.json'
    with patch('gmail_cleaner.auth.get_token_path', return_value=token_path):
        result = auth.load_token()
    assert result is None


@use(tmp_dir)
def test_load_token_returns_none_on_corrupt_file():
    d = tmp_dir()
    token_path = d / 'token.json'
    token_path.write_text('not valid json{')
    with patch('gmail_cleaner.auth.get_token_path', return_value=token_path):
        result = auth.load_token()
    assert result is None


@use(tmp_dir)
def test_load_token_returns_valid_credentials():
    d = tmp_dir()
    token_path = d / 'token.json'
    token_path.write_text('{}')
    mock_creds = MagicMock()
    mock_creds.valid = True
    with patch('gmail_cleaner.auth.get_token_path', return_value=token_path):
        with patch(
            'gmail_cleaner.auth.Credentials.from_authorized_user_file',
            return_value=mock_creds,
        ):
            result = auth.load_token()
    assert result is mock_creds


@use(tmp_dir)
def test_load_token_refreshes_expired_credentials():
    d = tmp_dir()
    token_path = d / 'token.json'
    token_path.write_text('{}')
    mock_creds = MagicMock()
    mock_creds.valid = False
    mock_creds.expired = True
    mock_creds.refresh_token = 'a_refresh_token'
    mock_creds.to_json.return_value = '{}'
    with patch('gmail_cleaner.auth.get_token_path', return_value=token_path):
        with patch(
            'gmail_cleaner.auth.Credentials.from_authorized_user_file',
            return_value=mock_creds,
        ):
            with patch('gmail_cleaner.auth.Request'):
                result = auth.load_token()
    assert result is mock_creds
    mock_creds.refresh.assert_called_once()


@use(tmp_dir)
def test_load_token_returns_none_on_refresh_error():
    d = tmp_dir()
    token_path = d / 'token.json'
    token_path.write_text('{}')
    mock_creds = MagicMock()
    mock_creds.valid = False
    mock_creds.expired = True
    mock_creds.refresh_token = 'a_refresh_token'
    mock_creds.refresh.side_effect = RefreshError('Token revoked')
    with patch('gmail_cleaner.auth.get_token_path', return_value=token_path):
        with patch(
            'gmail_cleaner.auth.Credentials.from_authorized_user_file',
            return_value=mock_creds,
        ):
            with patch('gmail_cleaner.auth.Request'):
                result = auth.load_token()
    assert result is None


@use(tmp_dir)
def test_load_token_propagates_transport_error():
    d = tmp_dir()
    token_path = d / 'token.json'
    token_path.write_text('{}')
    mock_creds = MagicMock()
    mock_creds.valid = False
    mock_creds.expired = True
    mock_creds.refresh_token = 'a_refresh_token'
    mock_creds.refresh.side_effect = TransportError('Network down')
    with patch('gmail_cleaner.auth.get_token_path', return_value=token_path):
        with patch(
            'gmail_cleaner.auth.Credentials.from_authorized_user_file',
            return_value=mock_creds,
        ):
            with patch('gmail_cleaner.auth.Request'):
                with pytest.raises(TransportError):
                    auth.load_token()


@use(tmp_dir)
def test_run_oauth_flow_returns_credentials():
    d = tmp_dir()
    creds_path = d / 'credentials.json'
    mock_flow = MagicMock()
    mock_creds = MagicMock()
    mock_flow.run_local_server.return_value = mock_creds
    with patch('gmail_cleaner.auth.get_credentials_path', return_value=creds_path):
        with patch(
            'gmail_cleaner.auth.InstalledAppFlow.from_client_secrets_file',
            return_value=mock_flow,
        ) as mock_flow_cls:
            result = auth.run_oauth_flow()
    mock_flow_cls.assert_called_once_with(str(creds_path), auth.SCOPES)
    mock_flow.run_local_server.assert_called_once_with(port=0)
    assert result is mock_creds
