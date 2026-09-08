# Claude Code discovery and handoff

Checked installed version: 2.1.251. Existing delegation skills and retained handoffs support print-mode execution and exact-ID continuation. Current help supersedes older command lists.

## Read retained history

Resolve `command -v claude`, `claude --version`, and `claude --help`.

The observed transcript root is `~/.claude/projects/`; resolve any configured Claude data-root override first. Project directories encode workspace paths, and session JSONL files contain conversation records. Search filenames by exact ID, then confirm cwd/session metadata from the selected file. Do not derive the target solely by reversing the directory encoding. Discover child transcripts under the selected session/project when relevant, keeping child identity separate from the root.

Read relevant user/assistant messages and tool results, following actual parent/message links. Summaries and compacted history may omit details. `--no-session-persistence` runs are not recoverable from a retained session file. Remote/cloud conversations need their owning product surface.

## Native commands

For a new user-requested headless task:

```sh
claude -p --output-format json < /path/to/handoff.txt
```

For a selected existing session:

```sh
claude --resume SESSION_ID -p --output-format json < /path/to/handoff.txt
```

Run in the selected workspace. Save the returned `session_id`, distinguish error results from successful completion, and check the requested output. `--continue` selects the newest conversation in the current directory; exact ID avoids ambiguity. `--fork-session` intentionally creates another identity.

For a caller-owned streaming process, inspect `--input-format stream-json`, `--output-format stream-json`, and `--replay-user-messages`. Supply the documented message envelope, not arbitrary text lines. Check whether the installed version requires `--verbose` for streamed print output. Keep the input stream open across turns.

The checked release also exposes `claude agents` for background-agent management, `claude logs ID` for recent terminal output, and `claude attach ID` for attachment. Inspect their help; a background short ID is not necessarily a transcript UUID. Older skill claims that `agents` only lists definitions are stale for this release.

## Historical lessons

Print mode works without a PTY. It skips the workspace trust dialog, but does not by itself grant every tool permission. Do not transfer an old bypass preference or blindly accept terminal dialogs.

Resuming in a new process does not inject a message into an already-running TUI. For an explicitly selected terminal session, identify the exact pane and inspect it before any terminal input; never send keystrokes into an unknown foreground process. Prefer native process or application controls when available.

Retained records contain exact-ID handoff instructions; they do not prove every current streaming/background/cloud path was exercised successfully. OAuth and API billing are different authentication paths; retain the chosen configuration.

Source: [official CLI reference](https://code.claude.com/docs/en/cli-reference).
