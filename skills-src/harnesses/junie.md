Use this skill only when the operator explicitly selects JetBrains Junie or asks to hand work to Junie. This adapter coordinates a handoff; it does not select another product or silently broaden permissions.

Contract source: https://junie.jetbrains.com/docs/

## CLI route

There is no official SDK for Junie in this contract; Junie CLI is in early access. Use the documented CLI surface. Run from the selected project:

```sh
command -v junie
junie --version
junie --help

# New task, only when creation was requested.
junie --project /absolute/workspace 'Perform the scoped task and verify its artifact.'

# Continue the exact retained session.
junie --project /absolute/workspace --resume --session-id SESSION_ID 'Perform the agreed next step.'
```

Authenticate with a JetBrains account, `JUNIE_API_KEY`, or BYOK provider keys according to the installed CLI. Never log tokens passed through `--auth`. `--resume` without `--session-id` resumes the last session; that is not an explicit resume. Parallel sessions share the project filesystem unless Git worktrees isolate them, so use worktrees when concurrent lanes write code.

## Independent local launches

When the operator requests a **new independent local task**, create one fresh `junie` process in the selected project with its complete prompt supplied through the authorized route. The launching harness must retain a real process handle for that process; an executor-owned background job, a `nohup` child whose parent will exit, a session record, or a launch acknowledgment is not a running task. Do not substitute `--resume`, an IDE session, or a remote/CI job for a requested fresh local run. Before reporting a launch, confirm both the process is alive and Junie emitted its initial event.

## Handoff workflow

When the user redirects this task here, stop advancing the superseded attempt and deliver the handoff; do not finish your own approach first. Preserve the goal, state, constraints, and requested outputs without prescribing the sender's tool recipe unless the user chose that method. Relay any new approval question to the user rather than answering on their behalf. An existing approval applies only within its original scope.

1. Capture a concise packet containing the objective, current state, decisions, relevant artifacts, constraints, exact next action, acceptance criteria, and return channel.
2. Keep operator identity, product, client, channel, model or inference mechanism, and execution adapter separate. A JetBrains IDE being open does not make Junie the target.
3. Discover the native Junie surface in the target environment and read the installed help before using version-sensitive flags.
4. Prefer continuing the explicitly selected existing session. Ask when more than one session is a plausible match.
5. Deliver the packet through the authorized route without copying secrets or private transcripts into it.
6. Report the selected target, delivery mechanism, session reference when appropriate, and the delivery receipt. If the native path is unavailable, return a manual handoff packet without switching harnesses.

Progress advisories. While running, a lane may report milestones against the packet's expected result as advisory messages carrying an optional status: `started`, `milestone`, `blocked`, or `done`. Status is self-reported presence, never proof of completion — the activating agent reads it to understand progress without parsing prose, and verifies the result itself. This shared advisory vocabulary carries no control state and never blocks the lane. A spawner that wants these reports subscribes to the lane; `blocked` and `done` reports fan out to subscribers, and anyone may subscribe.

## Junie-specific boundaries

- Treat session IDs as local routing metadata, not portable identity.
- Never invent a `junie` flag, session, model, or successful delivery.
- Do not use parallel live sessions against the same checkout without worktree isolation unless the operator explicitly accepts the overlap.
- Junie CLI flag sets are early-access and version-sensitive; installed help outranks this skill on any conflict.
