---
name: opencode-harness-handoff
description: Hand off work to an existing OpenCode session, or prepare a portable handoff packet when OpenCode is the explicitly selected target.
---

# OpenCode harness handoff

Use this skill only when the operator explicitly selects OpenCode or asks to hand work to OpenCode. It is a provider-neutral handoff adapter, not a research or coding workflow and not a reason to choose OpenCode on the operator's behalf.

## Handoff workflow

1. Write a compact packet with the objective, current state, decisions, relevant files or artifacts, constraints, exact next action, acceptance criteria, and return channel.
2. Separate operator identity, target product, client, channel, model or inference mechanism, and execution adapter. The current shell, editor, or model does not establish any of these by itself.
3. Discover the OpenCode surface available in the target environment. Check for the native `opencode` CLI, its current help, an existing OpenCode session, or an available app integration. Never assume a version-specific resume, session, or run flag.
4. Prefer the operator's explicitly selected existing session. If no session is selected, ask before creating one unless the request itself explicitly authorizes a new session.
5. Deliver the packet through the native OpenCode path that was discovered. Keep credentials, API keys, private transcripts, and machine-specific IDs out of portable text.
6. Return a receipt that states what was selected and how it was delivered. If no native bridge is available, provide a ready-to-paste packet and name the missing capability; do not substitute another harness.

## OpenCode-specific boundaries

- Do not invent an OpenCode command, provider configuration, session identifier, or delivery result.
- Keep workspace identity explicit when the target may be attached to a different repository or directory.
- Preserve the requested model or provider only when the operator supplied it; otherwise leave selection to OpenCode's configured native behavior.
