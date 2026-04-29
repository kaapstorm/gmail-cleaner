GMail Cleaner
=============

A set of command line tools for cleaning GMail.

**GMail Cleaner** is intended to be used alongside an AI agent like
Claude Code. An example prompt might look something like this:

> Read @README.md on how to use GMail Cleaner. I have logged into GMail
> already. Run `export-inbox` to export the metadata about the emails in
> my inbox, and run `list-filters` to see my current filters. Then
> analyze a sample of exported email metadata. Then we can discuss how
> to improve my filters so that only important or actionable emails end
> up in my inbox.


How NOT to use GMail Cleaner
----------------------------

The `export-inbox` command exports email metadata, including the first
30 characters of the content. Some of this metadata (like, who sends
you emails) could possibly be gleaned from LinkedIn. But if you get
emails from people whose identities or email addresses you don't want
to be uploaded to a third party, or where the first 30 characters might
be private, do not ask or allow a third-party AI agent to read the
output of `export-inbox`! For this kind of scenario, use a self-hosted
model like Ollama.


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

* **export-inbox**: Export metadata of all emails in Inbox.

* **list-filters**: List Gmail filters as JSONL.

* **get-filter**: Fetch a single Gmail filter by ID as JSON.

* **create-filter**: Create one or more Gmail filters from a JSONL file
  or stdin.

* **delete-filter**: Delete one or more Gmail filters by ID.

* **list-labels**: List user Gmail labels as JSONL.

* **create-label**: Create one or more Gmail labels from a JSONL file
  or stdin.


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


### export-inbox

Exports one JSON object of metadata about each inbox message to a JSONL
file, suitable for feeding into an LLM to suggest filter or labeling
improvements.

Example

```shell
gmc export-inbox inbox.jsonl
```

Use `-` as the output path to write to stdout:

```shell
gmc export-inbox - | jq '.subject'
```

Metadata includes headers, labels, Gmail snippet, attachment
filenames/sizes. It does not include message bodies or attachment bytes.


### list-filters

Prints all filters as JSONL (one JSON object per line). The output is
safe to pipe into a file, edit, and feed back into `create-filter`.

Example:

```shell
gmc list-filters > filters.jsonl
```


### get-filter

Fetches a single filter by ID and prints it as JSON. Exits non-zero if
the ID is not found.

Example:

```shell
gmc get-filter ABCDEF
```


### create-filter

Reads JSONL of filter objects (one per line) and creates each in Gmail.
Prints the created filters, with their new IDs, as JSONL.

Input objects must not include an `id` field — Gmail assigns IDs.

Examples:

```shell
gmc create-filter filters.jsonl
cat filters.jsonl | gmc create-filter -
```


### delete-filter

Deletes one or more filters by ID. Reports `deleted <id>` or
`not found <id>` per filter on stderr.

Example:

```shell
gmc delete-filter ABCDEF GHIJKL
```


### list-labels

Prints user labels as JSONL (one JSON object per line). System labels
(`INBOX`, `TRASH`, `CATEGORY_*`, etc.) are omitted.

Example:

```shell
gmc list-labels
```


### create-label

Reads JSONL of label objects (one per line) and creates each in Gmail.
Prints the created labels, with their new IDs, as JSONL. The smallest
valid input is `{"name": "MyLabel"}`; other Gmail label fields
(`messageListVisibility`, `labelListVisibility`, `color`) are accepted
as-is.

Examples:

```shell
gmc create-label labels.jsonl
echo '{"name": "AWS-Alerts"}' | gmc create-label -
```
