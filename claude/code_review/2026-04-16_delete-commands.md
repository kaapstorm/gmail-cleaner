# Code Review: delete-query and delete-label commands

**Date:** 2026-04-16
**Branch:** `nh/delete`
**Scope:** Implementation of two bulk-delete commands and the supporting `gmail` module additions.

Files reviewed:
- `gmail_cleaner/gmail.py` (new helpers: `_with_retry`, `_iter_message_ids`, `_batch_delete`, `_delete_message_batches`, `scan_for_messages`, `find_label`, `delete_label_completely`, `delete_messages_matching`, `_list_filters`, `_delete_filter`, `_delete_label_by_id`)
- `gmail_cleaner/commands/delete_label.py`
- `gmail_cleaner/commands/delete_query.py`
- `gmail_cleaner/commands/_progress.py`
- `gmail_cleaner/cli.py`
- `tests/test_gmail.py`, `tests/commands/test_delete_label.py`, `tests/commands/test_delete_query.py`

---

## Summary

The branch is solid: thin Typer commands delegate cleanly to a cohesive `gmail` module, pagination/batching/retry are factored into small helpers, progress reporting is injected as a callback, and the test suite is thorough with parametrized cases and a `no_sleep` fixture. Reviewers found no critical or security issues. The one real concern is partial-failure semantics in the multi-step `delete_label_completely`; everything else is polish.

## Findings

| #  | Sev | Finding                                                                                                                                                                   | Location                                                            |
|----|-----|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------|---------------------------------------------------------------------|
| 1  | 🟠  | `delete_label_completely` has undocumented partial-failure semantics; filter count is pre-counted, not counted-on-success                                                 | `gmail_cleaner/gmail.py:230-252`                                    |
| 2  | 🟡  | Confirmation prompt built on `resultSizeEstimate`; deletion bypasses Trash with no dry-run or audit of deleted IDs                                                        | `commands/delete_query.py:25-35`, `gmail.py:57-63`                  |
| 3  | 🟡  | Orchestration + business rule ("filters matching this label") live inside the data-access module                                                                          | `gmail.py:230-252`                                                  |
| 4  | 🟡  | `_with_retry`: broad `except Exception`, bare `assert`, `(0.0, *_DELAYS)` sentinel, ignores `Retry-After`, inconsistent coverage (paginated `list`/`list_next` unwrapped) | `gmail.py:9-37`, `40-54`                                            |
| 5  | 🟡  | `format_progress` is misnamed (prints, returns `None`) and lives in its own 4-line module                                                                                 | `commands/_progress.py:4-8`                                         |
| 6  | 🟡  | Positional tuple returns (`find_label`, `scan_for_messages`, `delete_label_completely`) are fragile; `has_messages` is returned then ignored                              | `gmail.py:163-173, 205-227, 230-252`; `commands/delete_label.py:29` |
| 7  | 🟡  | `build_service(creds)` rebuilt in every public function — no reuse, harder to compose/test                                                                                | `gmail.py` throughout                                               |
| 8  | 💡  | Inconsistent type annotations on `creds`/`service`; public helpers lack docstrings describing tuple return shapes                                                         | `gmail.py` (new additions)                                          |
| 9  | 💡  | Peek-for-results logic duplicated across `scan_for_messages`, `find_label`, and `_iter_message_ids`                                                                       | `gmail.py:163-173, 205-227`                                         |
| 10 | 💡  | `q=f'label:{label_id}'` works but `labelIds=[label_id]` is the documented, name-safe form                                                                                 | `gmail.py:217, 240`                                                 |
| 11 | 💡  | Terse names (`msgs`, `fs`, `mid`, `f`) and undocumented magic constants (`_LIST_PAGE_SIZE`, `_DELETE_BATCH_SIZE`, `_RETRY_DELAYS`)                                        | `commands/delete_label.py:41`; `gmail.py:9-11, 74-80, 244-250`      |

Severity key: 🔴 Critical · 🟠 Major · 🟡 Minor · 💡 Suggestion

## 🔵 Design Observations

Two threads run through most findings.

**First**, `gmail.py` is drifting from "thin API wrapper" toward "orchestrator + domain model": `delete_label_completely` composes three destructive operations and encodes the "which filters belong to this label" rule, and `find_label` / `scan_for_messages` do peek-style analysis. A small `gmail_cleaner/labels.py` (or `operations.py`) that consumes a passed-in `service` would restore the layering and naturally let `build_service` be called once per command.

**Second**, the module still passes raw `dict`s and positional tuples across its public surface — fine at this size, but with three such shapes already (`find_label`, `scan_for_messages`, `delete_label_completely` returns), it's worth a couple of small `NamedTuple`s now before callers calcify.

## ✅ What's Working Well

- Clean separation between CLI commands and the Gmail helpers; commands are short and read top-to-bottom.
- `_delete_message_batches` is a genuinely nice abstraction — generator in, callback progress out, shared between both commands.
- The `no_sleep` fixture + parametrized retry tests keep the suite fast and exhaustive.
- Confirmation-gated destructive actions with a `--force` escape hatch — exactly the right UX.
