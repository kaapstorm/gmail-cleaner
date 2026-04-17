import functools

import typer

from gmail_cleaner import auth, cleanup
from gmail_cleaner.commands._progress import echo_sample, report_progress


def _render_filter_criteria(criteria: dict) -> str:
    if not criteria:
        return '(no criteria)'
    parts: list[str] = []
    for key, value in criteria.items():
        if key == 'hasAttachment':
            if value:
                parts.append('has:attachment')
        elif key == 'excludeChats':
            if value:
                parts.append('-in:chats')
        elif key == 'query':
            parts.append(str(value))
        elif key == 'negatedQuery':
            parts.append(f'-({value})')
        else:
            parts.append(f'{key}:{value}')
    return ' AND '.join(parts) if parts else '(no criteria)'


def delete_label(
    label_name: str = typer.Argument(
        ...,
        help='Name of the label to delete.',
    ),
    dry_run: bool = typer.Option(
        False,
        '--dry-run',
        help='Preview matches, filters, and headers without deleting.',
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

    found = cleanup.find_label(creds, label_name)
    if found is None:
        typer.echo(f"Label '{label_name}' not found")
        raise typer.Exit(1)

    if dry_run:
        preview = cleanup.preview_label(creds, found.label)
        typer.echo('DRY RUN — nothing will be deleted.')
        typer.echo('')
        typer.echo(f"Label '{label_name}': {preview.total:,} messages")
        if preview.filters:
            typer.echo('')
            typer.echo(
                f'Filters that would be removed ({len(preview.filters)}):',
            )
            for filter_record in preview.filters:
                criteria = _render_filter_criteria(
                    filter_record.get('criteria', {}),
                )
                typer.echo(f'  {criteria}')
        if preview.sample_ids:
            typer.echo('')
            echo_sample(creds, preview.sample_ids)
        return

    if not force:
        typer.confirm(
            f'About {found.estimate:,} emails whose labels include '
            f"'{label_name}' will be permanently deleted, along with "
            f"filters for '{label_name}' and the '{label_name}' label."
            f'\nProceed?',
            abort=True,
        )

    on_progress = functools.partial(report_progress, found.estimate)
    result = cleanup.delete_label_completely(
        creds,
        found.label,
        on_progress=on_progress,
    )
    typer.echo(
        f'Deleted {result.messages_deleted:,} messages, '
        f"{result.filters_deleted} filters, and label '{label_name}'.",
        err=True,
    )
