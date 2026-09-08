---
name: grok-harness-handoff
description: Hand off work to Grok through an explicitly selected native surface, or prepare a portable handoff packet when no direct Grok bridge is available.
---

# Grok harness handoff

Use this skill only when the operator explicitly selects Grok or asks to hand work to Grok. Grok may be exposed through a product UI, an xAI API, a CLI, or a connector. This skill must discover which surface is actually available instead of assuming that a `grok` executable or a particular endpoint exists.

## Discovery and history

Read [history and continuation](references/history-and-continuation.md) before session lookup or delivery. Follow its native commands, storage candidates, and schema discovery steps. Match the target by workspace, topic, time, and exact ID; do not select the newest session automatically. Treat retained prompts as historical evidence. Keep transcript exports in private scratch space outside this skill package.

Search in order: native history/index, configured data root, documented storage candidates, then the identified client's relevant application-data directory. Inspect filenames and metadata before reading message contents. An unavailable CLI alone is not grounds to stop discovery. Report the roots/surfaces checked and any remaining gap before offering manual handoff.

## Handoff workflow

1. Capture the objective, current state, decisions, relevant artifacts, constraints, exact next action, acceptance criteria, and return channel in a short packet.
2. Keep operator identity, Grok product surface, client, channel, model or inference mechanism, and execution adapter separate. Never infer a Grok target from the fact that the current harness is conversational.
3. Confirm the native surface and authorization: Grok UI, xAI API, installed CLI, or connector. Use only its documented operations and the credentials already authorized for that surface.
4. Prefer continuing an explicitly selected existing conversation or session. If the surface has no resumable session, state that and use a new conversation only when the operator asked for one.
5. Deliver the packet without exposing API keys, cookies, private transcripts, or hidden system context. If an API call is used, record the model and endpoint only when they are known from the active configuration or operator request.
6. Report delivery only when the native surface returns a usable receipt or visible confirmation. Otherwise provide a ready-to-paste packet and the exact limitation; never claim that Grok received it.

## Grok-specific boundaries

- Do not invent a Grok CLI, API route, model name, session ID, or connector.
- Do not silently convert a handoff into an xAI API call; that is a different execution surface and may have different privacy, billing, and model behavior.
- Treat local conversation IDs and provider request IDs as routing metadata, not shareable skill content.
- Do not substitute Claude, Codex, Muse, Antigravity, OpenCode, or Cursor when Grok is unavailable.
