import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import gmail_cleaner.auth as auth
from unmagic import fixture, use


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


@fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


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
