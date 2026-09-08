# Antigravity history and continuation

Evidence: adapted from installed agent CLI 1.1.26 help and local storage inspection notes. CLI, desktop, and IDE can have separate stores.

## Discover and read

Resolve `command -v agy`, `agy --version`, and `agy --help`. Match the agent binary rather than assuming an IDE launcher has the same commands.

Observed CLI summary cache: `~/.gemini/antigravity-cli/conversation_summaries.db`.

```sh
sqlite3 -readonly "$HOME/.gemini/antigravity-cli/conversation_summaries.db" '.schema conversation_summaries'
```

After confirming schema, filter by exact conversation ID, title, or workspace. Useful fields are `conversation_id, title, preview, workspace_uris, project_id, parent_conversation_id, app_data_dir, last_modified_time, status, not_fully_idle, killed`. Limit results and use parameters for search input. Preserve `app_data_dir`: a single cache can include multiple application origins. Cached status does not establish current process state.

Candidate retained roots:

- `~/.gemini/antigravity-cli/conversations/` and `brain/`.
- `~/.gemini/antigravity/conversations/` and `brain/`.

Prefer a returned `log_uri`. An observed readable child transcript is `brain/CONVERSATION_ID/.system_generated/logs/transcript.jsonl`. List only the selected conversation's artifacts and read relevant text. Conversation databases can store `steps` as binary payloads; do not treat a strings dump as a complete transcript. Inspect schema and use a native decoder/view when needed.

## Continue or send

Interactive `/resume` selects retained conversations. An exact `--conversation ID` continues context through a new process; it is not a mailbox for an active process. Check workspace and associated project before continuation. `--continue` can pick the wrong session during concurrent work.

For a caller-owned multi-turn process, the checked CLI supports:

```sh
agy --input-format stream-json --output-format stream-json
```

Keep its stdin open and obtain the current input message contract from installed help/documentation before writing messages. Do not add an initial `-p` to this shape. Native child messaging belongs to the owning parent's actual tool schema. `agy agents` lists definitions, not every live child. No `agy export` or `agy sessions list` was present in the checked version.

Sources: [CLI reference](https://antigravity.google/docs/cli/reference), [conversations](https://antigravity.google/docs/cli/conversations/), [projects](https://antigravity.google/docs/cli/projects/).

