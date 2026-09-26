---
name: gemini-harness-handoff
description: Hand off work to a Gemini CLI session, or prepare a portable handoff packet when Gemini CLI is the explicitly selected target.
---

# Gemini CLI harness handoff

## Direct lane spawning

For a new handoff, spawn the requested number of independent caller-owned Gemini CLI processes directly. Each lane gets its own prompt, process handle, and result. Do not use a lane manager, leader, coordinator, relay, server, background task manager, or parent agent to fan out or run the lanes. Existing-session continuation is allowed only when the operator explicitly asks to continue that exact session.

Use this skill only when the operator explicitly selects Gemini CLI or asks to hand work to Gemini CLI. This is not Antigravity, the Gemini API, or a Gemini web product. This adapter coordinates a handoff; it does not select another product or silently broaden permissions.

Contract source: https://www.geminicli.com/docs/cli/headless

## CLI route

There is no published first-party SDK for native Gemini CLI sessions in this contract. Use the official headless interface for programmatic work. Run from the selected checkout:

```sh
command -v gemini
gemini --version
gemini --help

# New headless task, only when creation was requested.
gemini -p 'Perform the scoped task and verify its artifact.' --output-format json

# Stream JSONL events from one headless turn.
gemini -p 'Perform the scoped task.' --output-format stream-json

# Continue the exact retained session.
gemini --resume SESSION_ID -p 'Perform the agreed next step.'
```

`gemini --resume` without an ID selects the most recent session; `gemini --list-sessions` lists candidates by project. Neither is a substitute for an operator-selected exact session ID. Sessions are project-scoped and retained under the CLI's session store; switching directories switches history scope. Verify the installed auth surface before running: consumer free and Pro/Ultra tiers moved to Antigravity CLI, while enterprise and API-key use remains on Gemini CLI.

## Independent local launches

When the operator requests a **new independent local task**, create one fresh `gemini -p` process in the selected checkout with its complete prompt supplied through the authorized route. The launching harness must retain a real process handle for that process; an executor-owned background job, a `nohup` child whose parent will exit, a session record, or a launch acknowledgment is not a running task. Do not substitute `--resume`, a checkpoint rewind, or an Antigravity session for a requested fresh run. Before reporting a launch, confirm both the process is alive and Gemini emitted its initial event.

## Handoff workflow

When the user redirects this task here, stop advancing the superseded attempt and deliver the handoff; do not finish your own approach first. Preserve the goal, state, constraints, and requested outputs without prescribing the sender's tool recipe unless the user chose that method. Relay any new approval question to the user rather than answering on their behalf. An existing approval applies only within its original scope.

1. Capture a concise packet containing the objective, current state, decisions, relevant artifacts, constraints, exact next action, acceptance criteria, and return channel.
2. Keep operator identity, product, client, channel, model or inference mechanism, and execution adapter separate. A Gemini model behind another harness does not make Gemini CLI the target.
3. Discover the native Gemini CLI surface in the target environment and read the installed help before using version-sensitive flags.
4. Prefer continuing the explicitly selected existing session. Ask when more than one session is a plausible match.
5. Deliver the packet through the authorized route without copying secrets or private transcripts into it.
6. Report the selected target, delivery mechanism, session reference when appropriate, and the delivery receipt. If the native path is unavailable, return a manual handoff packet without switching harnesses.

Progress advisories. While running, a lane may report milestones against the packet's expected result as advisory messages carrying an optional status: `started`, `milestone`, `blocked`, or `done`. Status is self-reported presence, never proof of completion — the activating agent reads it to understand progress without parsing prose, and verifies the result itself. This shared advisory vocabulary carries no control state and never blocks the lane. A spawner that wants these reports subscribes to the lane; `blocked` and `done` reports fan out to subscribers, and anyone may subscribe.

## Gemini-specific boundaries

- Treat `gemini` and `agy` as different products with different session stores.
- Never invent a `gemini` flag, session, model, quota tier, or successful delivery.
- Do not substitute the Gemini API, Antigravity, or another harness's Gemini-backed model for Gemini CLI session control.
- Check exit codes and result events; a zero exit alone does not prove the delegated work succeeded.
