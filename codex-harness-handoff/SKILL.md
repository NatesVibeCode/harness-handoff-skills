---
name: codex-harness-handoff
description: Launch one or more explicitly requested fresh Codex CLI sessions with autonomous handoff prompts. Use when the operator explicitly asks to hand work to Codex CLI; do not use for an existing-session follow-up.
---

# Codex CLI harness handoff

## Direct lane spawning

For a new handoff, spawn the requested number of independent Codex CLI processes directly. Do not insert a lane manager, leader, coordinator, relay, server, background task manager, or parent agent between the sender and the lanes.

Use this skill only when the operator explicitly selects a **new Codex CLI handoff**. It creates one fresh CLI session in the operator-selected workspace. The fresh session, not the sending harness, continues the task.

Create more than one session only when the operator explicitly asks for a count, parallel lanes, or equivalent—for example, “spawn four lanes to attack this in parallel.” Do not infer parallelism from task size. Every requested lane is a separate fresh `codex exec` process with its own prompt file, output file, and retained process identity.

Do not inspect or attach to existing Codex sessions. Do not use `codex agents`, `codex queue`, `codex resume`, `codex exec resume`, `codex exec fork`, `codex app-server`, a browser, or an app-server protocol. Those are existing-session or server routes, not this handoff.

## Handoff packet

Create one concise UTF-8 prompt file containing:

- the operator's objective and expected result;
- current state, decisions, relevant paths or supplied URLs, and any unfinished work;
- constraints, acceptance criteria, and authorization already granted;
- a direct instruction to work autonomously: make ordinary in-scope decisions, run relevant checks, and finish or report a concrete blocker without waiting for a monitor.

For multiple lanes, give each lane a bounded responsibility and its own expected result. Do not run concurrent writers against the same files unless the operator explicitly requests that overlap. Preserve user-specified lane assignments; otherwise divide the work into independent investigation, implementation, or verification responsibilities.

Keep the operator's wording and scope. Do not include secrets, private transcripts, machine-specific session IDs, or an invented tool recipe. A URL is reference material unless the operator also selects it as the workspace or requests a clone.

Progress advisories. While running, a lane may report milestones against the packet's expected result as advisory messages carrying an optional status: `started`, `milestone`, `blocked`, or `done`. Status is self-reported presence, never proof of completion — the activating agent reads it to understand progress without parsing prose, and verifies the result itself. This shared advisory vocabulary carries no control state and never blocks the lane. A spawner that wants these reports subscribes to the lane; `blocked` and `done` reports fan out to subscribers, and anyone may subscribe.

## Launch exactly one new session

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
