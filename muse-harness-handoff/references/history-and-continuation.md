# Muse history and continuation

## Retained live-test findings

A prior 1.0.3-R2198.1 live test verified parent execution, child creation, and same-child follow-up after fixing command-ID reuse. The model-facing follow-up used `subagent_send_message` with `command_id`, `subagent_id`, `mode: followup`, and `message`. The child recalled context absent from the follow-up and wrote the expected artifact; its result and file were checked. Queue mode against a terminal child failed. These model-tool fields are distinct from MSP wire fields below.

Cross-session CLI ingress still returned `external_agent_ingress_closed` during that test. Successful parent-to-child messaging does not establish arbitrary cross-session delivery.

Evidence: adapted from installed Muse Code 1.0.3-R2198.1 help/schema notes. Confirm version-sensitive syntax with installed help.

## Discover and read

Run `command -v muse`, `muse --version`, and relevant subcommand help. Inspect `muse export --help`, `muse resume --help`, and `muse session-message --help`.

The observed data root is `~/.local/share/muse/`. Resolve overrides from the installed configuration or process before assuming that location. It contains `session-index.db` and `sessions/`. Open the index read-only:

```sh
sqlite3 -readonly "$HOME/.local/share/muse/session-index.db" '.schema sessions'
```

After confirming columns, search `sessions` by title, exact `session_id`, or `workspace_root`; select `session_id, title, workspace_root, session_log_path, updated_at_us`, newest first, with a bounded LIMIT. Use bound parameters for user text. The index is historical metadata, not a live-process list.

Export the selected session with the supported command:

```sh
muse export --session SESSION_UUID --out /path/to/private/transcript.json --redacted
```

Read the relevant exported messages, tool results, timestamps, and lineage. Raw logs may contain transaction frames with JSON strings in `children[].record_json`; prefer export over assuming plain-event JSONL.

An existing native MSP client can use `session/list` and `session/read`. The latter needs `excludeItems: false` for history. List accepts workspace/time filters, limit, and opaque cursor. Discover the exact contract using `muse schema generate-json-schema --out /path/to/private/schema`. Starting `muse serve` creates a host; it does not attach to another process.

## Continue or send

`muse session-message list --json` lists reachable messaging targets, not all historical sessions.

```sh
muse session-message send --target SESSION_UUID --json < /path/to/message.txt
```

There is no `--message` body flag in the checked version. Replies use the real returned token via `--in-reply-to`. `external_agent_ingress_closed` means delivery is unavailable, not that the session is missing. Do not force ingress open.

For deliberate continuation of a stopped session, use `muse --workspace /path/to/workspace resume SESSION_UUID` after checking current help. A fresh `muse exec` is a new run. Do not resume a competing writer.

Muse-owned children use the parent's native tools or schema-defined `subagent/sendMessage` and `subagent/followupTask`. Preserve parent, child, session, turn, and command identities separately; distinct mutations need distinct command IDs. `subagent/readResult` consumes state and is not passive history inspection.
