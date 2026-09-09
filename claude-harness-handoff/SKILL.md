---
name: claude-harness-handoff
description: Find Claude Code sessions and local transcripts, hand off tasks, and continue selected conversations through supported native capabilities.
---

# Claude Code harness handoff

Read [history and continuation](references/history-and-continuation.md) before discovery or execution. The user's request selects the workspace, task, and whether to inspect, send, continue, or create a session.

## CLI recipes

Run these from the selected workspace. Replace `SESSION_ID` with a verified conversation UUID and `BACKGROUND_ID` with the short ID printed by the background launcher; they are different identifiers.

```sh
command -v claude
claude --version
claude --help
claude agents --help
claude auth status --json

# Passive native process discovery, including completed background sessions.
claude agents --json --all --cwd /path/to/workspace
claude logs BACKGROUND_ID

# New headless task, only when creation was requested.
claude -p --output-format json < /path/to/handoff.txt

# Continue the exact conversation; this starts a turn, not passive inspection.
claude --resume SESSION_ID -p --output-format json < /path/to/handoff.txt

# Deliberate fork: preserves source history but returns a NEW session identity.
claude --resume SESSION_ID --fork-session -p --output-format json < /path/to/handoff.txt

# Stream events from one headless turn.
claude -p --verbose --output-format stream-json --include-partial-messages < /path/to/handoff.txt

# Native background execution; record the printed background ID.
claude --bg 'Perform the scoped task and verify the requested artifact.'
claude logs BACKGROUND_ID

# Interactive attachment, when requested; not a read-only log operation.
claude attach BACKGROUND_ID
```

`claude --continue` uses the newest conversation in the current directory. Do not use it when the user selected a different or exact conversation. Do not run concurrent resumes against the same conversation. `claude --session-id UUID` is not a substitute for `--resume`.

For authorized cancellation, `claude stop BACKGROUND_ID` stops the background process and retains the conversation. `claude rm BACKGROUND_ID` deletes the background session and potentially its worktree; it is not routine cleanup. `claude respawn --help` describes process restart after an upgrade, not task retry after an observation timeout.

## Native cross-session messaging

Current Claude documentation adds a route beyond CLI resume: inside a supported Claude session, `/list-agents` shows reachable agents; Claude uses `ListAgents` and `SendMessage` to discover and message the selected recipient. These are native model tools, not invented shell subcommands. Have the existing Claude parent use its actual tool schema and resolved recipient; do not start another session merely to perform discovery.

Messages arrive between tool calls or start a turn when idle. Delivery can be held or refused by `crossSessionInbound`; acceptance does not prove execution. Ordinary print workers can receive messages, but bare-mode workers have no inbox. For explicitly authorized unattended inbound delivery, the session-local setting is `--settings '{"crossSessionInbound":"accept"}'`; do not silently change global settings.

`SendMessage` also supports a one-shot `notify_when_idle` subscription for eligible same-machine sessions. Availability and cross-machine routing depend on version/provider and Remote Control. Use the documented discovery route, not guessed sockets or copied auth tokens. See [official cross-session messaging](https://code.claude.com/docs/en/cross-session-messaging) for current requirements and controls. This route was documentation-checked, not live-tested here.

## Approval, YOLO-equivalent, and isolation

Claude's checked CLI does not advertise a `--yolo` flag. Its explicit bypass is:

```sh
# Only when the user authorized permission bypass for this task.
claude --dangerously-skip-permissions -p --output-format json < /path/to/handoff.txt
claude --resume SESSION_ID --permission-mode bypassPermissions -p --output-format json < /path/to/handoff.txt

# Narrow tool grants instead of blanket bypass, when appropriate to the task.
claude -p --allowedTools 'Read' 'Bash(git diff *)' --output-format json < /path/to/handoff.txt
```

- `--allow-dangerously-skip-permissions` merely makes bypass available; it does not activate it.
- `--permission-mode` accepts `acceptEdits`, `auto`, `bypassPermissions`, `manual`, `dontAsk`, and `plan` in the checked version. Do not equate auto-classification or refusing prompts with unrestricted tool execution.
- `--tools` controls which built-in tools exist, `--allowedTools` controls grants, and `--disallowedTools` controls denials. These are not interchangeable.
- Permission bypass is not evidence that OS-level sandboxing is disabled. Inspect the selected settings and current sandbox documentation separately; do not invent a universal `--no-sandbox` switch.
- `--restricted` refuses bypass and changes tool/settings access. Do not combine it with bypass recipes.
- Print mode skips workspace trust prompts, not all permission checks. Use a trusted selected directory. Invalid settings can be silently ignored in print mode; check effective behavior when a control matters.

## Persistent streams, workspace, and authentication

For a caller-owned multi-turn subprocess, launch:

```sh
claude -p --verbose --input-format stream-json --output-format stream-json --replay-user-messages
```

Keep stdin open and write native JSON message envelopes, one per line, such as `{"type":"user","message":{"role":"user","content":"Perform the scoped next step."},"parent_tool_use_id":null}`. Read the returned session and result events before sending the next turn. A closed stdin or completed one-shot process is not a live messaging channel. Do not pipe a raw handoff text file into stream-json input. This protocol does not inject into an unrelated running TUI. The [SDK message reference](https://code.claude.com/docs/en/agent-sdk/typescript) defines user, initialization, and result envelopes; preserve parent tool identity for actual child traffic instead of copying the root example.

Use `--add-dir /path/to/extra-input` for additional authorized tool access. `--worktree NAME` creates a new checkout; choose it only when the task calls for isolation. `--tmux` requires `--worktree` in this release. Headless print and native background modes do not universally require tmux or a PTY.

Keep the selected auth path. `--bare` skips OAuth/keychain and auto-discovered context; it requires API-key/helper auth (or the selected third-party provider's credentials), so it is not a harmless startup optimization for subscription sessions. `--safe-mode` disables customizations but preserves normal auth/permissions. `--no-session-persistence` prevents later resume. Neither belongs in a durable handoff by default.

Optional task controls: `--model MODEL`, `--effort LEVEL`, `--max-budget-usd AMOUNT` for print mode, and `--json-schema SCHEMA` for structured output. Preserve configured defaults unless requested. Record result errors as failures; parseable JSON and a printed background ID establish neither task success nor artifact correctness.

## Workflow

When the user redirects this task here, stop advancing the superseded attempt and deliver the handoff; do not finish your own approach first. Preserve the goal, state, constraints, and requested outputs without prescribing the sender's tool recipe unless the user chose that method. Before replacing an owned worker for the same task, verify its identity and stop it through its native controls when cancellation is authorized; preserve its edits and do not terminate unrelated sessions. Relay any new approval question to the user rather than answering on their behalf. An existing approval applies only within its original scope.

1. Resolve the installed client and relevant help. Search native history and retained metadata by workspace, topic, date, and exact ID. Read the relevant prior request, last result, and unresolved work.
2. Deliver a concise goal, current state, constraints, input artifacts, and expected result. Let the receiving harness choose its native tools unless the user specified a method.
3. Continue the selected session when requested. A resume starts activity; use retained logs or native read tools for passive lookup. A new process is not a live-session message.
4. Preserve the user's existing authorization and requested controls. Do not import permission bypasses, fixed models, or personal services from historical examples.
5. Record session identity separately from process handles and workspace paths. Observe result events and requested artifacts before reporting completion; acceptance and process exit alone do not prove the work succeeded.
6. If one route fails, inspect other supported routes and report the exact limitation. Supply a manual packet only after applicable native discovery paths have been checked.

## Portability

Keep private transcripts and machine-specific IDs outside the skill package. Use actual local paths during a handoff, but replace them with placeholders in reusable examples. Do not confuse another harness's UUID with a Claude Code session merely because the formats match.
