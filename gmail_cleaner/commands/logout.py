import typer

from gmail_cleaner import auth


def logout():
    auth.delete_token()
    typer.echo('Logged out')
