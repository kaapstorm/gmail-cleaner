import functools

import typer

from gmail_cleaner import auth, gmail
from gmail_cleaner.commands._progress import format_progress


def delete_label(
    label_name: str = typer.Argument(
        ...,
        help='Name of the label to delete.',
    ),
    force: bool = typer.Option(
        False,
        '--force',
        help='Skip confirmation prompt.',
    ),
) -> None:
    creds = auth.load_token()
    if creds is None:
        typer.echo('Not logged in')
        raise typer.Exit(1)

    result = gmail.find_label(creds, label_name)
    if result is None:
        typer.echo(f"Label '{label_name}' not found")
        raise typer.Exit(1)
    label, estimate, _has_messages = result

    if not force:
        typer.confirm(
            f'About {estimate:,} emails whose labels include '
            f"'{label_name}' will be permanently deleted, along with "
            f"filters for '{label_name}' and the '{label_name}' label."
            f'\nProceed?',
            abort=True,
        )

    on_progress = functools.partial(format_progress, estimate)
    msgs, fs = gmail.delete_label_completely(
        creds,
        label,
        on_progress=on_progress,
    )
    typer.echo(
        f"Deleted {msgs:,} messages, {fs} filters, and label '{label_name}'.",
        err=True,
    )
