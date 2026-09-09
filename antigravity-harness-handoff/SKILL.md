---
name: antigravity-harness-handoff
description: Hand off work to an existing Google Antigravity conversation, or prepare a portable handoff packet when Antigravity is the explicitly selected target.
---

# Antigravity harness handoff

Use this skill only when the operator explicitly selects Google Antigravity or asks to hand work to Antigravity. This adapter coordinates a handoff; it does not select another product or silently broaden permissions.

## Discovery and history

Read [the full operating guide](references/operating-guide.md) for launch examples, unattended approval and sandbox controls, native message schemas, multi-turn operation, worktree behavior, and recovery. Preserve controls already authorized by the user; do not ask again merely because a new process is needed.

Read [history and continuation](references/history-and-continuation.md) before session lookup or delivery. Follow its native commands, storage candidates, and schema discovery steps. Match the target by workspace, topic, time, and exact ID; do not select the newest session automatically. Treat retained prompts as historical evidence. Keep transcript exports in private scratch space outside this skill package.

Search in order: native history/index, configured data root, documented storage candidates, then the identified client's relevant application-data directory. Inspect filenames and metadata before reading message contents. An unavailable CLI alone is not grounds to stop discovery. Report the roots/surfaces checked and any remaining gap before offering manual handoff.

## Command entrypoints

Run from the selected checkout: this CLI does not use Muse's `--workspace`, `--prompt-file`, or `exec` syntax.

```sh
command -v agy
agy --version
agy --help

# A new one-shot turn, only when creation was requested.
agy --output-format json --print 'Perform the scoped task and verify its artifact.'

# Continue the exact retained conversation.
agy --conversation CONVERSATION_ID --output-format json --print 'Perform the agreed next step.'

# User-authorized automatic approval; sandbox configuration is separate.
agy --dangerously-skip-permissions --conversation CONVERSATION_ID --output-format stream-json --print 'Perform the agreed next step.'

# Caller-owned multi-turn process: keep stdin open; do not add --print.
agy --input-format stream-json --output-format stream-json
```

For that persistent stream, submit newline-delimited `{"event":"user","message":{"content":"The next scoped task"}}` and flush. Wait for the turn's `result` before the next message; retain the `conversation_id` from native events. This is not Claude's `type:user` envelope. Closing stdin ends the input channel. Do not send guessed control frames or slash commands through it.

`--dangerously-skip-permissions` approves permission requests; it does not prove sandboxing is off. `--sandbox` forces sandboxing on, and the configured `enableTerminalSandbox` setting must be checked for an explicit no-sandbox request. No `--yolo` or universal `--no-sandbox` alias is established here. See the operating guide for the bounded settings check, argument-vector long-prompt example, and native child-message schema.

`--print-timeout 15m` changes the response timeout when needed. `--mode plan|accept-edits` is execution mode, not sandbox posture. `--continue` selects recent history and is unsuitable when an exact conversation was selected. A conversation resume is an active turn, not passive lookup or a mailbox for another busy process. No shell-level `agy send-message` was validated; native parent/child messaging uses Antigravity's own tools.

## Handoff workflow

When the user redirects this task here, stop advancing the superseded attempt and deliver the handoff; do not finish your own approach first. Preserve the goal, state, constraints, and requested outputs without prescribing the sender's tool recipe unless the user chose that method. Before replacing an owned worker for the same task, verify its identity and stop it through its native controls when cancellation is authorized; preserve its edits and do not terminate unrelated sessions. Relay any new approval question to the user rather than answering on their behalf. An existing approval applies only within its original scope.

1. Capture a concise packet containing the objective, current state, decisions, relevant artifacts, constraints, exact next action, acceptance criteria, and return channel.
2. Keep operator identity, product, client, channel, model or inference mechanism, and execution adapter separate. Do not infer the target from the application currently in use.
3. Discover the native Antigravity surface in the target environment. When the `agy` CLI is available, inspect its supported commands and options before using it. Otherwise use the available native Antigravity integration or UI.
4. Prefer continuing the explicitly selected existing conversation. If process or conversation identifiers are needed, resolve them locally and do not put them in the reusable skill. Ask when more than one conversation is a plausible match.
5. Use Antigravity's native communication path to deliver the packet and preserve the operator's wording and constraints. Do not copy secrets or private transcripts into the packet.
6. Report the selected target, delivery mechanism, conversation or process reference when appropriate, and the delivery receipt. If the native path is unavailable, return a manual handoff packet without switching harnesses.

## Permission boundary

The `--dangerously-skip-permissions` option, or any equivalent bypass, is never a default. Use it only when the operator explicitly requests it and the target environment supports it. Otherwise retain the normal permission flow and surface any approval request.

## Antigravity-specific boundaries

- Treat process IDs and conversation IDs as local routing metadata, not portable identity.
- Use native conversation inspection and messaging when available.
- Never invent an `agy` flag, conversation, process, or successful delivery.
- Do not use Antigravity subagents or parallel sessions unless the operator explicitly asks for them.
