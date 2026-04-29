import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from google.auth.exceptions import RefreshError, TransportError
from testsweet import catch_exceptions, test

import gmail_cleaner.auth as auth


@test
def get_credentials_path_default():
    env = {k: v for k, v in os.environ.items() if k != 'XDG_CONFIG_HOME'}
    with patch.dict('os.environ', env, clear=True):
        result = auth.get_credentials_path()
    assert (
        result
        == Path.home() / '.config' / 'gmail-cleaner' / 'credentials.json'
    )


@test
def get_credentials_path_custom_xdg():
    with patch.dict('os.environ', {'XDG_CONFIG_HOME': '/custom/config'}):
        result = auth.get_credentials_path()
    assert result == Path('/custom/config/gmail-cleaner/credentials.json')


@test
def get_token_path_default():
    env = {k: v for k, v in os.environ.items() if k != 'XDG_CONFIG_HOME'}
    with patch.dict('os.environ', env, clear=True):
        result = auth.get_token_path()
    assert result == Path.home() / '.config' / 'gmail-cleaner' / 'token.json'


@test
def get_token_path_custom_xdg():
    with patch.dict('os.environ', {'XDG_CONFIG_HOME': '/custom/config'}):
        result = auth.get_token_path()
    assert result == Path('/custom/config/gmail-cleaner/token.json')


@test
def save_token_writes_json():
    with tempfile.TemporaryDirectory() as tmp:
        token_path = Path(tmp) / 'subdir' / 'token.json'
        mock_creds = MagicMock()
        mock_creds.to_json.return_value = '{"token": "abc"}'
        with patch(
            'gmail_cleaner.auth.get_token_path', return_value=token_path
        ):
            auth.save_token(mock_creds)
        assert token_path.exists()
        assert json.loads(token_path.read_text()) == {'token': 'abc'}


@test
def save_token_sets_owner_only_permissions():
    with tempfile.TemporaryDirectory() as tmp:
        token_path = Path(tmp) / 'token.json'
        mock_creds = MagicMock()
        mock_creds.to_json.return_value = '{}'
        with patch(
            'gmail_cleaner.auth.get_token_path', return_value=token_path
        ):
            auth.save_token(mock_creds)
        # Owner read/write only — no group or other access at any point.
        assert token_path.stat().st_mode & 0o777 == 0o600


@test
def save_token_tightens_permissions_on_preexisting_file():
    with tempfile.TemporaryDirectory() as tmp:
        token_path = Path(tmp) / 'token.json'
        token_path.write_text('{}')
        token_path.chmod(0o644)
        mock_creds = MagicMock()
        mock_creds.to_json.return_value = '{}'
        with patch(
            'gmail_cleaner.auth.get_token_path', return_value=token_path
        ):
            auth.save_token(mock_creds)
        assert token_path.stat().st_mode & 0o777 == 0o600


@test
def save_token_creates_parent_dirs():
    with tempfile.TemporaryDirectory() as tmp:
        token_path = Path(tmp) / 'nested' / 'dirs' / 'token.json'
        mock_creds = MagicMock()
        mock_creds.to_json.return_value = '{}'
        with patch(
            'gmail_cleaner.auth.get_token_path', return_value=token_path
        ):
            auth.save_token(mock_creds)
        assert token_path.exists()


@test
def delete_token_removes_file():
    with tempfile.TemporaryDirectory() as tmp:
        token_path = Path(tmp) / 'token.json'
        token_path.write_text('{}')
        with patch(
            'gmail_cleaner.auth.get_token_path', return_value=token_path
        ):
            auth.delete_token()
        assert not token_path.exists()


@test
def delete_token_idempotent():
    with tempfile.TemporaryDirectory() as tmp:
        token_path = Path(tmp) / 'token.json'
        # file does not exist — should not raise
        with patch(
            'gmail_cleaner.auth.get_token_path', return_value=token_path
        ):
            auth.delete_token()


@test
def load_token_returns_none_when_no_file():
    with tempfile.TemporaryDirectory() as tmp:
        token_path = Path(tmp) / 'token.json'
        with patch(
            'gmail_cleaner.auth.get_token_path', return_value=token_path
        ):
            result = auth.load_token()
        assert result is None


@test
def load_token_returns_none_on_corrupt_file():
    with tempfile.TemporaryDirectory() as tmp:
        token_path = Path(tmp) / 'token.json'
        token_path.write_text('not valid json{')
        with patch(
            'gmail_cleaner.auth.get_token_path', return_value=token_path
        ):
            result = auth.load_token()
        assert result is None


@test
def load_token_returns_valid_credentials():
    with tempfile.TemporaryDirectory() as tmp:
        token_path = Path(tmp) / 'token.json'
        token_path.write_text('{}')
        mock_creds = MagicMock()
        mock_creds.valid = True
        with patch(
            'gmail_cleaner.auth.get_token_path', return_value=token_path
        ):
            with patch(
                'gmail_cleaner.auth.Credentials.from_authorized_user_file',
                return_value=mock_creds,
            ):
                result = auth.load_token()
        assert result is mock_creds


@test
def load_token_refreshes_expired_credentials():
    with tempfile.TemporaryDirectory() as tmp:
        token_path = Path(tmp) / 'token.json'
        token_path.write_text('{}')
        mock_creds = MagicMock()
        mock_creds.valid = False
        mock_creds.expired = True
        mock_creds.refresh_token = 'a_refresh_token'
        mock_creds.to_json.return_value = '{}'
        with patch(
            'gmail_cleaner.auth.get_token_path', return_value=token_path
        ):
            with patch(
                'gmail_cleaner.auth.Credentials.from_authorized_user_file',
                return_value=mock_creds,
            ):
                with patch('gmail_cleaner.auth.Request'):
                    result = auth.load_token()
        assert result is mock_creds
        mock_creds.refresh.assert_called_once()


@test
def load_token_returns_none_on_refresh_error():
    with tempfile.TemporaryDirectory() as tmp:
        token_path = Path(tmp) / 'token.json'
        token_path.write_text('{}')
        mock_creds = MagicMock()
        mock_creds.valid = False
        mock_creds.expired = True
        mock_creds.refresh_token = 'a_refresh_token'
        mock_creds.refresh.side_effect = RefreshError('Token revoked')
        with patch(
            'gmail_cleaner.auth.get_token_path', return_value=token_path
        ):
            with patch(
                'gmail_cleaner.auth.Credentials.from_authorized_user_file',
                return_value=mock_creds,
            ):
                with patch('gmail_cleaner.auth.Request'):
                    result = auth.load_token()
        assert result is None


@test
def load_token_propagates_transport_error():
    with tempfile.TemporaryDirectory() as tmp:
        token_path = Path(tmp) / 'token.json'
        token_path.write_text('{}')
        mock_creds = MagicMock()
        mock_creds.valid = False
        mock_creds.expired = True
        mock_creds.refresh_token = 'a_refresh_token'
        mock_creds.refresh.side_effect = TransportError('Network down')
        with patch(
            'gmail_cleaner.auth.get_token_path', return_value=token_path
        ):
            with patch(
                'gmail_cleaner.auth.Credentials.from_authorized_user_file',
                return_value=mock_creds,
            ):
                with patch('gmail_cleaner.auth.Request'):
                    with catch_exceptions() as excs:
                        auth.load_token()
        assert type(excs[0]) is TransportError


@test
def run_oauth_flow_returns_credentials():
    with tempfile.TemporaryDirectory() as tmp:
        creds_path = Path(tmp) / 'credentials.json'
        mock_flow = MagicMock()
        mock_creds = MagicMock()
        mock_flow.run_local_server.return_value = mock_creds
        with patch(
            'gmail_cleaner.auth.get_credentials_path', return_value=creds_path
        ):
            with patch(
                'gmail_cleaner.auth.InstalledAppFlow.from_client_secrets_file',
                return_value=mock_flow,
            ) as mock_flow_cls:
                result = auth.run_oauth_flow()
        mock_flow_cls.assert_called_once_with(str(creds_path), auth.SCOPES)
        mock_flow.run_local_server.assert_called_once_with(port=0)
        assert result is mock_creds
