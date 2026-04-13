import os
from pathlib import Path
from unittest.mock import patch

import gmail_cleaner.auth as auth


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
