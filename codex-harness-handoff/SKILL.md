---
name: codex-harness-handoff
description: Launch one or more explicitly requested fresh Codex sessions with autonomous handoff prompts. Use when the operator explicitly asks to hand work to Codex; do not use for an existing-session follow-up.
---

# Codex harness handoff

## Direct lane spawning

For a new handoff, spawn the requested number of independent caller-owned Codex executions directly through the contract-authorized fresh SDK or CLI route. Each lane gets its own prompt, owned thread/process handle, and result. Do not use a lane manager, leader, coordinator, relay, shared server, background task manager, or parent agent to fan out or run the lanes. Continuation, resume, fork, and app-server routes remain forbidden for this fresh-only handoff.

Use this skill only when the operator explicitly selects a **new Codex handoff**. It creates one fresh Codex thread in the operator-selected workspace. The fresh thread, not the sending harness, continues the task.

Create more than one thread only when the operator explicitly asks for a count, parallel lanes, or equivalent—for example, “spawn four lanes to attack this in parallel.” Do not infer parallelism from task size. Every requested lane is a separate fresh thread with its own prompt, output, and retained execution handle: either a TypeScript SDK thread handle or a `codex exec` process handle.

Do not inspect or attach to existing Codex sessions. Do not use `codex agents`, `codex queue`, `codex resume`, `codex exec resume`, `codex exec fork`, `codex app-server`, the Python SDK, a browser, or an app-server protocol. Those are existing-session, management, or server routes, not this fresh-only handoff.

Contract source: https://developers.openai.com/codex/sdk

## Fresh SDK route

Prefer the authorized TypeScript SDK for a new thread when Node execution is available. It controls a local Codex thread; it does not authorize resume, fork, thread listing, or app-server management.

```sh
npm install @openai/codex-sdk
```

```ts
import { Codex } from "@openai/codex-sdk";

const codex = new Codex();
const thread = codex.startThread({
  workingDirectory: "/absolute/workspace",
  skipGitRepoCheck: true,
});
const result = await thread.run("Perform the scoped handoff task.");
console.log(result.finalResponse);
```

Retain the SDK thread handle, streamed or buffered events, final response, workspace, approval/sandbox selection, and artifact checks. History for this skill means that owned fresh thread's output—not lookup, listing, resume, or export of unrelated existing sessions. Use `runStreamed` only for live observation; buffering events does not change the fresh-only boundary. If the SDK route is unavailable, use the pinned CLI fallback below.

## Handoff packet

Create one concise UTF-8 prompt file containing:

- the operator's objective and expected result;
- current state, decisions, relevant paths or supplied URLs, and any unfinished work;
- constraints, acceptance criteria, and authorization already granted;
- a direct instruction to work autonomously: make ordinary in-scope decisions, run relevant checks, and finish or report a concrete blocker without waiting for a monitor.

For multiple lanes, give each lane a bounded responsibility and its own expected result. Do not run concurrent writers against the same files unless the operator explicitly requests that overlap. Preserve user-specified lane assignments; otherwise divide the work into independent investigation, implementation, or verification responsibilities.

Keep the operator's wording and scope. Do not include secrets, private transcripts, machine-specific session IDs, or an invented tool recipe. A URL is reference material unless the operator also selects it as the workspace or requests a clone.

Progress advisories. While running, a lane may report milestones against the packet's expected result as advisory messages carrying an optional status: `started`, `milestone`, `blocked`, or `done`. Status is self-reported presence, never proof of completion — the activating agent reads it to understand progress without parsing prose, and verifies the result itself. This shared advisory vocabulary carries no control state and never blocks the lane. A spawner that wants these reports subscribes to the lane; `blocked` and `done` reports fan out to subscribers, and anyone may subscribe.

## CLI fallback: launch exactly one new session

Resolve the installed `codex` executable and use `codex exec` with the selected absolute workspace. Pass the complete handoff packet through stdin and keep the process handle, JSONL output, and final-message path.

```sh
# Default: autonomous full-access session. This prevents an unattended lane
# from stopping at Codex approval or sandbox boundaries.
codex exec -C /absolute/workspace \
  --dangerously-bypass-approvals-and-sandbox \
  --json -o /absolute/handoff-final.md - < /absolute/handoff-prompt.md
```

Use `--dangerously-bypass-approvals-and-sandbox` by default for this handoff. Omit it only when the operator explicitly selects a restricted sandbox or approval posture. Preserve an explicitly chosen model, profile, additional writable directory, or `--skip-git-repo-check` when applicable; otherwise leave Codex defaults intact.

This command starts a new persisted Codex CLI thread. Confirm its initial JSON event and retain its process identity before reporting a launch. A process exit, final-message file, or JSON event alone does not prove the delegated work succeeded; inspect the requested result before reporting completion.

Do not create a worktree, clone a repository, start a background daemon, or launch a second writer unless the operator explicitly requests that separate action.

## Programmatic execution

For driving sessions from code, prefer the repo's Go client over re-implementing CLI argv and parsers: `clients/codex-session-client/` (`github.com/NatesVibeCode/harness-handoff-skills/clients/codex-session-client`). Under this fresh-only skill use only its Start (fresh `codex exec`) path, with stdlib-only dependencies. The client also implements Resume, Fork, Stream, List, and Inspect over `codex exec` plus the documented session store, but continuation is forbidden here — the contract sets `continuation: forbidden`, this skill's lane block forbids `codex exec resume` / `codex exec fork`, and the bridge refuses codex continuation without executing. The client does not cover the TypeScript/Python SDKs, the app-server protocol, or approval/sandbox/model flags — the recipes elsewhere in this skill remain authoritative for interactive use, discovery, and those surfaces.

## MCP tools (optional)

Three local stdio servers expose the operator's own tooling, so a lane can
use tools instead of pasting transcripts: harness-fleet (research lanes),
skillflow (DAG runs and panel rooms), work-coordination (presence and
advisory messages). Wire once per machine:

- `harness-fleet mcp install --client codex --workspace-root <root>`
  appends the `[mcp_servers."harness-fleet"]` section to
  `~/.codex/config.toml`. That file is TOML and the installer is
  append-only there: read it back to confirm, and edit by hand to change it.
  Server docs live in the fleet README.
- skillflow: install with the `mcp` extra, then a section running
  `python3 -m skillflow.mcp_server` with `cwd` at a skillflow checkout
  (panel tools need `panel/` beside the engine). See the skillflow README.
- work-coordination: a section running `node <repo>/mcp/src/index.mjs`
  with a `[mcp_servers.work-coordination.env]` table setting
  `WORK_COORDINATION_MCP_CONFIG` to a `config.json` written from
  `mcp/config.example.json`. See `mcp/README.md`.

Confirm with a live session (ask it to list its MCP tools) before relying on
them. Never copy API keys into these files implicitly; fleet's `--env NAME`
opt-in is the pattern.
