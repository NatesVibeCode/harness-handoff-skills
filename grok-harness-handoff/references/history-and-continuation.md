# Grok history and continuation

## Grok Build CLI: primary local path

Checked installed version: 1.0.0 (3cd0d0cbcebe), stable. Resolve `grok --version` and relevant help; this is a concrete native CLI, distinct from the web product.

```sh
grok sessions list --limit 10
grok sessions search 'selected topic' --limit 10
grok export SESSION_ID /path/to/private/transcript.md
```

Search covers summaries and first prompts, not necessarily full transcript text. Export candidate IDs and inspect relevant turns before concluding there is no match. Retained ingestion code used `~/.grok/sessions/`, but that directory was absent during this audit; use native discovery first and follow current configured storage. Its absence does not mean history is gone.

For deliberate continuation use `grok --cwd /path/to/workspace --resume SESSION_ID`. Headless work supports `--prompt-file /path/to/handoff.txt --output-format json`; combine with the selected resume ID when continuing. `--session-id` names a new session, not an existing one. `--restore-code` changes repository state and is not required for conversation resume. Headless `-p` does not create a worktree merely because `--worktree` was supplied in the checked help.

`grok leader list` and `grok leader info --help` expose running backend discovery. `grok agent` advertises stdio, headless, serve, and leader modes; inspect their actual transport contracts before implementing control. The default leader socket is `~/.grok/leader.sock`; its existence does not establish permission or protocol shape for a guessed message.

Historical result reports record a successful structured-JSON handback after a plain-output/parser mismatch. Another review recorded cancellation or a process lingering after its result was written. Read structured terminal state and artifacts; process survival or parseable JSON alone is not task completion. No new inference was launched in this audit.

## Identify which Grok surface owns the history

Distinguish Grok on the web, Grok within X, API calls, and third-party local clients. A model name does not identify the application that retained its messages.

For the web product, use the authenticated native history UI to search by title/topic, open the selected conversation, and read relevant turns. Record its exact URL or ID, date, and last result. Do not create a public share link merely to read history. The official guide documents a history view, including conversations shared with the account: [Grok user guide](https://docs.x.ai/grok/user-guide).

For Grok within X, inspect that product's own history/export controls; do not assume the grok.com account exposes the same conversation.

## Local clients and exports

For clients other than Grok Build, resolve the executable/package and consult its help or source for persistence. Search that client's application-data directory for session indexes, JSON/JSONL exports, or SQLite databases. Inspect filenames and schemas first, then the selected conversation. For a user-selected export folder, inspect conversation-file structure before interpreting it.

For an API workflow, find the selected application's request/response store or documented retained-response retrieval facility. Follow actual recorded IDs and retention settings; do not assume API credentials provide access to web-product chats. An application may not have persisted its history.

Browser cookies and authentication databases are not transcript discovery mechanisms. Use the signed-in UI or supported export instead of extracting credentials or replaying private endpoints.

## Continue

Continue the exact selected web conversation using its native message composer when sending is requested. For a client/API, use its supported continuation contract and retained context. Report separately whether history was found, read completely, and continued. If records were deleted, expired, or never stored, state the gap precisely; a local filesystem search cannot recover server-only history.
