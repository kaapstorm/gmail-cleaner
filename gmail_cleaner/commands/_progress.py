import sys


def report_progress(total_estimate: int, deleted: int) -> None:
    print(
        f'Deleted {deleted:,} of ~{total_estimate:,} messages...',
        file=sys.stderr,
    )
