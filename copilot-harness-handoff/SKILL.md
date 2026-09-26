---
name: copilot-harness-handoff
description: Hand off work to a GitHub Copilot CLI session, or prepare a portable handoff packet when Copilot is the explicitly selected target.
---

# Copilot harness handoff

## Direct lane spawning

For a new handoff, spawn the requested number of independent caller-owned Copilot executions directly through the contract-authorized SDK or CLI route. Each lane gets its own prompt, owned session/process handle, and result. A per-lane owned SDK client is that lane's execution handle, not a shared server. Do not use a lane manager, leader, coordinator, relay, shared CLI server, background task manager, or parent agent to fan out or run the lanes. Existing-session continuation is allowed only when the operator explicitly asks to continue that exact session.

Use this skill only when the operator explicitly selects GitHub Copilot or asks to hand work to Copilot. This adapter coordinates a handoff; it does not select another product or silently broaden permissions.

Contract source: https://docs.github.com/en/copilot/how-tos/copilot-sdk/sdk-getting-started

## SDK route

Prefer the official Copilot SDK for TypeScript or Python execution. The SDK manages a Copilot CLI server over JSON-RPC and provides session creation, resume, streaming, history, tools, hooks, and persistence.
The `approveAll` examples below are only for a task with explicit unattended
tool approval. For ordinary handoffs, use an SDK permission handler that relays
requests to the operator, or use the CLI's normal permission flow. The repo's
MCP bridge uses the CLI by default and requires `approval=unattended` before
calling its `approve_all` SDK adapter, including on resume. Its fresh SDK route
also requires an explicit model and refuses a selected workspace it cannot bind.
The MCP server process must additionally allowlist `copilot` in
`HARNESS_HANDOFF_UNATTENDED_HARNESSES`.

```sh
npm install @github/copilot-sdk
python3 -m pip install github-copilot-sdk
```

```ts
import { CopilotClient, approveAll } from "@github/copilot-sdk";

// Only after the operator explicitly authorizes unattended tool approval.
const client = new CopilotClient();
await client.start();
const session = await client.createSession({
  model: "MODEL_ID",
  onPermissionRequest: approveAll,
});
const response = await session.sendAndWait({ prompt: "Perform the scoped handoff task." });
await client.stop();
```

```python
import asyncio
from copilot import CopilotClient
from copilot.session import PermissionHandler

# Only after the operator explicitly authorizes unattended tool approval.
async def main():
    async with CopilotClient() as client:
        async with await client.create_session(
            on_permission_request=PermissionHandler.approve_all,
            model="MODEL_ID",
        ) as session:
            await session.send("Perform the scoped handoff task.")

asyncio.run(main())
```

`approveAll`-style helpers apply only when managed settings are disabled and
the operator authorized unattended approval for this task. For resumable sessions, create the session with your own meaningful session ID and retain it; a generated ID cannot be resumed later. Re-provide BYOK provider configuration when resuming, since API keys are never persisted. A per-lane owned SDK client is that lane's execution handle, not a shared server. If the SDK route is unavailable, use the pinned CLI fallback below.

## CLI fallback

Run from the selected checkout:

```sh
command -v copilot
copilot --version
copilot help

# New non-interactive task, only when creation was requested.
copilot -s -p 'Perform the scoped task and verify its artifact.'

# Export the transcript after non-interactive completion for auditing.
copilot -s -p 'Perform the scoped task.' --share /absolute/private/copilot-session.md
```

`-s` suppresses stats and decoration for script piping. `--continue` resumes the last session and `--resume` browses sessions; neither selects an operator-chosen exact session for you. `--allow-all`/`--yolo` and per-tool allow/deny rules apply only with explicit operator authorization. Discover the model with the installed CLI before pinning one.

## Independent local launches

When the operator requests a **new independent local task**, create one fresh SDK-owned Copilot session or `copilot -p` process in the selected checkout with its complete prompt supplied through the authorized route. The launching harness must retain a real execution handle for that lane; an executor-owned background job, a `nohup` child whose parent will exit, a session record, or a launch acknowledgment is not a running task. Do not substitute an existing-session continuation for a requested fresh run. Before reporting a launch, confirm both the execution is alive and Copilot emitted its initial event.

## Handoff workflow

When the user redirects this task here, stop advancing the superseded attempt and deliver the handoff; do not finish your own approach first. Preserve the goal, state, constraints, and requested outputs without prescribing the sender's tool recipe unless the user chose that method. Relay any new approval question to the user rather than answering on their behalf. An existing approval applies only within its original scope.

1. Capture a concise packet containing the objective, current state, decisions, relevant artifacts, constraints, exact next action, acceptance criteria, and return channel.
2. Keep operator identity, product, client, channel, model or inference mechanism, and execution adapter separate. Do not infer the target from the application currently in use.
3. Discover the native Copilot surface in the target environment. When the `copilot` CLI is available, inspect its supported commands and options before using it.
4. Prefer continuing the explicitly selected existing session. Ask when more than one session is a plausible match.
5. Deliver the packet through the authorized route without copying secrets or private transcripts into it.
6. Report the selected target, delivery mechanism, session reference when appropriate, and the delivery receipt. If the native path is unavailable, return a manual handoff packet without switching harnesses.

Progress advisories. While running, a lane may report milestones against the packet's expected result as advisory messages carrying an optional status: `started`, `milestone`, `blocked`, or `done`. Status is self-reported presence, never proof of completion — the activating agent reads it to understand progress without parsing prose, and verifies the result itself. This shared advisory vocabulary carries no control state and never blocks the lane. A spawner that wants these reports subscribes to the lane; `blocked` and `done` reports fan out to subscribers, and anyone may subscribe.

## Copilot-specific boundaries

- Treat session IDs as local routing metadata, not portable identity.
- Never invent a `copilot` flag, session, model, or successful delivery.
- Do not use Team Admin API keys where the SDK does not support them.
- Do not carry one product's subscription, OAuth token, or API key into another product.
- Premium-request billing applies to SDK and CLI execution; verify quota behavior before launching parallel lanes.
