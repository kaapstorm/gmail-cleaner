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

    creds_path = auth.get_credentials_path()
    if not creds_path.exists():
        typer.echo(
            f'credentials.json not found at {creds_path}.\n'
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
