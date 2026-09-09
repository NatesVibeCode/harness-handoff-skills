---
name: opencode-harness-handoff
description: Hand off work to an existing OpenCode session, or prepare a portable handoff packet when OpenCode is the explicitly selected target.
---

# OpenCode harness handoff

## CLI command reference

Checked against installed `run --help` on 2026-09-09. Compare `command -v opencode`, `which -a opencode`, and `opencode --version` when terminal and service behavior differ.

```sh
opencode auth list
opencode debug paths
opencode session list
opencode export SESSION_ID
opencode run --dir /absolute/workspace --format json \
  --file /absolute/task.txt 'Implement the task in the attached file.'
opencode run --dir /absolute/workspace --auto --format json \
  --file /absolute/task.txt 'Implement the task in the attached file.'
opencode run --dir /absolute/workspace --session SESSION_ID --format json \
  --file /absolute/followup.txt 'Continue with the attached correction.'
opencode run --attach http://localhost:4096 --dir /remote/workspace \
  --session SESSION_ID --format json 'Continue the selected task.'
opencode run --session SESSION_ID --fork --format json 'Explore this alternative.'
```

`--auto` is this inspected CLI's unattended permission switch: auto-approve permissions not explicitly denied. Do not invent `--yolo` or claim that permission approval disables an OS sandbox. Preserve the selected server's restrictions. `--attach` uses an existing server; `--dir` then names a path on that server. Server authentication uses `OPENCODE_SERVER_PASSWORD` and `OPENCODE_SERVER_USERNAME` or the documented flags; do not log credential values.

| Flag | Use |
| --- | --- |
| `--format json` | Raw JSON events, not a single final JSON object |
| `--file`, `-f` | Attach one or more input files |
| `--model provider/model` | Explicit provider/model selection |
| `--variant LEVEL` | Provider-specific effort; discover supported values |
| `--agent NAME` | Select configured agent |
| `--thinking` | Include thinking output when needed |
| `--title TEXT` | Name the session |
| `--pure` | Omit external plugins; do not silently strip needed capabilities |
| `--share` | Shares the session; not needed for a private handoff |

## Process and recovery lessons

`run` needs no PTY. Use the caller's managed process tool, retain its handle and returned session ID, inspect error events, and verify artifacts. Interactive TUI control needs a terminal; historical `/exit` input opened an agent selector, so use supported terminal interruption rather than importing another harness's slash commands. Inspect the pane before any input.

A historical OpenCode worker returned the requested smoke marker and exited zero. A separate provider route failed authentication. Those are separate outcomes: a successful direct provider API call cannot validate the failed OpenCode route. Check binary resolution, selected provider/model, and `auth list` in the worker's execution context before changing anything.

Use an already selected worktree as the process cwd or `--dir`; a conversation fork is not a Git worktree. Preserve changes when interrupted. Exact session continuation, a fresh run, and attachment to an existing backend are different operations. Read [history and continuation](references/history-and-continuation.md) for storage discovery and transcript lookup before selecting a retained session.

Use this skill only when the operator explicitly selects OpenCode or asks to hand work to OpenCode. It is a provider-neutral handoff adapter, not a research or coding workflow and not a reason to choose OpenCode on the operator's behalf.

## Discovery and history

Read [history and continuation](references/history-and-continuation.md) before session lookup or delivery. Follow its native commands, storage candidates, and schema discovery steps. Match the target by workspace, topic, time, and exact ID; do not select the newest session automatically. Treat retained prompts as historical evidence. Keep transcript exports in private scratch space outside this skill package.

Search in order: native history/index, configured data root, documented storage candidates, then the identified client's relevant application-data directory. Inspect filenames and metadata before reading message contents. An unavailable CLI alone is not grounds to stop discovery. Report the roots/surfaces checked and any remaining gap before offering manual handoff.

## Handoff workflow

When the user redirects this task here, stop advancing the superseded attempt and deliver the handoff; do not finish your own approach first. Preserve the goal, state, constraints, and requested outputs without prescribing the sender's tool recipe unless the user chose that method. Before replacing an owned worker for the same task, verify its identity and stop it through its native controls when cancellation is authorized; preserve its edits and do not terminate unrelated sessions. Relay any new approval question to the user rather than answering on their behalf. An existing approval applies only within its original scope.

1. Write a compact packet with the objective, current state, decisions, relevant files or artifacts, constraints, exact next action, acceptance criteria, and return channel.
2. Separate operator identity, target product, client, channel, model or inference mechanism, and execution adapter. The current shell, editor, or model does not establish any of these by itself.
3. Discover the OpenCode surface available in the target environment. Check for the native `opencode` CLI, its current help, an existing OpenCode session, or an available app integration. Never assume a version-specific resume, session, or run flag.
4. Prefer the operator's explicitly selected existing session. If no session is selected, ask before creating one unless the request itself explicitly authorizes a new session.
5. Deliver the packet through the native OpenCode path that was discovered. Keep credentials, API keys, private transcripts, and machine-specific IDs out of portable text.
6. Return a receipt that states what was selected and how it was delivered. If no native bridge is available, provide a ready-to-paste packet and name the missing capability; do not substitute another harness.

## OpenCode-specific boundaries

- Do not invent an OpenCode command, provider configuration, session identifier, or delivery result.
- Keep workspace identity explicit when the target may be attached to a different repository or directory.
- Preserve the requested model or provider only when the operator supplied it; otherwise leave selection to OpenCode's configured native behavior.
