# Harness route coverage and contract limits

Snapshot date: 2026-10-01. This report describes this repository's current
Handoff bridge and the restrictions in `skills-src/contracts.json`. These
entries describe Handoff's contract, not the full capabilities of each vendor SDK.

Snapshot SHA-256: `6fa8bae83bc10b997e247d09254e8c01edead7b72383ecd97e01e267cc8247fa`.
The authoritative inputs remain `skills-src/contracts.json`,
`mcp_bridge/sdk_executors.py`, and `EVIDENCE.md`.

| Harness | Current bridge route | Continuation declared by Handoff | Handoff-local restrictions |
| --- | --- | --- | --- |
| Amp | CLI | SDK or CLI | Latest thread is not an exact continuation target; shared-thread mutation is restricted. |
| Antigravity | Python SDK or CLI | CLI | SDK takeover of native conversations, Gemini API session control, and newest-session guessing are restricted. |
| Claude | Python SDK or CLI | SDK or CLI | “Continue” is not exact resume; concurrent resume and subscription OAuth reuse are restricted. |
| Cline | CLI | SDK or CLI | Latest-session guessing and auto-approval by default are restricted. |
| Codex | CLI | Forbidden | Resume, fork, thread listing, app-server, and Python SDK routes are outside this Handoff contract. |
| Copilot | Python SDK or CLI | SDK or CLI | Team admin keys, approve-all by default, and cross-surface session reuse are restricted. |
| Cursor | Python SDK or CLI | SDK or CLI | Team admin keys, editor takeover, and newest-session guessing are restricted. |
| Droid | CLI | SDK or CLI | Unselected daemon takeover, assumed organization API access, and latest-session guessing are restricted. |
| Gemini CLI | CLI | CLI | Antigravity substitution, latest-session guessing, and Gemini API control of CLI sessions are restricted. |
| Grok Build | CLI/protocol | Protocol or CLI | xAI API substitution, treating an unforked session ID as resume, and newest-session guessing are restricted. |
| Junie | CLI | CLI | Latest-session guessing, auth flags that expose tokens in logs, and IDE-session takeover are restricted. |
| Muse | Python SDK or CLI | SDK or CLI | Shared-host fan-out, cross-host takeover, and latest-session guessing are restricted. |
| OpenCode | CLI | SDK or CLI | Shared-backend fan-out, newest-session guessing, and sharing for private handoff are restricted. |
| OpenHands | Python SDK or CLI | SDK or CLI | Headless approval override and cross-backend session reuse are restricted. |

There are 41 restriction entries across these 14 Handoff contracts. Many encode
useful safeguards: select the exact session, require an explicit approval
posture, keep credentials within their authorized surface, and avoid ambiguous
shared writers. Codex's route list is a Handoff scope decision. None of these
entries means that the underlying SDK lacks a capability or that another
product must omit it.

Any change to Handoff's own restrictions must start from the authored contract
and follow this repository's generator workflow.
