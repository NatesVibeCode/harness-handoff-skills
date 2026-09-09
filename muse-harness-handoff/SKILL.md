---
name: muse-harness-handoff
description: Hand off work to an existing Muse session, or prepare a portable handoff packet when Muse is the explicitly selected target.
---

# Muse harness handoff

Use this skill only when the operator explicitly selects Muse or asks to hand work to Muse. This is a coordination adapter. It does not choose a different harness, silently launch one, or grant permissions.

## Discovery and history

Read [the full operating guide](references/operating-guide.md) for launch examples, unattended approval and sandbox controls, native message schemas, multi-turn operation, worktree behavior, and recovery. Preserve controls already authorized by the user; do not ask again merely because a new process is needed.

Read [history and continuation](references/history-and-continuation.md) before session lookup or delivery. Follow its native commands, storage candidates, and schema discovery steps. Match the target by workspace, topic, time, and exact ID; do not select the newest session automatically. Treat retained prompts as historical evidence. Keep transcript exports in private scratch space outside this skill package.

Search in order: native history/index, configured data root, documented storage candidates, then the identified client's relevant application-data directory. Inspect filenames and metadata before reading message contents. An unavailable CLI alone is not grounds to stop discovery. Report the roots/surfaces checked and any remaining gap before offering manual handoff.

## Command entrypoints

```sh
command -v muse
muse --version
muse exec --help
muse resume --help
muse session-message list --json

# Deliver to the verified existing session; message body comes from stdin.
muse session-message send --target SESSION_ID --json < /path/to/handoff.txt

# Interactive history continuation, not live-session message delivery.
muse --workspace /path/to/workspace resume SESSION_ID

# New headless task in the selected checkout, when creation is requested.
muse exec --json --workspace /path/to/workspace --worktree off --prompt-file /path/to/handoff.txt

# Same launch with user-authorized unattended/no-sandbox controls.
muse exec --json --yolo --disable-sandbox --workspace /path/to/workspace --worktree off --prompt-file /path/to/handoff.txt
```

`--yolo` combines approval bypass, sandbox bypass, and workspace trust in the checked CLI. `--disable-sandbox` explicitly names shell isolation; `--disable-approval` and `--trust-workspace` are separate controls. Do not invent `--no-sandbox`, `--message`, or `muse subagent`. `muse serve` does not accept exec's `--yolo`; its approval controls belong to the MSP session protocol.

For an existing worktree use `--worktree existing --worktree-existing /path/to/worktree`; for intentional creation use `--worktree create --worktree-base VERIFIED_REF`. Preserve the actual execution directory returned by the run. A root isolation capability flag does not prove every child is isolated.

Read the operating guide before child messaging: a running child uses queue/send, a completed child needs `mode: followup`, and each distinct operation needs a fresh command ID. Cross-session CLI ingress, parent-owned child tools, and MSP root turns are separate routes. A historical `external_agent_ingress_closed` response means delivery failed; changing flag spelling or launching a replacement session does not turn it into a successful handoff.

## Handoff workflow

When the user redirects this task here, stop advancing the superseded attempt and deliver the handoff; do not finish your own approach first. Preserve the goal, state, constraints, and requested outputs without prescribing the sender's tool recipe unless the user chose that method. Before replacing an owned worker for the same task, verify its identity and stop it through its native controls when cancellation is authorized; preserve its edits and do not terminate unrelated sessions. Relay any new approval question to the user rather than answering on their behalf. An existing approval applies only within its original scope.

1. Capture the smallest useful packet:
   - objective and desired outcome
   - current state and decisions already made
   - relevant files, URLs, or artifacts
   - constraints, risks, and things not to change
   - exact next action for Muse
   - acceptance criteria and return channel
2. Keep operator identity, product, client, channel, model or inference mechanism, and execution adapter separate. Never treat the current access path as proof that Muse is the intended target.
3. Discover the native Muse surface available in the target environment. Use the installed `muse` CLI, an available native integration, or the Muse UI according to what is actually present. Consult its help or documentation before using unfamiliar commands or flags.
4. Prefer continuing the operator's explicitly selected existing session. If several sessions match, stop and ask the operator to choose. Create a new session only when the operator explicitly requests that.
5. Send the packet as a concise, self-contained message. Preserve paths as portable references where possible; do not embed secrets, credentials, private transcripts, or machine-specific session identifiers.
6. Report the target, delivery mechanism, selected or created session, and any receipt or blocker. If Muse cannot be reached, return the packet for manual pasting and do not substitute another harness.

## Muse-specific boundaries

- Use native session inspection and session messaging when those capabilities are available.
- Use Muse subagent communication only when the operator explicitly asks for subagent work.
- Do not invent a Muse command, API, session ID, or message-delivery result.
- Keep local process and session identifiers out of the shareable skill and out of portable handoff text unless the operator specifically needs one for a local continuation.
