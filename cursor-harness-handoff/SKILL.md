---
name: cursor-harness-handoff
description: Hand off work to an existing Cursor agent or workspace, or prepare a portable handoff packet when Cursor is the explicitly selected target.
---

# Cursor harness handoff

## CLI command reference

Checked against installed help on 2026-09-09. Resolve `command -v cursor-agent` and `cursor-agent --version`; an executable named `agent` needs provenance checking because other products use that name too.

```sh
cursor-agent status
cursor-agent models
cursor-agent --workspace /absolute/workspace --print --output-format json 'Implement the selected task.'
cursor-agent --workspace /absolute/workspace --yolo --sandbox disabled --trust \
  --print --output-format stream-json 'Implement the selected task.'
cursor-agent --workspace /absolute/workspace --resume CHAT_ID \
  --print --output-format json 'Continue with the requested correction.'
cursor-agent --workspace /absolute/workspace --mode ask --print 'Explain the selected code.'
cursor-agent --workspace /absolute/workspace --mode plan --print 'Plan the requested change.'
cursor-agent --workspace /absolute/repository --worktree selected-name \
  --worktree-base VERIFIED_REF --print 'Implement the isolated task.'
```

For long prompts, read the UTF-8 file and pass its contents as one argument through the caller's process API or `subprocess.Popen([...], cwd=...)`; this CLI does not advertise a prompt-file flag. Do not paste arbitrary prompt text into shell code.

| Flag | Meaning |
| --- | --- |
| `--yolo`, `--force`, `-f` | Allow commands unless explicitly denied; YOLO is a force alias |
| `--sandbox disabled` | Explicitly disables sandbox mode, overriding configuration |
| `--sandbox enabled` | Explicitly enables sandbox mode |
| `--trust` | Trust selected workspace without prompting |
| `--auto-review` | Classifier-based approval; may still prompt |
| `--approve-mcps` | Approves MCP servers separately; use when included in the requested controls |
| `--stream-partial-output` | Adds text deltas with print + stream-json |
| `--model MODEL` | Uses an explicit model; discover available IDs with `models` |
| `--add-dir PATH` | Adds another workspace root |
| `--skip-worktree-setup` | Skips configured worktree setup scripts; changes startup behavior |

Preserve the user's already-authorized controls in follow-ups. Force approval and sandbox mode are separate. Print mode has write and shell tools; it is not automatically read-only. `create-chat` creates new state. `ls` and bare `resume` are interactive/latest-session routes, not substitutes for bounded passive history lookup.

## Continuation and failure handling

Use the exact CLI chat ID only after matching workspace metadata and the relevant transcript. Editor and cloud conversation IDs are not automatically CLI chat IDs. The [history reference](references/history-and-continuation.md) covers the CLI SQLite store and separate editor stores.

A recorded continuation failed with `SecItemCopyMatching failed -50`. That is credential access failure, not missing history. Check `status` under the actual launching account and executable. Do not replace an authenticated session with a different endpoint, API key, or provider merely to make a smoke test pass.

## Independent local launches

When the operator requests a **new independent local task**, create one fresh Cursor CLI process in the selected workspace/worktree with the complete prompt from a file. The launching harness must retain a real process handle for that process; an executor-owned background job, a `nohup` child whose parent will exit, a session record, or a launch acknowledgment is not a running task. Use a user-visible terminal or an installed local process supervisor only after checking that it is available, and keep its process/session identifier with the task. Do not substitute a continuation, editor task, or remote bridge for a requested fresh local run. Before reporting a launch, confirm both the process/session is alive and Cursor emitted its initial event.

Keep the subprocess handle, stream output and stderr, and inspect the final result and requested artifacts. Quiet output does not prove a hang. A new CLI resume is a new process continuing history; it does not establish delivery into an already busy editor agent. For a selected running editor agent, use its available native control surface and verify the selected workspace before sending.

Use this skill only when the operator explicitly selects Cursor or asks to hand work to Cursor. This adapter coordinates context transfer; it does not decide which editor, agent, repository, or model should be used.

## Discovery and history

Read [history and continuation](references/history-and-continuation.md) before session lookup or delivery. Follow its native commands, storage candidates, and schema discovery steps. Match the target by workspace, topic, time, and exact ID; do not select the newest session automatically. Treat retained prompts as historical evidence. Keep transcript exports in private scratch space outside this skill package.

Search in order: native history/index, configured data root, documented storage candidates, then the identified client's relevant application-data directory. Inspect filenames and metadata before reading message contents. An unavailable CLI alone is not grounds to stop discovery. Report the roots/surfaces checked and any remaining gap before offering manual handoff.

## Handoff workflow

When the user redirects this task here, stop advancing the superseded attempt and deliver the handoff; do not finish your own approach first. Preserve the goal, state, constraints, and requested outputs without prescribing the sender's tool recipe unless the user chose that method. Before replacing an owned worker for the same task, verify its identity and stop it through its native controls when cancellation is authorized; preserve its edits and do not terminate unrelated sessions. Relay any new approval question to the user rather than answering on their behalf. An existing approval applies only within its original scope.

1. Capture a self-contained packet with the objective, current state, decisions, relevant files or artifacts, constraints, exact next action, acceptance criteria, and return channel.
2. Make the target workspace explicit. The current working directory may not be the workspace open in Cursor. Never assume that an editor window, repository, branch, or worktree is the same across harnesses.
3. Discover the native Cursor surface available in the target environment, such as the Cursor app, its agent CLI when installed, or an existing integration. Read the installed version's help or documentation before using session or workspace options.
4. Prefer continuing the operator's explicitly selected existing agent or workspace. Ask when multiple windows, repositories, branches, or sessions could match. Create or open a new target only when the operator explicitly requests it.
5. Deliver the packet through the discovered native path. Include portable paths or repository-relative paths where possible, and exclude secrets, private transcripts, and machine-specific IDs.
6. Report the workspace, branch or session reference when known, the delivery mechanism, and any receipt. If direct delivery is unavailable, return a ready-to-paste packet and do not switch to another harness.

## Cursor-specific boundaries

- Do not invent a `cursor-agent` option, app automation, session, workspace, or delivery result.
- Do not make repository changes merely to prepare a handoff unless the operator separately asked for those changes.
- Preserve the operator's requested model or mode only when explicitly supplied; otherwise leave model selection to Cursor's native configuration.
- Keep editor-local IDs and window state out of the shareable skill.
