import json
import sys
from pathlib import Path

import typer

from gmail_cleaner import auth, filters

STDIN_MARKER = '-'


def _iter_input_lines(source: str):
    if source == STDIN_MARKER:
        for line in sys.stdin:
            yield line
        return
    with Path(source).open('r', encoding='utf-8') as handle:
        for line in handle:
            yield line


def _parse_jsonl(source: str) -> list[dict]:
    records: list[dict] = []
    for lineno, line in enumerate(_iter_input_lines(source), start=1):
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as exc:
            location = 'stdin' if source == STDIN_MARKER else source
            raise typer.BadParameter(
                f'{location}:{lineno}: {exc.msg}',
            ) from exc
    return records


def _print_created(created: list[dict]) -> None:
    for record in created:
        sys.stdout.write(json.dumps(record))
        sys.stdout.write('\n')


def create_filter(
    path: str = typer.Argument(
        ...,
        help='Path to JSONL file of filters, or "-" for stdin.',
    ),
) -> None:
    creds = auth.load_token()
    if creds is None:
        typer.echo('Not logged in')
        raise typer.Exit(1)

    filter_dicts = _parse_jsonl(path)
    try:
        created = filters.create_filters(creds, filter_dicts)
    except filters.CreateFiltersError as exc:
        _print_created(exc.created)
        typer.echo(f'create-filter failed: {exc.__cause__}', err=True)
        raise typer.Exit(1) from exc

    _print_created(created)
