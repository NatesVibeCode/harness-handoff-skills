# Cursor history and continuation

## Separate CLI, editor, and remote agents

Resolve the installed `cursor-agent` or `agent` binary and inspect its version/help. Do not assume an executable named `agent` belongs to Cursor without checking provenance. The editor launcher alone does not establish an agent CLI.

Documented CLI discovery is `cursor-agent ls`; check whether the installed implementation opens an interactive resume picker. Inspect without selecting when only lookup is requested. Deliberate continuation uses `cursor-agent --resume=CHAT_ID`. Do not assume an editor conversation ID is accepted by the CLI.

Sources: [CLI overview](https://docs.cursor.com/en/cli/overview), [parameters](https://docs.cursor.com/en/cli/reference/parameters). Installed help governs when documentation redirects or differs.

## Discover local editor history

The following are search candidates based on the editor's application-data layout, not stable transcript APIs:

- macOS: `~/Library/Application Support/Cursor/User/`.
- Linux: `${XDG_CONFIG_HOME:-$HOME/.config}/Cursor/User/`.
- Windows: `%APPDATA%\\Cursor\\User\\`.

Resolve a custom user-data directory or profile from the selected application when present. Under that root, inspect filenames in `workspaceStorage/`, `globalStorage/`, and selected profiles. Look for `workspace.json` to map hashed workspace directories to actual repositories and for `state.vscdb` databases. Check `~/.cursor/` for a separate CLI store only when it exists; discover its layout rather than assuming editor storage is shared.

Open candidate databases read-only and inspect tables first:

```sh
sqlite3 -readonly /path/to/state.vscdb '.schema'
```

For a confirmed key/value table, enumerate a bounded set of key names matching chat, composer, conversation, or bubble; inspect selected values only after mapping workspace/session identity. Discover actual table and column names before querying. JSON metadata may reference message records elsewhere; follow those exact IDs rather than reporting headers as a full transcript. Binary or missing data should be reported as incomplete and read through the native history UI/export when available.

These database details are implementation-dependent discovery hints, not a verified parser or guaranteed storage contract. Never modify editor databases to resume a chat. Cloud agents may require the corresponding native remote history surface even when local stores are empty.

