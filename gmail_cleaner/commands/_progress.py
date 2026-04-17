import sys


def report_progress(total_estimate: int, deleted: int) -> None:
    """Write a running delete count to stderr.

    Called repeatedly during long-running deletes. Output goes to
    stderr so it doesn't pollute stdout for callers piping the
    command's output.
    """
    print(
        f'Deleted {deleted:,} of ~{total_estimate:,} messages...',
        file=sys.stderr,
    )
