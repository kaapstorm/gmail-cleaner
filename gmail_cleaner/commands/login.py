import typer

from gmail_cleaner import auth, gmail


def login():
    creds = auth.load_token()
    if creds is not None:
        typer.echo(f'Already logged in as {gmail.get_user_email(creds)}')
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
    typer.echo(f'Logged in as {gmail.get_user_email(creds)}')
