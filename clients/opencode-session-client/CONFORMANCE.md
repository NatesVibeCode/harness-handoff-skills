# Conformance

**Sources:** `harness-sdk-briefs/opencode.md` (research dated 2026-09-25)
plus the official CLI reference, read 2026-09-25. No installed CLI was
consulted: CLI execution was suspended at the operator's request, so flags
and behaviors below are brief- and docs-derived only.

- CLI: `https://opencode.ai/docs/cli/`
- SDK: `https://opencode.ai/docs/sdk/`
- Server: `https://opencode.ai/docs/server/`

## Surfaces

| Method | Invokes | Basis |
| --- | --- | --- |
| `Start` | `opencode run --dir <abs> --format json [--model <p/m>] <prompt>`; event bytes verbatim | Brief §3/§5 + CLI `run` reference (`[message..]`, `--dir`, `--format`, `--model`) |
| `Resume` | Same with `--session <id>` | Brief + CLI reference (`--session/-s`: session ID to continue) |
| `Fork` | Same with `--session <id> --fork` | Brief + CLI reference (`--fork`: fork when continuing) |
| `Stream` | Same argv as fresh/resumed/forked; bytes pass-through | CLI reference (`--format json`: raw JSON events) |
| `List` | `opencode session list --format json [--max-count N]`; bytes verbatim | Brief + CLI reference (`session list`, `--max-count`, `--format`) |
| `Inspect` | `opencode export <id>`; bytes verbatim, no `--sanitize` | Brief + CLI reference (`export [sessionID]`) |

## Notes

- Event envelopes are not parsed: the consulted docs confirm raw JSON
  events but not envelope field names, so `Result` carries raw bytes and
  callers extract IDs per the server/SDK reference.
- `--continue` (= latest session) and `--share` (= publish) are never
  used; resume always takes an explicit ID.
- `--file/-f` attaches files to the message; it is not a prompt file and
  is not used.
- The client never attaches to a remote server (`--attach`) and never
  passes server credentials.
- V1 vs V2 naming collides on `@opencode-ai/sdk`; the CLI route used here
  is version-independent of that split.
- Offline fixture tests cover argument construction, argv-last prompt
  delivery, list/inspect pass-through, and invalid-argument paths. Live
  behavior is untested.
