Use this skill only when the operator explicitly selects Factory Droid or asks to hand work to Droid. This adapter coordinates a handoff; it does not select another product or silently broaden permissions.

Contract source: https://docs.factory.ai/sdk/typescript

## SDK route

Prefer the official Droid TypeScript SDK when Node execution is available. It runs the same agent harness as the CLI, desktop, and web surfaces, with runs, persistent sessions, resume, fork, streaming, discovery, tool controls, and daemon connectivity.

```sh
npm install @factory/droid-sdk
export FACTORY_API_KEY="private-key-not-logged"
```

```ts
import { createSession, DroidMessageType } from "@factory/droid-sdk/node";

const session = await createSession({ cwd: process.cwd() });
try {
  for await (const message of session.stream("Perform the scoped handoff task.")) {
    if (message.type === DroidMessageType.Assistant) console.log(message.text);
  }
} finally {
  await session.close();
}
```

Resume only with the exact retained session ID via `resumeSession`; the newest session is not an explicit resume. List local sessions with `listSessions` for passive discovery. A session owns its working directory, settings, and one active turn at a time. A per-lane owned SDK session is that lane's execution handle; connecting to an existing shared daemon is a separate, explicitly selected operation. A Python `droid-sdk` package also exists, but the TypeScript SDK is the authorized binding until the Python surface is verified. If the SDK route is unavailable, use the pinned CLI fallback below.

## CLI fallback

Run from the selected checkout:

```sh
command -v droid
droid --version
droid exec --help

# New headless task, only when creation was requested.
droid exec 'Perform the scoped task and verify its artifact.'

# Exact-ID continuation in exec mode.
droid exec -s SESSION_ID 'Continue with the agreed next step.'

# Deliberate fork of a retained session.
droid --fork SESSION_ID
```

`droid exec -f prompt.md` loads a prompt from a file for long handoffs. Set autonomy level, reasoning effort, model, and tool allowlists explicitly per run. Daemon, REST, and cloud session APIs are separate surfaces with their own availability rules; do not assume a local session ID works there.

## Independent local launches

When the operator requests a **new independent local task**, create one fresh SDK-owned Droid session or `droid exec` process in the selected checkout with its complete prompt supplied through the authorized route. The launching harness must retain a real execution handle for that lane; an executor-owned background job, a `nohup` child whose parent will exit, a session record, or a launch acknowledgment is not a running task. Do not substitute an existing-session continuation or a shared daemon task for a requested fresh run. Before reporting a launch, confirm both the execution is alive and Droid emitted its initial event.

## Handoff workflow

When the user redirects this task here, stop advancing the superseded attempt and deliver the handoff; do not finish your own approach first. Preserve the goal, state, constraints, and requested outputs without prescribing the sender's tool recipe unless the user chose that method. Relay any new approval question to the user rather than answering on their behalf. An existing approval applies only within its original scope.

1. Capture a concise packet containing the objective, current state, decisions, relevant artifacts, constraints, exact next action, acceptance criteria, and return channel.
2. Keep operator identity, product, client, channel, model or inference mechanism, and execution adapter separate. Do not infer the target from the application currently in use.
3. Discover the native Droid surface in the target environment. When the `droid` CLI is available, inspect its supported commands and options before using it.
4. Prefer continuing the explicitly selected existing session. Ask when more than one session is a plausible match.
5. Deliver the packet through the authorized route without copying secrets or private transcripts into it.
6. Report the selected target, delivery mechanism, session reference when appropriate, and the delivery receipt. If the native path is unavailable, return a manual handoff packet without switching harnesses.

Progress advisories. While running, a lane may report milestones against the packet's expected result as advisory messages carrying an optional status: `started`, `milestone`, `blocked`, or `done`. Status is self-reported presence, never proof of completion — the activating agent reads it to understand progress without parsing prose, and verifies the result itself. This shared advisory vocabulary carries no control state and never blocks the lane. A spawner that wants these reports subscribes to the lane; `blocked` and `done` reports fan out to subscribers, and anyone may subscribe.

## Droid-specific boundaries

- Treat session IDs as local routing metadata, not portable identity.
- Never invent a `droid` flag, session, model, mission, or successful delivery.
- Do not use missions, custom droids, daemons, or cloud session APIs unless the operator explicitly asks for them.
- Do not log `FACTORY_API_KEY` or paste it into prompts, files, or receipts.
