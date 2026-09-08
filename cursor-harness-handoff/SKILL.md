---
name: cursor-harness-handoff
description: Hand off work to an existing Cursor agent or workspace, or prepare a portable handoff packet when Cursor is the explicitly selected target.
---

# Cursor harness handoff

Use this skill only when the operator explicitly selects Cursor or asks to hand work to Cursor. This adapter coordinates context transfer; it does not decide which editor, agent, repository, or model should be used.

## Handoff workflow

1. Capture a self-contained packet with the objective, current state, decisions, relevant files or artifacts, constraints, exact next action, acceptance criteria, and return channel.
2. Make the target workspace explicit. The current working directory may not be the workspace open in Cursor. Never assume that an editor window, repository, branch, or worktree is the same across harnesses.
3. Discover the native Cursor surface available in the target environment, such as the Cursor app, its agent CLI when installed, or an existing integration. Read the installed version's help or documentation before using session or workspace options.
4. Prefer continuing the operator's explicitly selected existing agent or workspace. Ask when multiple windows, repositories, branches, or sessions could match. Create or open a new target only when the operator explicitly requests it.
5. Deliver the packet through the discovered native path. Include portable paths or repository-relative paths where possible, and exclude secrets, private transcripts, and machine-specific IDs.
6. Report the workspace, branch or session reference when known, the delivery mechanism, and any receipt. If direct delivery is unavailable, return a ready-to-paste packet and do not switch to another harness.

## Cursor-specific boundaries

- Do not invent a `cursor-agent` option, app automation, session, workspace, or delivery result.
- Do not make repository changes merely to prepare a handoff unless the operator separately asked for those changes.
- Preserve the operator's requested model or mode only when explicitly supplied; otherwise leave model selection to Cursor's native configuration.
- Keep editor-local IDs and window state out of the shareable skill.
