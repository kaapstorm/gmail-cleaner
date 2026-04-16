import sys


def format_progress(total_estimate: int, deleted: int) -> None:
    print(
        f'Deleted {deleted:,} of ~{total_estimate:,} messages...',
        file=sys.stderr,
    )
