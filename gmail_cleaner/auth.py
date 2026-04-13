import os
from pathlib import Path

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

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


def save_token(creds: Credentials) -> None:
    token_path = get_token_path()
    token_path.parent.mkdir(parents=True, exist_ok=True)
    # Create the file with 0o600 atomically — writing then chmod-ing
    # leaves a brief window where the token is world-readable.
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    fd = os.open(token_path, flags, 0o600)
    with os.fdopen(fd, 'w') as f:
        f.write(creds.to_json())
    # If the file pre-existed with broader perms, the O_CREAT mode is
    # ignored — enforce 0o600 explicitly to cover that case.
    token_path.chmod(0o600)


def delete_token() -> None:
    get_token_path().unlink(missing_ok=True)


def load_token() -> Credentials | None:
    token_path = get_token_path()
    if not token_path.exists():
        return None
    try:
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    except (ValueError, OSError):
        # Corrupt or unreadable token file — treat as no token. The user
        # can recover by running `gmc login` again.
        return None
    if creds.valid:
        return creds
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except RefreshError:
            # Token was revoked or is otherwise unrefreshable — treat as
            # no token. Transport/network errors are not caught here;
            # they propagate so the user sees the real failure instead
            # of a misleading "Not logged in".
            return None
        save_token(creds)
        return creds
    return None
