# Using Muse sessions and subagents through the CLI

Checked locally on 2026-09-04 against Muse Code 1.0.3 (1.0.3-R2198.1). This is a mechanics guide. The user's current instructions select the task, roles, models, concurrency, workspace strategy, and whether any execution is wanted.

## Discovery and lookup

Start with the smallest relevant help surface:

```sh
command -v muse
muse --version
muse --help
muse exec --help
muse resume --help
muse export --help
muse session-message --help
muse serve --help
muse trace inspect --help
muse skills --help
```

For authoritative protocol shapes from the installed binary, export the schema locally:

```sh
muse schema generate-json-schema --out /tmp/muse-schema
# Alternatively: muse schema generate-ts --out /tmp/muse-schema-ts
```

Read `msp.schema.json`: `methods` maps operations to parameter/result definitions in `$defs`; `capabilities`, `notifications`, and `errors` describe the host contract. Read the fields for the operation actually needed. Do not treat an old example or a feature absent from this guide as the complete CLI manual.

### Find a session without resuming it

`muse session-message list --json` discovers messaging targets when ingress is available; it is not a complete historical-session inventory.

The native MSP methods `session/list` and `session/read` provide read-only history without loading a session or acquiring its writer lease. `session/list` accepts `workspaceRoot`, `updatedAfter`, `limit` (default 50, maximum 200), and its own opaque pagination `cursor`. `session/read` requires `sessionId`; set `excludeItems: false` to include folded history (the default is metadata only).

When no MSP client is already available, use the retained local index for bounded discovery and `muse export` for a specific transcript. On this installation the index is `~/.local/share/muse/session-index.db`; sessions live beneath `~/.local/share/muse/sessions/`. Resolve the actual installation/data root on other machines. The index is a discovery cache, not proof a process is running. Open it read-only and inspect its schema before querying:

```python
from pathlib import Path
import sqlite3

index = Path.home() / '.local/share/muse/session-index.db'
with sqlite3.connect(index.as_uri() + '?mode=ro', uri=True) as db:
    print(db.execute('PRAGMA table_info(sessions)').fetchall())
    rows = db.execute('''
        SELECT session_id, title, workspace_root, session_log_path, updated_at_us
        FROM sessions
        WHERE title LIKE ? OR session_id = ?
        ORDER BY updated_at_us DESC LIMIT 10
    ''', ('%selected topic%', 'exact-session-uuid')).fetchall()
    for row in rows:
        print(row)
```

Use the found UUID or exact log path:

```sh
muse export --session <session-uuid-or-log-path> --out /absolute/transcript.json --redacted
```

`export` is offline and writes a self-contained JSON document with messages, tools/results, timestamps, model IDs, and lineage. Redaction supports sharing but does not justify dumping an entire transcript. Read bounded relevant excerpts. Prefer exact `--session` over `--last` when coordinating several sessions. `--last` is workspace-sensitive. Supplying `--out` without `--session` also selects the latest session; it does not select by the output filename.

Raw logs may wrap records in retained transaction frames whose `children[].record_json` strings need decoding. Do not assume every JSONL line is a plain event. Prefer export/trace or the folded MSP view before writing a parser. Correlate approval starts with their later outcomes; a historical start is not necessarily still pending.

## Launch and controls

For one headless task, write the exact prompt to a file and launch `muse exec`. A PTY is unnecessary. Use the caller's process tool to retain a process handle, poll bounded output, and observe final exit status. An interactive TUI needs a real terminal; it is not the default automation transport.

Existing selected checkout, without creating a worktree:

```sh
muse exec --json --yolo --disable-sandbox \
  --workspace /absolute/selected/checkout --worktree off \
  --prompt-file /absolute/task.txt
```

Caller-owned existing worktree:

```sh
muse exec --json --yolo --disable-sandbox \
  --workspace /absolute/repository \
  --worktree existing --worktree-existing /absolute/existing/worktree \
  --prompt-file /absolute/task.txt
```

Have Muse create a worktree when that is the selected strategy:

```sh
muse exec --json --yolo --disable-sandbox \
  --workspace /absolute/repository --worktree create \
  --worktree-base <verified-ref> --prompt-file /absolute/task.txt
```

Use the actual resolved execution root for subsequent checks. `--worktree-base` defaults to HEAD; a bare `-w` means create. Do not assume dirty changes in the original checkout are included in a created worktree. Shared workspaces and isolated worktrees are both supported choices; choose from the assignment and concurrent write boundaries.

### Exact control meanings

| Option | Meaning in the checked CLI |
|---|---|
| `--yolo` | Disable approval and sandboxing, and trust the workspace for this run |
| `--disable-sandbox` | Disable shell filesystem/network sandboxing |
| `--disable-approval` | Disable tool approval prompts |
| `--trust-workspace` | Load workspace skills/rules; trust is not saved |
| `--approval-mode never` | Approval setting; does not by itself express disabling the OS sandbox |
| `--json` | Emit JSONL events to stdout |
| `--session-id` | Select an identity for a new exec run; do not assume it resumes history |
| `--max-model-steps`, `--max-tool-output-bytes` | Optional bounds when the task needs them |
| `--model`, `--reasoning-effort` | Optional explicit selections; use user choices or installed defaults |
| `--no-foreign-personal-context` | Excludes imported personal context; use only when the assignment calls for that |

The customary order here is `muse exec --json --yolo --disable-sandbox ...`. Do not make up `--no-sandbox`, `--message`, or a `muse subagent` CLI command. Do not disable context or pin the historical `muse-spark-1.3` / `xhigh` choice by default.

`--subagent-worktree-isolation` is a compatibility capability flag. The installed help says capability defaults on, omission of the per-child request stays shared, and only an affirmative **per-child** request asks for isolation. The root flag alone does not isolate every child. Confirm the actual child tool schema and returned workspace before claiming isolation.

### Continue versus replace

To resume a retained session interactively:

```sh
muse --workspace /absolute/workspace --yolo --disable-sandbox resume <session-uuid>
```

Root options may appear on either side of `resume`. Use native messaging to communicate with a running session, rather than resuming a second writer. A new `exec` with the old task file starts another run; it is not a history-preserving continuation. If a relaunch is required, establish that the old worker has stopped, preserve the selected files/worktree, and record old and new IDs. Change only what the requested recovery needs.

## Native messaging

Three scopes must remain distinct:

| Target | Native surface |
|---|---|
| Another existing Muse session | `muse session-message` cross-session ingress |
| A child owned by a Muse parent session | Parent's native subagent tools / MSP `subagent/*` |
| A root session owned by an MSP client | `turn/start`, `turn/steer`, and native turn lifecycle operations |

### Cross-session CLI

Discover a real target, write the requested message body into a UTF-8 file, then send it through stdin:

```sh
muse session-message list --json
muse session-message send --target <exact-session-uuid> --json < /absolute/message.txt
# For a reply, use the token actually returned by the backend:
muse session-message send --target <exact-session-uuid> \
  --in-reply-to <actual-reply-token> --json < /absolute/reply.txt
```

The target may be a UUID or a resolvable session name; exact IDs avoid ambiguity. The checked help has no message-body flag. Hermes's stdin invocation reached the ingress check; its `--message` invocation failed option parsing.

On 2026-09-04, both Hermes's attempt and this guide's read-only probe returned `external_agent_ingress_closed`. End-to-end delivery was therefore **not verified**. Treat this as a backend availability condition, not an invitation to guess hidden environment variables, edit runtime registrations/leases, or type into a TUI. Recheck after a concrete host/configuration change; do not retry unchanged failures in a loop. Report the unavailable action accurately while continuing independent work.

A send receipt is acceptance, not proof that the target read, acted, or finished. Follow its actual session/view evidence.

### Muse-owned children: intra-session backend

When the assignment calls for Muse to spawn and manage children, tell that Muse parent to use its **own native subagent creation, messaging, follow-up, and result tools**. The available model tool schema governs creation arguments; the checked root CLI does not expose `muse subagent spawn`. The MSP stable schema exposes these owner operations:

| Method | Purpose |
|---|---|
| `subagent/sendMessage` | Queue a note into a running child |
| `subagent/followupTask` | Queue a further task for a child |
| `subagent/interrupt` | Ask a child to yield at its next boundary |
| `subagent/stop`, `subagent/close` | Stop or owner-close a child |
| `subagent/resume`, `subagent/reopen` | Resume/reopen as a durable later attempt |
| `subagent/readResult` | Consume a ready result; **state-changing**, not passive reading |

`sendMessage` and `followupTask` parameters:

```json
{
  "commandId": "<client-minted UUIDv7>",
  "sessionId": "<owning session UUID>",
  "subagentId": "<actual durable child ID from the parent view>",
  "body": "<nonempty note or next task>"
}
```

These are method parameters, not a complete transport request. Use the actual owner's MSP client and current exported schema. Do not pass a child ID as a root-session UUID or substitute a Codex agent ID. Acknowledgments are admission only: inspect the child's view stream and the parent's subagent item for settlement. For passive lookup, read the item's `result` field rather than consuming it with `readResult`.

### Verified model-tool spelling (2026-09-04 live test)

The model-facing native tools differ from MSP wire methods. The tested parent used `subagent_spawn`, `subagent_wait`, `subagent_read_result`, and `subagent_send_message` (displayed with a `muse.` namespace by the model).

A follow-up accepted by the native backend used this shape:

```json
{
  "command_id": "<fresh unique ID for this logical follow-up>",
  "subagent_id": "<returned child ID>",
  "mode": "followup",
  "message": "<next task>"
}
```

Use `mode: followup` for later work after the initial child result; the tested `queue` call against a terminal child was rejected. Use distinct command IDs for spawn, follow-up, and other distinct operations. Reusing the spawn ID for a different follow-up produced `durable later product attempt mirror conflicts with its command identity`. Reuse an ID only for an identical retry. The model-tool test accepted string command IDs; MSP's documented UUIDv7 requirement is a separate wire contract.

The initial `subagent_wait` used `subagent_id`, `command_id`, `wait_for: result_ready`, and `timeout_ms`. Do not confuse returned `task_ref`, child ID, and command ID. Inspect structured result content even when the outer tool result says success: a rejected operation can be returned successfully as data.

### MSP hosts and root-session turns

`muse serve` starts a native MSP session host over stdio. The client owns its stdin/stdout and is its only connection. Starting a host does not attach you to somebody else's existing host or unlock cross-session ingress.

For a user-requested client-managed workflow with the relaxed sandbox posture:

```sh
muse serve --disable-sandbox --trust-workspace
```

Unlike `exec`, `serve` does **not** offer `--yolo` or an approval CLI flag. Sandbox posture is fixed for the host lifetime; approval mode is selected on the wire through the defined `session/start` or `session/setApprovalMode` contract. Resolve the available mode from the current schema/host configuration. Do not guess a literal mode from another CLI's vocabulary.

A client can use `session/start` for new roots, `session/resume` for loading retained roots, and `session/fork` for an intentional branch. `session/start` rejects a retained/reserved supplied ID; it does not resume it. Use `turn/start` to submit input (default busy disposition is queue), or `turn/steer` with the exact `expectedTurnId` to avoid steering a later turn accidentally. Read schema/transport documentation before implementing a client; this guide has not validated a new MSP client or live child round trip.

## Multi-session workflows

Only apply orchestration when requested. The user's instructions may put the calling harness in charge, make Muse the coordinator, or define several levels. Do not import Hermes's historical “one manager” or “Muse only does hard lanes” arrangement as a universal rule.

For a requested workflow, make dependencies and outputs concrete enough to connect the sessions. Carry forward the selected role, task, workspace/write scope, inputs, expected result, and relevant IDs in the task's existing coordination artifact. Avoid a new tracker when the current task already has one. Dispatch independent work concurrently only when requested/allowed; wait for actual prerequisite results before dependent work. Shared checkout writes need compatible scopes; use isolation when selected or necessary.

Messages should state the actual correction or next task, not paste the whole history. Use the native backend appropriate to the target. On completion, inspect the required artifact, test result, or other agreed evidence before releasing dependent work. Process survival, a queued message, a successful launch, or an agent's prose alone may not meet that requirement.

For recovery, distinguish: running and progressing; waiting on approval; completed; failed; stopped; and unknown. `approval_wait.effect.started` without a later resolution identifies a pending wait. Do not restart productive work just because output is quiet. When a requested restart is needed, reconcile existing changes and process state before launching a replacement. For source work, focused tests and scoped diff readback establish what changed; a read-only answer may correctly produce no diff. Persistent monitoring schedules belong to the user's request, not automatic skill behavior.

