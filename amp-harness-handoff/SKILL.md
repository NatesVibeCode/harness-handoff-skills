---
name: amp-harness-handoff
description: Hand off work to an Amp agent thread, or prepare a portable handoff packet when Amp is the explicitly selected target.
---

# Amp harness handoff

## Direct lane spawning

For a new handoff, spawn the requested number of independent caller-owned Amp executions directly through the contract-authorized SDK or CLI route. Each lane gets its own prompt, owned thread/process handle, and result. A per-lane owned SDK run is that lane's execution handle, not a shared backend. Do not use a lane manager, leader, coordinator, relay, shared server, shared thread, background task manager, or parent agent to fan out or run the lanes. Existing-thread continuation is allowed only when the operator explicitly asks to continue that exact thread.

Use this skill only when the operator explicitly selects Amp or asks to hand work to Amp. This adapter coordinates a handoff; it does not select another product or silently broaden permissions.

Contract source: https://ampcode.com/docs/sdk

## SDK route

Prefer the official Amp TypeScript SDK when Node execution is available. It executes Amp programmatically with structured streaming output and thread continuity.

```sh
npm install @ampcode/sdk
export AMP_API_KEY="private-key-not-logged"
```

```ts
import { execute } from "@ampcode/sdk";

for await (const message of execute({
  prompt: "Perform the scoped handoff task.",
})) {
  if (message.type === "result" && !message.is_error) console.log(message.result);
}
```

To continue an explicitly selected thread, pass its exact thread ID in the execution options; the newest thread is not an explicit resume. Retain the thread ID, streamed events, permission configuration, and artifact checks. If the SDK route is unavailable, use the pinned CLI fallback below.

## CLI fallback

Run from the selected checkout:

```sh
command -v amp
amp --version
amp --help

# New headless task, only when creation was requested.
amp --execute 'Perform the scoped task and verify its artifact.' --stream-json
```

`amp threads continue` resumes an explicitly selected thread; it does not select the newest thread for you. Declare permissions explicitly per execution. Autonomous runs modify files and execute commands, so unattended execution needs explicit operator authorization.

## Independent local launches

When the operator requests a **new independent local task**, create one fresh SDK-owned Amp run or `amp --execute` process in the selected checkout with its complete prompt supplied through the authorized route. The launching harness must retain a real execution handle for that lane; an executor-owned background job, a `nohup` child whose parent will exit, a thread record, or a launch acknowledgment is not a running task. Do not substitute an existing-thread continuation for a requested fresh run. Before reporting a launch, confirm both the execution is alive and Amp emitted its initial event.

## Handoff workflow

When the user redirects this task here, stop advancing the superseded attempt and deliver the handoff; do not finish your own approach first. Preserve the goal, state, constraints, and requested outputs without prescribing the sender's tool recipe unless the user chose that method. Relay any new approval question to the user rather than answering on their behalf. An existing approval applies only within its original scope.

1. Capture a concise packet containing the objective, current state, decisions, relevant artifacts, constraints, exact next action, acceptance criteria, and return channel.
2. Keep operator identity, product, client, channel, model or inference mechanism, and execution adapter separate. Do not infer the target from the application currently in use.
3. Discover the native Amp surface in the target environment. When the `amp` CLI is available, inspect its supported commands and options before using it.
4. Prefer continuing the explicitly selected existing thread. Ask when more than one thread is a plausible match.
5. Deliver the packet through the authorized route without copying secrets or private transcripts into it.
6. Report the selected target, delivery mechanism, thread reference when appropriate, and the delivery receipt. If the native path is unavailable, return a manual handoff packet without switching harnesses.

Progress advisories. While running, a lane may report milestones against the packet's expected result as advisory messages carrying an optional status: `started`, `milestone`, `blocked`, or `done`. Status is self-reported presence, never proof of completion — the activating agent reads it to understand progress without parsing prose, and verifies the result itself. This shared advisory vocabulary carries no control state and never blocks the lane. A spawner that wants these reports subscribes to the lane; `blocked` and `done` reports fan out to subscribers, and anyone may subscribe.

## Amp-specific boundaries

- Treat thread IDs as local routing metadata, not portable identity.
- Never invent an `amp` flag, thread, or successful delivery.
- Do not mutate a thread shared with another operator or lane without explicit authorization.
- Do not use Amp subagents, schedules, or connectors unless the operator explicitly asks for them.
