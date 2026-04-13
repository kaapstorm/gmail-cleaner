import os
from pathlib import Path

SCOPES = [
    'https://mail.google.com/',
    'https://www.googleapis.com/auth/gmail.settings.basic',
]


def _config_dir() -> Path:
    xdg = os.environ.get('XDG_CONFIG_HOME', '~/.config')
    return Path(xdg).expanduser() / 'gmail-cleaner'


def get_credentials_path() -> Path:
    return _config_dir() / 'credentials.json'


def get_token_path() -> Path:
    return _config_dir() / 'token.json'
