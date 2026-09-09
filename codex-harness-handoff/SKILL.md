---
name: codex-harness-handoff
description: Find Codex sessions and local transcripts, hand off tasks, and continue selected conversations through supported native capabilities.
---

# Codex harness handoff

## Commands to use

Resolve the executable with `command -v codex`; check `codex --version` and the relevant subcommand help. The following command surfaces were inspected on 2026-09-09. Use the selected workspace and preserve the user's model and control choices.

```sh
# Headless task; reads the complete prompt from a UTF-8 file through stdin.
codex exec -C /absolute/workspace --json \
  -o /absolute/final-message.txt - < /absolute/task.txt

# User-selected YOLO posture: approvals and Codex sandbox both disabled.
codex exec -C /absolute/workspace \
  --dangerously-bypass-approvals-and-sandbox --json \
  -o /absolute/final-message.txt - < /absolute/task.txt

# Continue an exact retained session in a new headless process.
codex exec resume SESSION_UUID - --json < /absolute/followup.txt

# Queue a message through the native existing-session route.
codex queue --thread SESSION_UUID --message 'Continue with the agreed tests.'

# Interactive session browser and exact interactive continuation.
codex agents
codex resume SESSION_UUID

# Deliberately fork retained context into a new session.
codex exec fork --help

# Authentication status, without printing stored credentials.
codex login status
```

`--yolo` is an accepted hidden alias in the inspected root parser; the long bypass flag states its effect explicitly. Check the selected subcommand's parser before using aliases. YOLO does not change the assigned scope. Preserve an already-authorized posture without asking again for every continuation.

## Approval, sandbox, and context options

| Option | Actual distinction |
| --- | --- |
| `-s read-only` | Selects read-only sandbox policy |
| `-s workspace-write` | Selects workspace sandbox; does not mean every approval is granted |
| `-s danger-full-access` | Disables the Codex sandbox; approval is a separate setting |
| `-a never` | Never asks for command approval; rejected execution returns an error |
| `--approve-for-me` | Automatic approval review with workspace-write sandbox |
| `--dangerously-bypass-approvals-and-sandbox` | Disables both controls |
| `--add-dir PATH` | Adds a writable directory alongside the main workspace |
| `--skip-git-repo-check` | Permits deliberately selected non-Git work; no unsolicited `git init` needed |
| `--output-schema FILE` | Constrains final response shape; event stream still needs parsing |
| `--ephemeral` | Does not retain ordinary session files; avoid for recoverable work |
| `--ignore-user-config`, `--ignore-rules` | Deliberately omit those configuration sources; not routine handoff defaults |
| `-m MODEL`, `-c key=value` | Explicit model/configuration overrides; config values use TOML syntax |

Root and subcommand options differ. For example, exec-resume does not advertise every launch option. Set the subprocess cwd explicitly when resuming and use its actual help rather than moving flags between command levels by analogy.

## Desktop and server routing

When the calling application exposes native task tools, use its list/read tools to identify the task, its send tool for a follow-up, and its wait tool for completion. Preserve the returned host ID and task ID. Paginate both ordinary and archived results. A setup handle for a pending worktree is not yet a usable task UUID.

`codex agents` is a browser on the shared local app-server daemon, not a promised JSON listing command. `codex queue` is a concrete native messaging command in this version. Use an argument vector for a long message read from a file; never interpolate the file contents into shell code. Inspect queue acceptance and then the destination's actual result. Do not claim completed work from an enqueue acknowledgment.

Remote commands accept `--remote` with a supported websocket or Unix address and `--remote-auth-token-env` naming an existing token variable. A local session file is not proof that the remote host owns the current task. Starting a fresh `codex app-server` does not attach to an arbitrary running terminal. For a client you own, use its advertised protocol and distinguish thread resume from turn start/steer; preserve the exact turn ID when steering.

## Process and Git lessons

Headless `exec` works through pipes; a PTY is for interactive use. Retain the process handle and read JSONL while it runs. Keep diagnostics on stderr separate from stdout events. A final message file, zero process exit, and a successful launch are different facts: inspect errors and verify the requested files/tests before reporting success.

### Independent local launches

When the operator requests a **new independent local task**, create one fresh `codex exec` process in the selected checkout with its complete prompt supplied from a file. The launching harness must retain a real process handle for that process; an executor-owned background job, a `nohup` child whose parent will exit, a session file, or a thread-created acknowledgment is not a running task. Use a user-visible terminal or an installed local process supervisor only after checking that it is available, and keep its process/session identifier with the task. Do not substitute `resume`, `queue`, an app-server task, or a desktop-thread API for a requested fresh CLI run. Before reporting a launch, confirm both the process/session is alive and the CLI emitted its initial run event.

For a selected linked worktree, inspect `git rev-parse --show-toplevel`, `git rev-parse --git-common-dir`, `git branch --show-current`, and `git status --short` there. A historical sandbox failure came from inaccessible shared Git metadata outside the worktree. Resolve that exact directory before adding access under the authorized scope. In service contexts, bubblewrap/user-namespace failures can occur before useful model work; identify the actual failing layer and use the user's selected execution controls.

Resume restores conversation context; it does not promise rollback or transfer of dirty files. A fork of context does not establish a separate checkout. Preserve existing edits and the selected branch. Do not start a second writer to nudge a busy task. For authorized cancellation, stop the owned process, inspect its final state and changes, then decide whether exact-ID continuation or a new run is appropriate.

Read [history and continuation](references/history-and-continuation.md) before discovery or execution. The user's request selects the workspace, task, and whether to inspect, send, continue, or create a session.

## Workflow

When the user redirects this task here, stop advancing the superseded attempt and deliver the handoff; do not finish your own approach first. Preserve the goal, state, constraints, and requested outputs without prescribing the sender's tool recipe unless the user chose that method. Before replacing an owned worker for the same task, verify its identity and stop it through its native controls when cancellation is authorized; preserve its edits and do not terminate unrelated sessions. Relay any new approval question to the user rather than answering on their behalf. An existing approval applies only within its original scope.

1. Resolve the installed client and relevant help. Search native history and retained metadata by workspace, topic, date, and exact ID. Read the relevant prior request, last result, and unresolved work.
2. Deliver a concise goal, current state, constraints, input artifacts, and expected result. Let the receiving harness choose its native tools unless the user specified a method.
3. Continue the selected session when requested. A resume starts activity; use retained logs or native read tools for passive lookup. A new process is not a live-session message.
4. Preserve the user's existing authorization and requested controls. Do not import permission bypasses, fixed models, or personal services from historical examples.
5. Record session identity separately from process handles and workspace paths. Observe result events and requested artifacts before reporting completion; acceptance and process exit alone do not prove the work succeeded.
6. If one route fails, inspect other supported routes and report the exact limitation. Supply a manual packet only after applicable native discovery paths have been checked.

## Portability

Keep private transcripts and machine-specific IDs outside the skill package. Use actual local paths during a handoff, but replace them with placeholders in reusable examples. Do not confuse another harness's UUID with a Codex session merely because the formats match.
