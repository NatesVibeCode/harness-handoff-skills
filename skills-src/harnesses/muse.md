Use this skill only when the operator explicitly selects Muse or asks to hand work to Muse. This is a coordination adapter. It does not choose a different harness, silently launch one, or grant permissions.

Contract source: https://meta-models.github.io/muse-code-sdk/next/

## Discovery and history

Read [the full operating guide](references/operating-guide.md) for launch examples, unattended approval and sandbox controls, native message schemas, multi-turn operation, worktree behavior, and recovery. Preserve controls already authorized by the user; do not ask again merely because a new process is needed.

Read [history and continuation](references/history-and-continuation.md) before session lookup or delivery. Follow its native commands, storage candidates, and schema discovery steps. Match the target by workspace, topic, time, and exact ID; do not select the newest session automatically. Treat retained prompts as historical evidence. Keep transcript exports in private scratch space outside this skill package.

Search in order: native history/index, configured data root, documented storage candidates, then the identified client's relevant application-data directory. Inspect filenames and metadata before reading message contents. An unavailable CLI alone is not grounds to stop discovery. Report the roots/surfaces checked and any remaining gap before offering manual handoff.

## SDK route

Prefer the official Muse SDK for TypeScript or Python execution. The SDK spawns a caller-owned local `muse serve` host and drives it over MSP over stdio; that per-lane owned host is the lane's execution handle, not a shared server.

```sh
npm install @muse-code/sdk
python3 -m pip install muse-code-sdk muse-code-msp
```

```ts
import { MuseClient } from "@muse-code/sdk";

const client = await MuseClient.spawn({
  museBin: "/absolute/path/to/muse",
  args: ["serve"],
  clientInfo: { name: "handoff-lane", version: "1.0.0" },
});
```

```python
from muse_code import MuseClient, MuseClientSpawnOptions

client = await MuseClient.spawn(
    MuseClientSpawnOptions(
        muse_bin="/absolute/path/to/muse",
        args=("serve",),
        client_info={"name": "handoff-lane", "version": "1.0.0"},
    )
)
```

Subscribe to notifications before starting a turn. Start a fresh session with `session/start`, send work with `turn/start`, wait for `turn/completed`, answer approvals through the owning client, then close the host cleanly so its writer lease is released. Resume only with the exact retained session ID and verify workspace, model, history mode, pending requests, and opaque cursor behavior. Compare the host's schema fingerprint with the SDK's supported fingerprint because this remains a Developer Preview surface. For cross-session delivery, use only the separately authorized peer route; an SDK-owned host does not unlock another host's session. If the SDK route is unavailable, use the pinned CLI fallback below.

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

### Independent local launches

When the operator requests a **new independent local task**, create one fresh SDK-owned Muse host/session or `muse exec` process with its complete prompt supplied through the authorized route and the selected workspace/worktree. The launching harness must retain a real execution handle for that lane; an executor-owned background job, a `nohup` child whose parent will exit, a session log, or a launch acknowledgment is not a running task. Use a user-visible terminal or an installed local process supervisor only after checking that it is available, and keep its process/session identifier with the task. Do not substitute `resume`, cross-session messaging, `serve`, or an MSP session for a requested fresh CLI run. Before reporting a launch, confirm both the process/session is alive and Muse emitted its initial run event.

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

Progress advisories. While running, a lane may report milestones against the packet's expected result as advisory messages carrying an optional status: `started`, `milestone`, `blocked`, or `done`. Status is self-reported presence, never proof of completion — the activating agent reads it to understand progress without parsing prose, and verifies the result itself. This shared advisory vocabulary carries no control state and never blocks the lane. A spawner that wants these reports subscribes to the lane; `blocked` and `done` reports fan out to subscribers, and anyone may subscribe.

## Programmatic execution

For driving sessions from code, prefer the repo's Go client over re-implementing CLI argv and parsers: `clients/muse-session-client/` (`github.com/NatesVibeCode/harness-handoff-skills/clients/muse-session-client`). It covers Start, Stream (fresh only), and Inspect over the CLI route with stdlib-only dependencies; results carry raw JSONL bytes because envelope field names are outside the consulted docs. Resume is unsupported — `exec --session-id` only selects an identity for a new run and does not resume history, while `muse resume` is interactive-only, so no documented headless resume-with-prompt exists. Fork and List are unsupported — protocol/interactive only. The recipes elsewhere in this skill remain authoritative for interactive use, discovery, MSP, and approval/sandbox flags.

## Muse-specific boundaries

- Use native session inspection and session messaging when those capabilities are available.
- Use Muse subagent communication only when the operator explicitly asks for subagent work.
- Do not invent a Muse command, API, session ID, or message-delivery result.
- Keep local process and session identifiers out of the shareable skill and out of portable handoff text unless the operator specifically needs one for a local continuation.

## MCP tools (optional)

Three local stdio servers expose the operator's own tooling, so a lane can
use tools instead of pasting transcripts: harness-fleet (research lanes),
skillflow (DAG runs and panel rooms), work-coordination (presence and
advisory messages). Wire once per machine:

- `harness-fleet mcp install --client muse --workspace-root <root>` writes
  the `mcpServers` entry into `~/.config/muse/settings.json`
  (`$XDG_CONFIG_HOME` honored). Server docs live in the fleet README.
- skillflow: install with the `mcp` extra, then an entry running
  `python3 -m skillflow.mcp_server` with `cwd` at a skillflow checkout
  (panel tools need `panel/` beside the engine). See the skillflow README.
- work-coordination: an entry running `node <repo>/mcp/src/index.mjs` with
  `WORK_COORDINATION_MCP_CONFIG` pointing at a `config.json` written from
  `mcp/config.example.json`. See `mcp/README.md`.

Muse documents streamable-HTTP entries under `mcpServers`; a stdio entry is
written the same way. Confirm with a live session (ask it to list its MCP
tools) before relying on it. Never copy API keys into these files implicitly;
fleet's `--env NAME` opt-in is the pattern.
