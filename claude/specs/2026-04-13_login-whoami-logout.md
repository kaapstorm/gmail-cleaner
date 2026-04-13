# Design: `login`, `whoami`, and `logout` commands

## Overview

Implement the three authentication commands for the `gmc` CLI tool, establishing
the credential management foundation that all other commands will build on.


## File structure

```
gmail_cleaner/
  __init__.py
  auth.py               # credential paths, OAuth flow, token load/save/delete
  cli.py                # Typer app, command registration
  commands/
    __init__.py
    login.py
    whoami.py
    logout.py
tests/
  commands/
    test_login.py
    test_whoami.py
    test_logout.py
  test_auth.py
```

`pyproject.toml` changes:
- Add dependencies: `typer`, `google-auth-oauthlib`, `google-api-python-client`
- Add `[project.scripts]`: `gmc = "gmail_cleaner.cli:app"`


## `auth.py`

Owns all credential-related logic. Exposes:

**Constants**

- `SCOPES: list[str]` — scopes requested at login:
  - `https://mail.google.com/` — full mailbox access (read, modify, delete)
  - `https://www.googleapis.com/auth/gmail.settings.basic` — filter read/write

**Path helpers**

- `get_credentials_path() -> Path` — `$XDG_CONFIG_HOME/gmail-cleaner/credentials.json`,
  where `XDG_CONFIG_HOME` defaults to `~/.config`
- `get_token_path() -> Path` — `$XDG_CONFIG_HOME/gmail-cleaner/token.json`

**Credential functions**

- `load_token() -> Credentials | None` — loads token from disk; refreshes if expired;
  returns `None` if no token file exists or if the token cannot be refreshed
- `save_token(creds: Credentials) -> None` — serialises credentials to token.json,
  creating parent directories if needed
- `delete_token() -> None` — deletes token.json if it exists; no-op if absent
- `run_oauth_flow() -> Credentials` — runs `InstalledAppFlow` from `credentials.json`,
  opens browser for user consent, returns new credentials


## Commands

### `login`

1. Call `load_token()`. If valid credentials are returned, print
   `"Already logged in as <email>"` and exit cleanly.
2. Check `credentials.json` exists; if not, print a helpful setup message
   referencing the README and exit with code 1.
3. Call `run_oauth_flow()`, then `save_token()`.
4. Fetch email via `gmail.users().getProfile(userId='me')`.
5. Print `"Logged in as <email>"`.

### `whoami`

1. Call `load_token()`. If `None`, print `"Not logged in"` and exit with code 1.
2. Call `gmail.users().getProfile(userId='me')`.
3. Print the `emailAddress` field.

### `logout`

1. Call `delete_token()`.
2. Print `"Logged out"`. Idempotent — no error if already logged out.


## Error handling

- **`credentials.json` missing** (login): print a friendly setup message, exit 1.
- **No token** (whoami): print `"Not logged in"`, exit 1.
- **Unrefreshable expired token** (load_token): treat as `None` — same as no token.
- **Network/API errors** (login, whoami): let `google-api-python-client` exceptions
  propagate; Typer prints the exception and exits non-zero. No custom wrapping at
  this stage.


## Testing

Tests use `pytest` with `pytest-unmagic`. File I/O and the OAuth flow are mocked —
no real credentials needed.

| File                         | What is tested                                                              |
|------------------------------|-----------------------------------------------------------------------------|
| `test_auth.py`               | `load_token`: no file, valid token, expired+refreshable, expired+revoked    |
|                              | `save_token`: creates parent dirs, writes JSON                              |
|                              | `delete_token`: idempotent                                                  |
| `commands/test_login.py`     | Already-logged-in path, missing credentials.json, successful OAuth flow     |
| `commands/test_whoami.py`    | Not-logged-in path, successful profile fetch                                |
| `commands/test_logout.py`    | Idempotent delete, success message printed                                  |
