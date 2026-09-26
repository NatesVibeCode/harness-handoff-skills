# Conformance

**Sources:** `harness-sdk-briefs/cursor.md` (research dated 2026-09-25) plus
the official CLI reference pages below, read 2026-09-25. No installed CLI
was consulted: CLI execution was suspended at the operator's request, so
flags, shapes, and behaviors below are brief- and docs-derived only.

- Parameters: `https://cursor.com/docs/cli/reference/parameters`
- Output format: `https://cursor.com/docs/cli/reference/output-format`
- Headless: `https://cursor.com/docs/cli/headless`
- TypeScript SDK: `https://cursor.com/docs/sdk/typescript`
- Python SDK: `https://cursor.com/docs/sdk/python`

## Surfaces

| Method | Invokes | Basis |
| --- | --- | --- |
| `Start` | `cursor-agent --workspace <abs> --sandbox enabled --print --output-format json [--model <m>] <prompt>`; parses the single `result` object (`session_id`, `result`, `is_error`) | Brief pinned form + output-format page |
| `Resume` | Same with `--resume <chat-id>` | Brief resume form + parameters page (`--resume [chatId]`) |
| `Stream` | Same with `--output-format stream-json` (+ `--stream-partial-output` when enabled); NDJSON pass-through | Brief streaming section + output-format page |
| `List` | `cursor-agent --workspace <abs> ls`; bytes verbatim, no parsed contract | Parameters page (`ls` command); shape unverified |
| `Fork` | Unsupported | No fork flag or command in the brief or parameters page |
| `Inspect` | Unsupported | No transcript export or passive read documented; local stores are undocumented SQLite/editor state |

## Notes

- Binary naming: docs invoke `agent`; the brief resolves `cursor-agent`
  as the same first-party family. The default is `cursor-agent`,
  overridable via `Client.Binary`.
- `--continue` (= latest session) is never used; resume always takes an
  explicit ID.
- ID namespaces are not interchangeable: CLI chat IDs, SDK `agent-…`, and
  cloud `bc-…` IDs cannot be substituted for one another.
- Model values are caller-provided; the docs direct callers to
  `--list-models` instead of hard-coding IDs.
- Offline fixture tests cover argument construction, argv-last prompt
  delivery, JSON decoding, stream/list pass-through, and the unsupported
  paths. Live behavior is untested.
