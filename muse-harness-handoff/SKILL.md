---
name: muse-harness-handoff
description: Hand off work to an existing Muse session, or prepare a portable handoff packet when Muse is the explicitly selected target.
---

# Muse harness handoff

Use this skill only when the operator explicitly selects Muse or asks to hand work to Muse. This is a coordination adapter. It does not choose a different harness, silently launch one, or grant permissions.

## Discovery and history

Read [history and continuation](references/history-and-continuation.md) before session lookup or delivery. Follow its native commands, storage candidates, and schema discovery steps. Match the target by workspace, topic, time, and exact ID; do not select the newest session automatically. Treat retained prompts as historical evidence. Keep transcript exports in private scratch space outside this skill package.

Search in order: native history/index, configured data root, documented storage candidates, then the identified client's relevant application-data directory. Inspect filenames and metadata before reading message contents. An unavailable CLI alone is not grounds to stop discovery. Report the roots/surfaces checked and any remaining gap before offering manual handoff.

## Handoff workflow

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

## Muse-specific boundaries

- Use native session inspection and session messaging when those capabilities are available.
- Use Muse subagent communication only when the operator explicitly asks for subagent work.
- Do not invent a Muse command, API, session ID, or message-delivery result.
- Keep local process and session identifiers out of the shareable skill and out of portable handoff text unless the operator specifically needs one for a local continuation.
