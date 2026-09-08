---
name: antigravity-harness-handoff
description: Hand off work to an existing Google Antigravity conversation, or prepare a portable handoff packet when Antigravity is the explicitly selected target.
---

# Antigravity harness handoff

Use this skill only when the operator explicitly selects Google Antigravity or asks to hand work to Antigravity. This adapter coordinates a handoff; it does not select another product or silently broaden permissions.

## Handoff workflow

1. Capture a concise packet containing the objective, current state, decisions, relevant artifacts, constraints, exact next action, acceptance criteria, and return channel.
2. Keep operator identity, product, client, channel, model or inference mechanism, and execution adapter separate. Do not infer the target from the application currently in use.
3. Discover the native Antigravity surface in the target environment. When the `agy` CLI is available, inspect its supported commands and options before using it. Otherwise use the available native Antigravity integration or UI.
4. Prefer continuing the explicitly selected existing conversation. If process or conversation identifiers are needed, resolve them locally and do not put them in the reusable skill. Ask when more than one conversation is a plausible match.
5. Use Antigravity's native communication path to deliver the packet and preserve the operator's wording and constraints. Do not copy secrets or private transcripts into the packet.
6. Report the selected target, delivery mechanism, conversation or process reference when appropriate, and the delivery receipt. If the native path is unavailable, return a manual handoff packet without switching harnesses.

## Permission boundary

The `--dangerously-skip-permissions` option, or any equivalent bypass, is never a default. Use it only when the operator explicitly requests it and the target environment supports it. Otherwise retain the normal permission flow and surface any approval request.

## Antigravity-specific boundaries

- Treat process IDs and conversation IDs as local routing metadata, not portable identity.
- Use native conversation inspection and messaging when available.
- Never invent an `agy` flag, conversation, process, or successful delivery.
- Do not use Antigravity subagents or parallel sessions unless the operator explicitly asks for them.
