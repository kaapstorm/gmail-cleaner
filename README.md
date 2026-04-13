GMail Cleaner
=============

A set of command line tools for cleaning GMail.


Setup
-----

1. Follow the Python quickstart guide to enable the GMail API:
   https://developers.google.com/gmail/api/quickstart/python

2. Download and save the OAuth client credentials in
   `~/.config/gmail-cleaner/credentials.json`. The file must only be
   readable by the user (`chmod 600 ...`) because it contains secret
   values.


Usage
-----

```shell
gmc <command> <options> [--help]
```


Commands
--------

* **login**: Log in. Saves token in `~/.config/gmail-cleaner/token.json`.

* **whoami**: Show authenticated username.

* **logout**: Log out. Deletes `~/.config/gmail-cleaner/token.json`.

* **old-labels**: List labels whose most recent email is older than a
  given age, defaults to two years.

* **delete-label**: Permanently delete all emails with this label,
  delete filters for this label, and delete the label.

* **list-query**: Return a count and a list of the first 10 emails that
  match a given query.

* **delete-query**: Permanently delete all emails that match a given
  query.

* **export-inbox**: Export all emails in Inbox.

* **normalize-filters**: Split filter actions into multiple filters and
  remove duplicates.


### old-labels

Example:

```shell
gmc old-labels --age 2y
```
Options:

* **--age**: The age of the most recent email for a label to be old.
  Defaults to two years ("2y").


### delete-label

> [!WARNING]
> This command is very destructive and cannot be undone.

Example

```shell
gmc delete-label 'MySpace'
```


### list-query

Example

```shell
gmc list-query 'in:MySpace older_than:2y'
```


### delete-query

> [!WARNING]
> This command is very destructive and cannot be undone. Test queries
> first using the **list-query** command.

Example

```shell
gmc delete-query 'in:MySpace older_than:2y'
```
