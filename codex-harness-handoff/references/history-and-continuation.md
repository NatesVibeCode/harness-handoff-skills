# Codex discovery and handoff

Checked installed CLI: 0.153.2. Recovered historical notes cover one-shot delegation, linked-worktree sandbox problems, and app-server versus process-resume distinctions.

## Read sessions without running them

Resolve `command -v codex`, `codex --version`, `codex resume --help`, and `codex exec resume --help`.

Resolve `CODEX_HOME`, defaulting to `~/.codex`. Retained rollouts are under `sessions/`; also check `archived_sessions/` when present. Search filenames first, narrowing by date or known ID. Read JSONL metadata to confirm session ID and cwd before selected message/event excerpts. A rollout filename, process ID, thread UUID, and application task handle are different identifiers. Session indexes and SQLite metadata may vary by version; discover filenames and schema rather than hardcoding database versions. Do not read authentication files to find transcripts.

Within a Codex application exposing native task tools, prefer its available list/read tools, including archived tasks and pagination. Read-only task tools avoid starting a model turn. Resolve the owning host for remote tasks; local disk does not contain every remote/cloud conversation.

## Execute a handoff

For a new user-requested task, use `codex exec --json` with the prompt supplied through its supported input path. Run in the selected cwd. Interactive mode needs a terminal; headless exec does not universally require a PTY.

For exact-ID continuation in a new process:

```sh
codex exec resume SESSION_ID - --json < /path/to/handoff.txt
```

Interactive continuation is `codex resume SESSION_ID`. The picker is cwd-filtered; `--all` widens it, and `--include-non-interactive` exists in the checked interactive resume help. Prefer exact ID over `--last`. Check subcommand help because options differ.

Use an available native application send tool to continue an existing app task. Do not launch a second writer merely because a task is busy. For a client-owned app-server, inspect the current protocol for thread/list, thread/read, thread/resume and turn/start/steer; launching another app-server is not attachment to an existing TUI. Use the actual available transport and schema, not a guessed mailbox.

## Lessons from historical use

Retained delegation guidance had unconditional PTY and Git-repository requirements. Current headless help includes `--skip-git-repo-check`; use it for intentionally selected non-repository work rather than initializing an unsolicited repository. Sandbox and approval settings remain separate choices.

A recorded linked-worktree launch needed access to Git's shared metadata directory. When the selected sandbox blocks Git there, resolve the common Git directory through native Git metadata, verify it belongs to that worktree, and add only the needed path under the user's authorized scope. Do not disable sandboxing automatically.

Capture terminal result/error events and final artifacts. Preserve OAuth support; a missing API-key environment variable alone does not mean authentication is absent.

Source: [official CLI reference](https://developers.openai.com/codex/cli/reference/). Historical execution reports are evidence of those runs, not a fresh test of every transport.
