---
name: openhands-harness-handoff
description: Hand off work to an OpenHands conversation, or prepare a portable handoff packet when OpenHands is the explicitly selected target.
---

# OpenHands harness handoff

## Direct lane spawning

For a new handoff, spawn the requested number of independent caller-owned OpenHands executions directly through the contract-authorized SDK or CLI route. Each lane gets its own prompt, owned conversation/process handle, and result. A per-lane owned SDK conversation is that lane's execution handle, not a shared backend. Do not use a lane manager, leader, coordinator, relay, shared server, background task manager, or parent agent to fan out or run the lanes. Existing-conversation continuation is allowed only when the operator explicitly asks to continue that exact conversation.

Use this skill only when the operator explicitly selects OpenHands or asks to hand work to OpenHands. This adapter coordinates a handoff; it does not select another product or silently broaden permissions.

Contract source: https://docs.openhands.dev/sdk

## SDK route

Prefer the official OpenHands Python SDK when Python execution is available. It provides agents, tools, local or remote workspaces, conversations, events, and confirmation policies.

```sh
python3 -m pip install openhands-sdk
```

```python
from openhands.sdk import LLM, Agent, Conversation

llm = LLM(model="MODEL_ID", api_key="private-key-not-logged")
agent = Agent(llm=llm, tools=[])
conversation = Conversation(agent=agent, workspace="/absolute/workspace")
conversation.send_message("Perform the scoped handoff task.")
conversation.run()
```

Select the workspace backend explicitly: local machine, Docker/ephemeral workspace, or remote Agent Server. A per-lane owned conversation is that lane's execution handle, not a shared backend. Resume or load only the exact retained conversation ID. Retain the conversation ID, backend selection, confirmation policy, streamed events, and artifact checks. If the SDK route is unavailable, use the pinned CLI fallback below.

## CLI fallback

Headless CLI mode always runs with always-approve and cannot be changed. Use it only with explicit unattended authorization.

```sh
command -v openhands
openhands --version
openhands --help

# New headless task, only when creation and unattended execution were requested.
openhands --headless --json --file /absolute/handoff-task.txt

# Continue the exact retained conversation.
openhands --resume CONVERSATION_ID --headless --json --file /absolute/handoff-followup.txt
```

`openhands --resume` without an ID lists recent conversations; `--resume --last` takes the most recent. Neither selects an operator-chosen exact conversation for you. Override stored LLM settings with `LLM_API_KEY`, `LLM_MODEL`, and `LLM_BASE_URL` only through explicitly authorized environment configuration. Conversation history is stored under the CLI's session root; Docker, local, and cloud backends are separate surfaces.

## Independent local launches

When the operator requests a **new independent local task**, create one fresh SDK-owned OpenHands conversation or `openhands --headless` process with its complete task supplied through the authorized route. The launching harness must retain a real execution handle for that lane; an executor-owned background job, a `nohup` child whose parent will exit, a conversation record, or a launch acknowledgment is not a running task. Do not substitute `--resume`, a served web session, or a cloud conversation for a requested fresh local run. Before reporting a launch, confirm both the execution is alive and OpenHands emitted its initial event.

## Handoff workflow

When the user redirects this task here, stop advancing the superseded attempt and deliver the handoff; do not finish your own approach first. Preserve the goal, state, constraints, and requested outputs without prescribing the sender's tool recipe unless the user chose that method. Relay any new approval question to the user rather than answering on their behalf. An existing approval applies only within its original scope.

1. Capture a concise packet containing the objective, current state, decisions, relevant artifacts, constraints, exact next action, acceptance criteria, and return channel.
2. Keep operator identity, product, client, channel, model or inference mechanism, and execution adapter separate. Do not infer the target from the application currently in use.
3. Discover the native OpenHands surface in the target environment. When the `openhands` CLI is available, inspect its supported commands and options before using it.
4. Prefer continuing the explicitly selected existing conversation. Ask when more than one conversation is a plausible match.
5. Deliver the packet through the authorized route without copying secrets or private transcripts into it.
6. Report the selected target, delivery mechanism, conversation reference when appropriate, and the delivery receipt. If the native path is unavailable, return a manual handoff packet without switching harnesses.

Progress advisories. While running, a lane may report milestones against the packet's expected result as advisory messages carrying an optional status: `started`, `milestone`, `blocked`, or `done`. Status is self-reported presence, never proof of completion — the activating agent reads it to understand progress without parsing prose, and verifies the result itself. This shared advisory vocabulary carries no control state and never blocks the lane. A spawner that wants these reports subscribes to the lane; `blocked` and `done` reports fan out to subscribers, and anyone may subscribe.

## OpenHands-specific boundaries

- Treat conversation IDs as backend-scoped routing metadata, not portable identity.
- Never invent an `openhands` flag, conversation, backend, or successful delivery.
- Never override headless always-approve; there is no supported flag for it.
- Do not mix local, Docker, served, and cloud backends within one lane without explicit authorization.
