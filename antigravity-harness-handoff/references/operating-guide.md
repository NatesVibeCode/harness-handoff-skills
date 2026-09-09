# Antigravity CLI, conversations, and subagents

Checked on 2026-09-04 against local `agy` 1.1.26. This guide supports the user's chosen mode of use; it does not prescribe delegation or management roles.

## Discovery and lookup

Resolve the actual agent binary and inspect only relevant help:

```sh
command -v agy
agy --version
agy --help
agy help agents
agy help models
agy help remote-control
```

Use `agy models` and `agy agents` when a model/agent choice needs discovery. Keep existing defaults unless the user selects an override. The local help supports `--model`, `--agent`, and `--effort low|medium|high`; do not copy Muse's `--reasoning-effort xhigh` spelling. On this installation `agy` is `<resolved-agy-executable>`; both `/Applications/Antigravity.app` and `/Applications/Antigravity IDE.app` also exist.

The installed built-in guide points to the [official CLI reference](https://antigravity.google/docs/cli/reference). Consult it for commands not covered here and compare it with installed help. Do not infer a feature is absent solely because this guide omits it.

### Read-only conversation discovery

The checked local CLI has a SQLite summary cache at `~/.gemini/antigravity-cli/conversation_summaries.db`. Inspect its schema before using this version-specific query:

```python
from pathlib import Path
import sqlite3

path = Path.home() / '.gemini/antigravity-cli/conversation_summaries.db'
with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as db:
    print(db.execute('PRAGMA table_info(conversation_summaries)').fetchall())
    rows = db.execute('''
        SELECT conversation_id, title, preview, workspace_uris, project_id,
               parent_conversation_id, app_data_dir, last_modified_time,
               status, not_fully_idle, killed
        FROM conversation_summaries
        WHERE title LIKE ? OR conversation_id = ?
        ORDER BY last_modified_time DESC LIMIT 10
    ''', ('%selected topic%', 'exact-conversation-id')).fetchall()
    for row in rows:
        print(row)
```

This is a bounded discovery cache, not a live process oracle. Preserve `app_data_dir`: the inspected cache contains both `antigravity-cli` and `antigravity` origins. An empty `source` field does not resolve that distinction. Use actual workspace URIs, parent IDs, and artifacts to identify the intended conversation; do not assume the latest row is the target.

Local retained data was found under:

- `~/.gemini/antigravity-cli/conversations/` and `brain/` for CLI data.
- `~/.gemini/antigravity/conversations/` and `brain/` for app data.

Inspect filenames within the selected conversation only, then read relevant existing text artifacts. The live test exposed a readable native child transcript at `brain/<conversation-id>/.system_generated/logs/transcript.jsonl`; prefer the actual returned `log_uri` over guessing this path. Artifacts may be incomplete or stale. The sampled conversation `.db` has `steps` with BLOB payloads, not plain JSON transcript rows. Inspect schema/format before decoding. Do not use lossy binary strings as an authoritative conversation transcript, edit the store, or delete WAL files. Prefer a native readable transcript/view where available. The checked CLI help exposes no `agy export` or `agy sessions list`; do not invent them.

Interactive `/resume` offers session selection. Conversation history is workspace-scoped, and `/fork` branches conversation context without guaranteeing a separate Git checkout. Use an exact `--conversation` ID for deliberate continuation rather than relying on `--continue` amid concurrent work. [Conversation documentation](https://antigravity.google/docs/cli/conversations/)

`--project` accepts a project identifier/name in installed help; `--new-project` creates one. Resuming selects the conversation's associated project. Keep project identity separate from the subprocess working directory, and check both before work. [Projects documentation](https://antigravity.google/docs/cli/projects/)

## Launch and permissions

Set the subprocess working directory explicitly to the selected checkout. For one task:

```sh
agy --dangerously-skip-permissions --output-format stream-json \
  --print 'The exact task and expected result'
```

For a long prompt, avoid shell interpolation by reading a file and passing an argument vector:

```python
from pathlib import Path
import subprocess

prompt = Path('/absolute/task.txt').read_text()
subprocess.run(
    ['agy', '--dangerously-skip-permissions', '--output-format', 'json',
     '--print', prompt],
    cwd='/absolute/selected/workspace', check=True,
)
```

This example executes a task when run. Use the calling harness's managed process facility for long work, retain its handle, and inspect bounded progress without waiting for the whole process before reading output. Verify the resulting artifact separately from process exit.

Installed options useful for particular assignments:

| Option | Use |
|---|---|
| `--output-format text|json|stream-json` | Select output format |
| `--print-timeout 15m` | Set a task-appropriate response timeout; default is five minutes |
| `--conversation <id>` | Continue a particular retained conversation |
| `--continue` / `-c` | Continue the most recent conversation |
| `--mode plan|accept-edits` | Select execution mode; distinct from sandbox posture |
| `--json-schema /absolute/schema.json` | Constrain structured output |
| `--add-dir /absolute/path` | Add an explicitly selected workspace directory |
| `--log-file /absolute/log` | Select a CLI diagnostic log destination |
| `--disable-slash-commands` | Disable skill/slash expansion in print mode when specifically wanted |

No `--workspace`, `--prompt-file`, `--worktree`, or `exec` subcommand appears in the checked help. Do not copy those Muse patterns. If isolation is selected, prepare/use the appropriate Git worktree and launch with that working directory; record the actual resulting workspace.

### Unattended/no-sandbox posture

`--dangerously-skip-permissions` auto-approves permission requests according to installed help. It does not itself document disabling the sandbox. The official configuration uses `enableTerminalSandbox` (default false); `--sandbox` forces it on. Inspect that setting rather than assuming omission forces it off. [Sandbox documentation](https://antigravity.google/docs/cli/sandbox/)

A bounded read that avoids dumping unrelated settings:

```python
import json
from pathlib import Path
p = Path.home() / '.gemini/antigravity-cli/settings.json'
s = json.loads(p.read_text()) if p.exists() else {}
print({k: s.get(k, '<unset>') for k in ('enableTerminalSandbox', 'toolPermission')})
```

When the assignment explicitly calls for disabling an enabled persistent sandbox, apply the supported configuration route within that authorization and make its persistence clear. Do not silently change global settings merely to write a guide or run a lookup. The current local setting was absent; no setting was changed during this skill's creation. Inspect effective behavior after launch and account for child/project restrictions; a flags-only claim is insufficient.

## Native communication

### A CLI process owned by the caller

Start with `--input-format stream-json --output-format stream-json`, without `-p`. Write one NDJSON user message and flush:

```json
{"event":"user","message":{"content":"The next user-directed task"}}
```

Read `init`, `step_update`, then the turn's `result`; wait for that result before submitting the next prompt. Retain `conversation_id`. Close stdin to finish gracefully. `response` is per-turn; counters accumulate. Do not send `control_request`, `control_response`, or CLI-handled slash commands such as `/model` over this stream. Inspect `status`, errors, and stderr: approval soft-denials can coexist with exit zero. Subagent updates may include child conversation IDs, log URIs, and workspace URIs. [Headless protocol](https://antigravity.google/docs/cli/headless/)

Use this native input channel for successive turns in a process you launched. It is not an attach protocol for an arbitrary desktop process. For a retained, inactive conversation, a deliberate new-process continuation is:

```sh
agy --conversation <exact-id> --dangerously-skip-permissions \
  --output-format stream-json --print 'The authorized next task'
```

Do not use that command as passive lookup or as an assumed mailbox for a busy conversation. If ownership/activity is unclear, resolve it first using current session evidence. Preserve the distinction between continuing context and delivering a message to a running agent.

### Antigravity's own subagent backend

Have the Antigravity parent use its native `invoke_subagent` and agent-message tools, with actual conversation IDs. Official documentation supports parent, child, and peer messaging; messaging an idle child wakes it with its retained context. New children start without the parent's conversation history, so supply their required inputs. Workspace choices include `inherit`, `branch`, and `share`. Children inherit permission/sandbox scopes; killed children cannot be awakened. The live test confirmed `send_message` arguments `Recipient` (conversation ID) and `Message` (text). Use the live tool schema for additional arguments and lifecycle operations. [Subagent architecture](https://antigravity.google/docs/subagents)

There is no validated shell-level `agy send-message` in the inspected help. The external caller should communicate through its owned root process and have that root route messages natively when appropriate. Do not replace the intra-session backend with foreign mailboxes or guessed internal RPC endpoints. If the required messaging tool is unavailable, report the precise missing surface; a new worker is not equivalent to a successfully delivered message.

Interactive `/agents` shows child activity; `/tasks` covers background operations. Custom agents can be discovered in `.agents/agents/` and `~/.gemini/config/agents/`. Selecting `--agent` is not the same as spawning a child. Consult the definition schema only when creating/customizing agents is requested. [CLI subagents](https://antigravity.google/docs/cli/subagents/)

### Remote control

```sh
agy remote-control status
agy remote-control start --help
```

The local status check reported **not running**. `start` registers and starts a daemon; `--session` makes registration login-scoped rather than boot-starting. These are lifecycle changes, not required steps for local CLI orchestration. Use remote control only when the selected workflow needs that product surface; it is not a generic conversation-message CLI. [Remote control documentation](https://antigravity.google/docs/remote-control/)

## User-directed multi-session workflows

Choose from the actual assignment: independent root processes, native children under an Antigravity parent, or Antigravity's Teamwork product. Do not impose one manager, fixed model tiers, a fixed number of workers, or mandatory worktrees simply because an earlier Hermes task used them.

`/teamwork-preview` is the documented built-in team workflow. It has its own scoping/prompt-review phase, then milestone execution and verification, and is documented for paid plans. Invoke it only when selected; do not silently substitute it for ordinary subagent work or invent a noninteractive approval bypass. Preserve the chosen workspace rather than accepting an unintended default project directory. [Teamwork documentation](https://antigravity.google/docs/teamwork/)

For caller-managed workflows, record the role, task, workspace/write scope, dependencies, expected output, conversation ID, and process handle in the existing coordination artifact. Start independent work only within the requested concurrency; release dependent work after its input evidence exists. Pass concise corrections and artifact paths through native messages. Shared files need compatible ownership; isolation is a task choice rather than an automatic property of every fork.

Distinguish working, idle, approval-blocked, failed, stopped, and unknown. Check current output, permission notices, and artifacts before relaunching. On replacement, establish the old process has stopped and preserve its files and identity before starting another. For code, use appropriate diff/test evidence; for lookup, a correct answer can require no changes. Recurring monitoring is a separate user instruction, not a skill default.

