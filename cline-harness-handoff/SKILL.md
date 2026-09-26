---
name: cline-harness-handoff
description: Hand off work to a Cline agent session, or prepare a portable handoff packet when Cline is the explicitly selected target.
---

# Cline harness handoff

## Direct lane spawning

For a new handoff, spawn the requested number of independent caller-owned Cline executions directly through the contract-authorized SDK or CLI route. Each lane gets its own prompt, owned session/process handle, and result. Do not use a lane manager, leader, coordinator, relay, shared server, background task manager, or parent agent to fan out or run the lanes. Existing-session continuation is allowed only when the operator explicitly asks to continue that exact session.

Use this skill only when the operator explicitly selects Cline or asks to hand work to Cline. This adapter coordinates a handoff; it does not select another product or silently broaden permissions.

Contract source: https://docs.cline.bot/sdk/overview

## SDK route

Prefer the official Cline TypeScript SDK when Node execution is available. It embeds the same agent runtime that powers the Cline IDE extensions and CLI, with sessions, tools, providers, approvals, and persistence.

```sh
npm install @cline/sdk
```

```ts
import { Agent } from "@cline/sdk";

const agent = new Agent({ /* provider and tool configuration */ });
const result = await agent.run("Perform the scoped handoff task.");
console.log(result.text);
```

When session persistence, built-in tools, config discovery, or cross-process management is needed, use `ClineCore` instead of the stateless agent loop. Resume only with the exact retained session ID. Retain the session ID, streamed events, provider/model configuration, approval settings, and artifact checks. If the SDK route is unavailable, use the pinned CLI fallback below.

## CLI fallback

Run from the selected checkout:

```sh
command -v cline
cline --version
cline --help
cline auth
cline doctor

# New headless task, only when creation was requested.
cline --json 'Perform the scoped task and verify its artifact.'

# Passive history lookup.
cline history
```

`cline --json` emits newline-delimited JSON for scripting. Autonomous execution needs explicit auto-approval configuration; use a clean branch and review results. Re-provide provider configuration when resuming across processes. Do not log provider API keys.

## Independent local launches

When the operator requests a **new independent local task**, create one fresh SDK-owned Cline session or `cline` process in the selected checkout with its complete prompt supplied through the authorized route. The launching harness must retain a real execution handle for that lane; an executor-owned background job, a `nohup` child whose parent will exit, a session record, or a launch acknowledgment is not a running task. Do not substitute an existing-session continuation for a requested fresh run. Before reporting a launch, confirm both the execution is alive and Cline emitted its initial event.

## Handoff workflow

When the user redirects this task here, stop advancing the superseded attempt and deliver the handoff; do not finish your own approach first. Preserve the goal, state, constraints, and requested outputs without prescribing the sender's tool recipe unless the user chose that method. Relay any new approval question to the user rather than answering on their behalf. An existing approval applies only within its original scope.

1. Capture a concise packet containing the objective, current state, decisions, relevant artifacts, constraints, exact next action, acceptance criteria, and return channel.
2. Keep operator identity, product, client, channel, model or inference mechanism, and execution adapter separate. Do not infer the target from the application currently in use.
3. Discover the native Cline surface in the target environment. When the `cline` CLI is available, inspect its supported commands and options before using it.
4. Prefer continuing the explicitly selected existing session. Ask when more than one session is a plausible match.
5. Deliver the packet through the authorized route without copying secrets or private transcripts into it.
6. Report the selected target, delivery mechanism, session reference when appropriate, and the delivery receipt. If the native path is unavailable, return a manual handoff packet without switching harnesses.

Progress advisories. While running, a lane may report milestones against the packet's expected result as advisory messages carrying an optional status: `started`, `milestone`, `blocked`, or `done`. Status is self-reported presence, never proof of completion — the activating agent reads it to understand progress without parsing prose, and verifies the result itself. This shared advisory vocabulary carries no control state and never blocks the lane. A spawner that wants these reports subscribes to the lane; `blocked` and `done` reports fan out to subscribers, and anyone may subscribe.

## Cline-specific boundaries

- Treat session IDs as local routing metadata, not portable identity.
- Never invent a `cline` flag, session, provider, or successful delivery.
- Do not silently convert a handoff into a different provider, model, or endpoint.
- Do not use Cline schedules, connectors, or messaging bridges unless the operator explicitly asks for them.
