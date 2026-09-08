# OpenCode history and continuation

## Native discovery

Check `opencode --version` and subcommand help. Use `opencode session list` to find sessions and `opencode export SESSION_ID` to read a selected transcript as JSON. Confirm output/redaction flags in installed help. Export into private scratch space when a file is needed.

For deliberate continuation, `opencode --session SESSION_ID` selects context; `--continue` selects the latest instead. An existing backend can be reached with `opencode attach URL --session SESSION_ID` when supported. Resolve its actual address and workspace first. Attaching/resuming can create activity; use exports for inspection.

Source: [official CLI reference](https://opencode.ai/docs/cli/).

## Locate retained history

Documented storage candidates are `~/.local/share/opencode/` on macOS/Linux and `%USERPROFILE%\\.local\\share\\opencode` on Windows. Respect discovered data-root overrides. Consult relevant `opencode debug --help` or `opencode db --help` if advertised by the installed CLI.

Inspect only filenames first. Versions can use SQLite or directory storage; find the actual database or project storage rather than hardcoding a schema. Inspect any discovered database with `sqlite3 -readonly DATABASE '.schema'`, then query session metadata with a limit and export the matching ID natively. Directory-based versions can retain project-specific session/message data under `project/`; inspect the selected project's structure.

Application diagnostics in `log/` are not the conversation transcript. Exclude `auth.json`, which contains authentication data.

Source: [official storage and troubleshooting documentation](https://opencode.ai/docs/troubleshooting/).

## Identify the right session

Match session ID, title, project directory, modification time, and parent/child relationship when available. Compare the selected transcript's final user request and last result to the intended work. Use the configured server's documented session API if local history belongs to a remote backend; an empty local list does not prove that remote history is absent.

