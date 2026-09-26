# Conformance

**Sources:** `harness-sdk-briefs/antigravity.md` (research dated
2026-09-25) plus the `antigravity` CLI skill notes (checked against `agy`
1.1.26). No installed CLI was consulted: CLI execution was suspended at
the operator's request, so flags and behaviors below are brief- and
docs-derived only.

- CLI headless: `https://antigravity.google/docs/cli/headless/`
- CLI conversations: `https://antigravity.google/docs/cli/conversations/`
- CLI install/auth: `https://antigravity.google/docs/cli/install/`
- SDK overview: `https://antigravity.google/docs/sdk/overview/`

## Surfaces

| Method | Invokes | Basis |
| --- | --- | --- |
| `Start` | `agy --output-format json --print <prompt>`; parses the envelope (`conversation_id`, `status`, `response`, `error`) | Brief pinned argv + json envelope fields |
| `Resume` | Same with `--conversation <id>` | Brief resume form |
| `Stream` | `agy --input-format stream-json --output-format stream-json [--conversation <id>]`; writes one `{"event":"user","message":{"content":…}}` frame, closes stdin, passes bytes through | Brief stdin protocol; `--conversation` combination is docs-composed |
| `Fork` | Unsupported | Fork exists in the IDE only; no CLI fork documented |
| `List` | Unsupported | No list command documented; local SQLite/transcript paths are explicitly not an API |
| `Inspect` | Unsupported | No export command documented; transcript paths are explicitly not an API |

## Notes

- Non-`SUCCESS` statuses (`ERROR`, `CANCELED`, `INTERRUPTED`, `INVALID`,
  `WAITING`, `RUNNING`) become errors carrying the envelope's `error`
  text. Unapproved tools can soft-deny with exit 0 — callers must check
  status and artifacts.
- History is workspace-scoped: the client launches from the configured
  checkout and resume requires the same one. `--continue` (= newest) is
  never used.
- The stream drives only the process the client launched; it is not an
  attach protocol for another process.
- The Python SDK, managed Interactions agent, and legacy `gemini` CLI are
  separate surfaces and are never substituted.
- Offline fixture tests cover argument construction, envelope decoding
  (success/error/missing/conversation-less), stream frame shape and
  pass-through, and the unsupported paths. Live behavior is untested.
