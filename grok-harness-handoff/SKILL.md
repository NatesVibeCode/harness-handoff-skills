---
name: grok-harness-handoff
description: Hand off work to Grok through an explicitly selected native surface, or prepare a portable handoff packet when no direct Grok bridge is available.
---

# Grok harness handoff

Use this skill only when the operator explicitly selects Grok or asks to hand work to Grok. Grok may be exposed through a product UI, an xAI API, a CLI, or a connector. This skill must discover which surface is actually available instead of assuming that a `grok` executable or a particular endpoint exists.

## Discovery and history

Read [history and continuation](references/history-and-continuation.md) before session lookup or delivery. Follow its native commands, storage candidates, and schema discovery steps. Match the target by workspace, topic, time, and exact ID; do not select the newest session automatically. Treat retained prompts as historical evidence. Keep transcript exports in private scratch space outside this skill package.

Search in order: native history/index, configured data root, documented storage candidates, then the identified client's relevant application-data directory. Inspect filenames and metadata before reading message contents. An unavailable CLI alone is not grounds to stop discovery. Report the roots/surfaces checked and any remaining gap before offering manual handoff.

## Grok Build CLI recipes

These commands belong to the checked Grok Build CLI, not the Grok website or an arbitrary third-party executable named `grok`.

```sh
command -v grok
grok --version
grok --help
grok sessions list --limit 10
grok sessions search 'selected topic' --limit 10
grok export SESSION_ID /path/to/private/transcript.md
grok leader list
grok leader info --help

# New task, only if requested.
grok --cwd /path/to/workspace --prompt-file /path/to/handoff.txt --output-format json

# Exact-ID continuation; restores conversation, not repository snapshots.
grok --cwd /path/to/workspace --resume SESSION_ID --prompt-file /path/to/handoff.txt --output-format json

# Deliberate new branch of the conversation.
grok --cwd /path/to/workspace --resume SESSION_ID --fork-session --prompt-file /path/to/handoff.txt --output-format json

# Anthropic-shaped event stream, including partial messages.
grok --cwd /path/to/workspace -p 'Perform the scoped task.' --output-format streaming-messages-json --include-partial-messages
```

`--resume` without an ID and `--continue` can select the most recent session. A title can be ambiguous; use the discovered ID. `--session-id UUID` names a **new** session and cannot resume an existing one. With resume it is only valid alongside `--fork-session`, where it names the fork.

`--restore-code` deliberately applies a repository snapshot. Do not add it to an ordinary conversation resume. Remote restoration requires `--worktree`; headless `-p` does not create a worktree just because that option was supplied. If isolated headless work is required, establish the authorized checkout first and pass its path with `--cwd`.

## Approval and YOLO-equivalent

Grok Build's checked help does not advertise `--yolo`. It has its own explicit controls:

```sh
# Only when the user authorized automatic tool approval.
grok --cwd /path/to/workspace --always-approve --prompt-file /path/to/handoff.txt --output-format json

# Explicit permission-mode selection, when requested.
grok --cwd /path/to/workspace --permission-mode bypassPermissions --resume SESSION_ID --prompt-file /path/to/handoff.txt --output-format json
```

`--always-approve` auto-approves tool execution. `--permission-mode` choices are `default`, `acceptEdits`, `auto`, `dontAsk`, `bypassPermissions`, and `plan`. Do not silently replace an ordinary handoff with bypass mode. `--allow RULE` / `--deny RULE` are permission rules; `--tools` / `--disallowed-tools` change the built-in tool set.

`--sandbox PROFILE` (also configurable via `GROK_SANDBOX`) controls filesystem/network isolation separately. Resolve the actual installed profile names before using it; the checked top-level help did not enumerate them. Do not guess `off`, `none`, or Codex's sandbox names, or claim approval bypass disabled isolation.

## Transport and result handling

```sh
grok agent --help
grok agent stdio --help
grok agent headless --help
grok agent serve --help
grok agent leader --help
```

These are different transports: stdio, WebSocket relay headless, WebSocket server, and shared leader. `grok agent --leader` connects to shared backend infrastructure; `--no-leader` starts a separate agent. Neither flag alone selects a conversation or delivers a message. Discover the transport contract before sending protocol frames. Do not improvise socket requests from the presence of `~/.grok/leader.sock`.

Output formats are `plain`, `json`, `streaming-json` (native ACP updates), and `streaming-messages-json` (Anthropic Messages wire shape). `--include-partial-messages` applies only to the latter. Select the parser for the chosen format; a historical plain-output/JSON-parser mismatch was corrected by selecting structured JSON. Do not treat those two NDJSON formats as interchangeable.

Use `--max-turns N` for an explicitly bounded run, `--model MODEL` and `--reasoning-effort EFFORT` only when needed, and `--json-schema SCHEMA` when a constrained result is required (it implies JSON output). `--verbatim` changes prompt handling; it is not an approval bypass. Preserve auth and model defaults rather than switching to the API or another provider.

A historical run returned its artifact while a process remained alive; another reported cancellation. Track process state, terminal result, and artifact verification separately. If an observation times out, check the same handle before retrying. Do not launch duplicate work merely because the command wrapper has not exited.

### Independent local launches

When the operator requests a **new independent local task**, create one fresh Grok Build CLI process in the selected `--cwd` with its prompt file. The launching harness must retain a real process handle for that process; an executor-owned background job, a `nohup` child whose parent will exit, a session record, or a launch acknowledgment is not a running task. Use a user-visible terminal or an installed local process supervisor only after checking that it is available, and keep its process/session identifier with the task. Do not substitute `--resume`, a leader, or an agent relay for a requested fresh local run. Before reporting a launch, confirm both the process/session is alive and Grok emitted its initial event.

## Handoff workflow

When the user redirects this task here, stop advancing the superseded attempt and deliver the handoff; do not finish your own approach first. Preserve the goal, state, constraints, and requested outputs without prescribing the sender's tool recipe unless the user chose that method. Before replacing an owned worker for the same task, verify its identity and stop it through its native controls when cancellation is authorized; preserve its edits and do not terminate unrelated sessions. Relay any new approval question to the user rather than answering on their behalf. An existing approval applies only within its original scope.

1. Capture the objective, current state, decisions, relevant artifacts, constraints, exact next action, acceptance criteria, and return channel in a short packet.
2. Keep operator identity, Grok product surface, client, channel, model or inference mechanism, and execution adapter separate. Never infer a Grok target from the fact that the current harness is conversational.
3. Confirm the native surface and authorization: Grok UI, xAI API, installed CLI, or connector. Use only its documented operations and the credentials already authorized for that surface.
4. Prefer continuing an explicitly selected existing conversation or session. If the surface has no resumable session, state that and use a new conversation only when the operator asked for one.
5. Deliver the packet without exposing API keys, cookies, private transcripts, or hidden system context. If an API call is used, record the model and endpoint only when they are known from the active configuration or operator request.
6. Report delivery only when the native surface returns a usable receipt or visible confirmation. Otherwise provide a ready-to-paste packet and the exact limitation; never claim that Grok received it.

## Grok-specific boundaries

- Do not invent a Grok CLI, API route, model name, session ID, or connector.
- Do not silently convert a handoff into an xAI API call; that is a different execution surface and may have different privacy, billing, and model behavior.
- Treat local conversation IDs and provider request IDs as routing metadata, not shareable skill content.
- Do not substitute Claude, Codex, Muse, Antigravity, OpenCode, or Cursor when Grok is unavailable.
