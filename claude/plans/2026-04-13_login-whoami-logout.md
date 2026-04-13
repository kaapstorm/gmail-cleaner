# login / whoami / logout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the `login`, `whoami`, and `logout` subcommands for the `gmc` CLI, backed by OAuth2 credential management using the Gmail API.

**Architecture:** A `gmail_cleaner` package exposes an `auth` module (all credential I/O, OAuth flow) and a `commands` sub-package (one module per command). The Typer app in `cli.py` wires commands together. Tests mock file I/O and Google API calls — no real credentials required.

**Tech Stack:** Python 3.14, Typer, google-api-python-client, google-auth-oauthlib, pytest, pytest-unmagic, ruff, mypy

---

## File map

| Action | Path | Responsibility |
|--------|------|----------------|
| Modify | `pyproject.toml` | Add dependencies and `gmc` entry point |
| Create | `gmail_cleaner/__init__.py` | Package marker |
| Create | `gmail_cleaner/auth.py` | SCOPES, path helpers, token load/save/delete, OAuth flow |
| Create | `gmail_cleaner/cli.py` | Typer app, command registration |
| Create | `gmail_cleaner/commands/__init__.py` | Package marker |
| Create | `gmail_cleaner/commands/login.py` | `login` command |
| Create | `gmail_cleaner/commands/whoami.py` | `whoami` command |
| Create | `gmail_cleaner/commands/logout.py` | `logout` command |
| Create | `tests/__init__.py` | Package marker |
| Create | `tests/test_auth.py` | Tests for `auth.py` |
| Create | `tests/commands/__init__.py` | Package marker |
| Create | `tests/commands/test_login.py` | Tests for `login` command |
| Create | `tests/commands/test_whoami.py` | Tests for `whoami` command |
| Create | `tests/commands/test_logout.py` | Tests for `logout` command |

---

### Task 1: Add dependencies and scaffold the package

**Files:**
- Modify: `pyproject.toml`
- Create: `gmail_cleaner/__init__.py`
- Create: `gmail_cleaner/commands/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/commands/__init__.py`

- [ ] **Step 1: Add dependencies via uv**

```bash
uv add typer google-api-python-client google-auth-oauthlib
```

Expected: `pyproject.toml` `dependencies` updated, `uv.lock` regenerated.

- [ ] **Step 2: Add the `gmc` entry point to `pyproject.toml`**

Add this section after `[project]` (before `[dependency-groups]`):

```toml
[project.scripts]
gmc = "gmail_cleaner.cli:app"
```

- [ ] **Step 3: Create empty package markers**

```bash
mkdir -p gmail_cleaner/commands tests/commands
touch gmail_cleaner/__init__.py gmail_cleaner/commands/__init__.py
touch tests/__init__.py tests/commands/__init__.py
```

- [ ] **Step 4: Verify the package is importable**

```bash
uv run python3 -c "import gmail_cleaner; print('ok')"
```

Expected: `ok`

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml uv.lock gmail_cleaner/ tests/
git commit -m "chore: scaffold gmail_cleaner package with dependencies"
```

---

### Task 2: `auth.py` — path helpers

**Files:**
- Create: `gmail_cleaner/auth.py`
- Create: `tests/test_auth.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_auth.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_auth.py -v
```

Expected: 4 errors — `ModuleNotFoundError` or similar (auth.py does not exist yet).

- [ ] **Step 3: Implement the path helpers in `auth.py`**

Create `gmail_cleaner/auth.py`:

```python
import os
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_auth.py -v
```

Expected: 4 PASSED.

- [ ] **Step 5: Check types and linting**

```bash
uv run mypy gmail_cleaner/auth.py
uv run ruff check gmail_cleaner/auth.py tests/test_auth.py
```

Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add gmail_cleaner/auth.py tests/test_auth.py
git commit -m "feat: add auth path helpers"
```

---

### Task 3: `auth.py` — `save_token` and `delete_token`

**Files:**
- Modify: `gmail_cleaner/auth.py`
- Modify: `tests/test_auth.py`

- [ ] **Step 1: Add the failing tests**

Append to `tests/test_auth.py`:

```python
import json
import tempfile
from unittest.mock import MagicMock

from unmagic import fixture, use


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
```

- [ ] **Step 2: Run tests to verify the new ones fail**

```bash
uv run pytest tests/test_auth.py -v
```

Expected: 4 PASSED (path tests), 4 FAILED (save/delete tests — functions not defined).

- [ ] **Step 3: Implement `save_token` and `delete_token` in `auth.py`**

Append to `gmail_cleaner/auth.py` (after `get_token_path`):

```python

def save_token(creds: Credentials) -> None:
    token_path = get_token_path()
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(creds.to_json())


def delete_token() -> None:
    get_token_path().unlink(missing_ok=True)
```

- [ ] **Step 4: Run tests to verify all pass**

```bash
uv run pytest tests/test_auth.py -v
```

Expected: 8 PASSED.

- [ ] **Step 5: Check types and linting**

```bash
uv run mypy gmail_cleaner/auth.py
uv run ruff check gmail_cleaner/auth.py tests/test_auth.py
```

Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add gmail_cleaner/auth.py tests/test_auth.py
git commit -m "feat: add save_token and delete_token"
```

---

### Task 4: `auth.py` — `load_token`

**Files:**
- Modify: `gmail_cleaner/auth.py`
- Modify: `tests/test_auth.py`

- [ ] **Step 1: Add the failing tests**

Append to `tests/test_auth.py`:

```python
@use(tmp_dir)
def test_load_token_returns_none_when_no_file():
    d = tmp_dir()
    token_path = d / 'token.json'
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
def test_load_token_returns_none_on_refresh_failure():
    d = tmp_dir()
    token_path = d / 'token.json'
    token_path.write_text('{}')
    mock_creds = MagicMock()
    mock_creds.valid = False
    mock_creds.expired = True
    mock_creds.refresh_token = 'a_refresh_token'
    mock_creds.refresh.side_effect = Exception('Token revoked')
    with patch('gmail_cleaner.auth.get_token_path', return_value=token_path):
        with patch(
            'gmail_cleaner.auth.Credentials.from_authorized_user_file',
            return_value=mock_creds,
        ):
            with patch('gmail_cleaner.auth.Request'):
                result = auth.load_token()
    assert result is None
```

- [ ] **Step 2: Run tests to verify the new ones fail**

```bash
uv run pytest tests/test_auth.py -v
```

Expected: 8 PASSED (prior tests), 4 FAILED (load_token not defined).

- [ ] **Step 3: Implement `load_token` in `auth.py`**

Append to `gmail_cleaner/auth.py` (after `delete_token`):

```python

def load_token() -> Credentials | None:
    token_path = get_token_path()
    if not token_path.exists():
        return None
    creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    if creds.valid:
        return creds
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            save_token(creds)
            return creds
        except Exception:
            return None
    return None
```

- [ ] **Step 4: Run tests to verify all pass**

```bash
uv run pytest tests/test_auth.py -v
```

Expected: 12 PASSED.

- [ ] **Step 5: Check types and linting**

```bash
uv run mypy gmail_cleaner/auth.py
uv run ruff check gmail_cleaner/auth.py tests/test_auth.py
```

Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add gmail_cleaner/auth.py tests/test_auth.py
git commit -m "feat: add load_token"
```

---

### Task 5: `auth.py` — `run_oauth_flow`

**Files:**
- Modify: `gmail_cleaner/auth.py`
- Modify: `tests/test_auth.py`

- [ ] **Step 1: Add the failing test**

Append to `tests/test_auth.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_auth.py::test_run_oauth_flow_returns_credentials -v
```

Expected: FAILED — `AttributeError: module 'gmail_cleaner.auth' has no attribute 'run_oauth_flow'`.

- [ ] **Step 3: Implement `run_oauth_flow` in `auth.py`**

Append to `gmail_cleaner/auth.py`:

```python

def run_oauth_flow() -> Credentials:
    flow = InstalledAppFlow.from_client_secrets_file(
        str(get_credentials_path()), SCOPES
    )
    return flow.run_local_server(port=0)
```

- [ ] **Step 4: Run all auth tests to verify they pass**

```bash
uv run pytest tests/test_auth.py -v
```

Expected: 13 PASSED.

- [ ] **Step 5: Check types and linting**

```bash
uv run mypy gmail_cleaner/auth.py
uv run ruff check gmail_cleaner/auth.py tests/test_auth.py
```

Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add gmail_cleaner/auth.py tests/test_auth.py
git commit -m "feat: add run_oauth_flow"
```

---

### Task 6: CLI entry point

**Files:**
- Create: `gmail_cleaner/cli.py`

- [ ] **Step 1: Create `cli.py`**

Create `gmail_cleaner/cli.py`:

```python
import typer

from gmail_cleaner.commands.login import login
from gmail_cleaner.commands.logout import logout
from gmail_cleaner.commands.whoami import whoami

app = typer.Typer()
app.command()(login)
app.command()(whoami)
app.command()(logout)
```

The import will fail until the command modules exist; we will create stubs for the imports to verify the entry point first.

- [ ] **Step 2: Create stub command modules**

Create `gmail_cleaner/commands/login.py`:

```python
def login() -> None:
    pass
```

Create `gmail_cleaner/commands/whoami.py`:

```python
def whoami() -> None:
    pass
```

Create `gmail_cleaner/commands/logout.py`:

```python
def logout() -> None:
    pass
```

- [ ] **Step 3: Verify `gmc --help` works**

```bash
uv run gmc --help
```

Expected output contains: `login`, `whoami`, `logout` listed as commands.

- [ ] **Step 4: Check types and linting**

```bash
uv run mypy gmail_cleaner/cli.py
uv run ruff check gmail_cleaner/cli.py
```

Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add gmail_cleaner/cli.py gmail_cleaner/commands/login.py gmail_cleaner/commands/whoami.py gmail_cleaner/commands/logout.py
git commit -m "feat: add CLI entry point and command stubs"
```

---

### Task 7: `logout` command

**Files:**
- Modify: `gmail_cleaner/commands/logout.py`
- Create: `tests/commands/test_logout.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/commands/test_logout.py`:

```python
from unittest.mock import patch

from typer.testing import CliRunner

from gmail_cleaner.cli import app

runner = CliRunner()


def test_logout_calls_delete_token():
    with patch('gmail_cleaner.auth.delete_token') as mock_delete:
        result = runner.invoke(app, ['logout'])
    assert result.exit_code == 0
    mock_delete.assert_called_once()


def test_logout_prints_logged_out():
    with patch('gmail_cleaner.auth.delete_token'):
        result = runner.invoke(app, ['logout'])
    assert 'Logged out' in result.output


def test_logout_idempotent():
    # delete_token is a no-op if token doesn't exist; logout should still succeed
    with patch('gmail_cleaner.auth.delete_token'):
        result = runner.invoke(app, ['logout'])
    assert result.exit_code == 0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/commands/test_logout.py -v
```

Expected: 3 FAILED — the stub `logout` does nothing.

- [ ] **Step 3: Implement `logout`**

Replace `gmail_cleaner/commands/logout.py` with:

```python
import typer

from gmail_cleaner import auth


def logout() -> None:
    auth.delete_token()
    typer.echo('Logged out')
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/commands/test_logout.py -v
```

Expected: 3 PASSED.

- [ ] **Step 5: Run the full test suite**

```bash
uv run pytest -v
```

Expected: all tests PASSED.

- [ ] **Step 6: Check types and linting**

```bash
uv run mypy gmail_cleaner/commands/logout.py
uv run ruff check gmail_cleaner/commands/logout.py tests/commands/test_logout.py
```

Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add gmail_cleaner/commands/logout.py tests/commands/test_logout.py
git commit -m "feat: implement logout command"
```

---

### Task 8: `whoami` command

**Files:**
- Modify: `gmail_cleaner/commands/whoami.py`
- Create: `tests/commands/test_whoami.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/commands/test_whoami.py`:

```python
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from gmail_cleaner.cli import app

runner = CliRunner()


def test_whoami_not_logged_in_exits_with_error():
    with patch('gmail_cleaner.auth.load_token', return_value=None):
        result = runner.invoke(app, ['whoami'])
    assert result.exit_code == 1


def test_whoami_not_logged_in_prints_message():
    with patch('gmail_cleaner.auth.load_token', return_value=None):
        result = runner.invoke(app, ['whoami'])
    assert 'Not logged in' in result.output


def test_whoami_prints_email():
    mock_creds = MagicMock()
    mock_service = MagicMock()
    mock_service.users().getProfile().execute.return_value = {
        'emailAddress': 'user@example.com'
    }
    with patch('gmail_cleaner.auth.load_token', return_value=mock_creds):
        with patch(
            'gmail_cleaner.commands.whoami.build', return_value=mock_service
        ):
            result = runner.invoke(app, ['whoami'])
    assert result.exit_code == 0
    assert 'user@example.com' in result.output
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/commands/test_whoami.py -v
```

Expected: 3 FAILED — stub `whoami` does nothing.

- [ ] **Step 3: Implement `whoami`**

Replace `gmail_cleaner/commands/whoami.py` with:

```python
import typer
from googleapiclient.discovery import build

from gmail_cleaner import auth


def whoami() -> None:
    creds = auth.load_token()
    if creds is None:
        typer.echo('Not logged in', err=True)
        raise typer.Exit(1)
    service = build('gmail', 'v1', credentials=creds)
    profile = service.users().getProfile(userId='me').execute()
    typer.echo(profile['emailAddress'])
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/commands/test_whoami.py -v
```

Expected: 3 PASSED.

- [ ] **Step 5: Run the full test suite**

```bash
uv run pytest -v
```

Expected: all tests PASSED.

- [ ] **Step 6: Check types and linting**

```bash
uv run mypy gmail_cleaner/commands/whoami.py
uv run ruff check gmail_cleaner/commands/whoami.py tests/commands/test_whoami.py
```

Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add gmail_cleaner/commands/whoami.py tests/commands/test_whoami.py
git commit -m "feat: implement whoami command"
```

---

### Task 9: `login` command

**Files:**
- Modify: `gmail_cleaner/commands/login.py`
- Create: `tests/commands/test_login.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/commands/test_login.py`:

```python
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner
from unmagic import fixture, use

from gmail_cleaner.cli import app

runner = CliRunner()


@fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


def test_login_already_logged_in_prints_message():
    mock_creds = MagicMock()
    mock_service = MagicMock()
    mock_service.users().getProfile().execute.return_value = {
        'emailAddress': 'user@example.com'
    }
    with patch('gmail_cleaner.auth.load_token', return_value=mock_creds):
        with patch(
            'gmail_cleaner.commands.login.build', return_value=mock_service
        ):
            result = runner.invoke(app, ['login'])
    assert result.exit_code == 0
    assert 'Already logged in as user@example.com' in result.output


@use(tmp_dir)
def test_login_missing_credentials_exits_with_error():
    d = tmp_dir()
    creds_path = d / 'credentials.json'
    with patch('gmail_cleaner.auth.load_token', return_value=None):
        with patch(
            'gmail_cleaner.auth.get_credentials_path', return_value=creds_path
        ):
            result = runner.invoke(app, ['login'])
    assert result.exit_code == 1


@use(tmp_dir)
def test_login_missing_credentials_prints_message():
    d = tmp_dir()
    creds_path = d / 'credentials.json'
    with patch('gmail_cleaner.auth.load_token', return_value=None):
        with patch(
            'gmail_cleaner.auth.get_credentials_path', return_value=creds_path
        ):
            result = runner.invoke(app, ['login'])
    assert 'credentials.json not found' in result.output


@use(tmp_dir)
def test_login_success_saves_token_and_prints_email():
    d = tmp_dir()
    creds_path = d / 'credentials.json'
    creds_path.write_text('{}')
    mock_creds = MagicMock()
    mock_service = MagicMock()
    mock_service.users().getProfile().execute.return_value = {
        'emailAddress': 'user@example.com'
    }
    with patch('gmail_cleaner.auth.load_token', return_value=None):
        with patch(
            'gmail_cleaner.auth.get_credentials_path', return_value=creds_path
        ):
            with patch(
                'gmail_cleaner.auth.run_oauth_flow', return_value=mock_creds
            ):
                with patch('gmail_cleaner.auth.save_token') as mock_save:
                    with patch(
                        'gmail_cleaner.commands.login.build',
                        return_value=mock_service,
                    ):
                        result = runner.invoke(app, ['login'])
    assert result.exit_code == 0
    assert 'Logged in as user@example.com' in result.output
    mock_save.assert_called_once_with(mock_creds)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/commands/test_login.py -v
```

Expected: 4 FAILED — stub `login` does nothing.

- [ ] **Step 3: Implement `login`**

Replace `gmail_cleaner/commands/login.py` with:

```python
import typer
from googleapiclient.discovery import build

from gmail_cleaner import auth


def login() -> None:
    creds = auth.load_token()
    if creds is not None:
        service = build('gmail', 'v1', credentials=creds)
        profile = service.users().getProfile(userId='me').execute()
        typer.echo(f"Already logged in as {profile['emailAddress']}")
        return

    if not auth.get_credentials_path().exists():
        typer.echo(
            f'credentials.json not found at {auth.get_credentials_path()}.\n'
            'Follow the setup instructions in README.md to download OAuth '
            'credentials from the Google Cloud Console.',
            err=True,
        )
        raise typer.Exit(1)

    creds = auth.run_oauth_flow()
    auth.save_token(creds)
    service = build('gmail', 'v1', credentials=creds)
    profile = service.users().getProfile(userId='me').execute()
    typer.echo(f"Logged in as {profile['emailAddress']}")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/commands/test_login.py -v
```

Expected: 4 PASSED.

- [ ] **Step 5: Run the full test suite**

```bash
uv run pytest -v
```

Expected: all tests PASSED.

- [ ] **Step 6: Check types and linting**

```bash
uv run mypy gmail_cleaner/commands/login.py
uv run ruff check gmail_cleaner/commands/login.py tests/commands/test_login.py
```

Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add gmail_cleaner/commands/login.py tests/commands/test_login.py
git commit -m "feat: implement login command"
```

---

### Task 10: Final check

- [ ] **Step 1: Run the full test suite**

```bash
uv run pytest -v
```

Expected: all tests PASSED.

- [ ] **Step 2: Run mypy across the whole package**

```bash
uv run mypy gmail_cleaner/
```

Expected: no errors.

- [ ] **Step 3: Run ruff across the whole project**

```bash
uv run ruff check
```

Expected: no errors.

- [ ] **Step 4: Verify the CLI works end-to-end**

```bash
uv run gmc --help
uv run gmc login --help
uv run gmc whoami --help
uv run gmc logout --help
```

Expected: help text for each command is shown with no errors.
