# Conformance

**Checked:** 2026-09-25  
**Installed CLI:** `claude 2.1.270 (Claude Code)`  
**Implementation route:** documented Claude Code CLI subprocess surface
(`-p`, stdin prompt, `--output-format json` / `stream-json`, `--resume`,
`--fork-session`) plus the documented local transcript store for
list/inspect. No Agent SDK or Messages API client is included.

## Capability status

| Capability | Implemented surface | Verification status |
| --- | --- | --- |
| Fresh session | `claude -p --output-format json` with prompt on stdin | Verified live 2026-09-25: `Start` returned session `2d5ce505-…` with text `ok` for a trivial prompt in a disposable cwd. Offline wrapper tests cover argument construction, stdin delivery, and JSON-array decoding. |
| Explicit-ID resume | `claude -p --output-format json --resume <session-id>` with prompt on stdin | Verified live 2026-09-25: `Resume` on the fresh ID returned the same ID (in-place continue) with text `ok2`. |
| Deliberate fork | `claude -p --output-format json --resume <session-id> --fork-session` with prompt on stdin | Verified live 2026-09-25: `Fork` returned a distinct ID `160f4644-…` with text `ok3`; source history unchanged. |
| Streaming output | `claude -p --output-format stream-json` with prompt on stdin | Verified live 2026-09-25: fresh stream delivered 19821 bytes before exit. |
| Session list | Read `$CLAUDE_CONFIG_DIR/projects/<encoded-cwd>/` (or `~/.claude/projects/<encoded-cwd>/`) `*.jsonl` | Verified live 2026-09-25: new, forked, and streamed sessions all appeared (3 entries with IDs, sizes, mtimes). |
| Session inspect | Read `<session-id>.jsonl` from the workspace project dir | Verified live 2026-09-25: fork transcript returned verbatim (146850 bytes of JSONL). |

The offline tests use a local fake executable and synthetic output fixtures
plus a temp transcript store. They verify argument construction, stdin
prompt delivery, session ID extraction, output pass-through, store
encoding, and ID validation. They do **not** establish successful provider
behavior or exact response formatting from a live session.

## Installed surface checks

These read-only commands were run against the installed binary:

```text
claude --version
claude --help
claude agents --help
claude logs --help
```

The installed help exposes `-p/--print`, `--output-format` (`text`,
`json`, `stream-json`), `--input-format`, `--resume`, `--continue`,
`--fork-session`, `--session-id`, `agents --json`, and `logs <id>`. The
package uses `--resume`, never `--session-id`, for continuation.

Live shape probes (trivial prompts, disposable cwd, authenticated CLI):

```text
claude -p "Reply with exactly: ok" --output-format json
echo "Reply with exactly: ok-stdin" | claude -p --output-format json
claude -p "Reply with exactly: ok-resume" --output-format json --resume <id>
```

Observed: `--output-format json` emits a JSON array whose `result`
message carries `session_id` and the result text; stdin prompt delivery
works with no positional prompt argument; `--resume <id>` continues
in place (same ID returned).

## Public sources checked

- [Agent SDK overview](https://code.claude.com/docs/en/agent-sdk/overview)
- [Work with sessions](https://code.claude.com/docs/en/agent-sdk/sessions)
- [Streaming input vs single-message](https://code.claude.com/docs/en/agent-sdk/streaming-vs-single-mode)
- [TypeScript reference](https://code.claude.com/docs/en/agent-sdk/typescript)
- [Python reference](https://code.claude.com/docs/en/agent-sdk/python)
- [CLI sessions / transcript location](https://code.claude.com/docs/en/sessions)

The official docs were reviewed on 2026-09-25. They document headless `-p`
JSON output with `session_id` capture, exact-ID resume and fork, streaming
output, the local transcript store location and cwd encoding, and the
CLI-vs-SDK boundary (other languages drive the agent loop via CLI
subprocess).

## Discrepancies and limits

- `claude agents --json --all` lists background agents only; headless `-p`
  sessions do not appear there (verified: two `-p` sessions absent from the
  listing while their transcripts existed on disk). `List` therefore reads
  the transcript store instead of shelling out, and `logs <id>` (background
  terminal output) is not used.
- The store encoding replaces non-alphanumerics with `-` (verified:
  `/private/tmp/claude-probe-ws` → `-private-tmp-claude-probe-ws`). The
  documented truncation+hash rule for overlong names is not replicated;
  unusually long workspace paths may resolve to the wrong directory.
- `--session-id <uuid>` names the session for the conversation; it is not
  a resume mechanism and the client does not use it.
- `--continue` resumes the most recent session in the directory; the client
  never uses it because it can select a session the operator did not choose.
- Live package-level calls use provider credits and invoke workspace tools
  under the user's configured Claude permissions. The 2026-09-25 live run
  below used trivial "Reply with exactly: …" prompts in a disposable cwd
  (model routed via the operator's configured provider); all probe
  transcripts were deleted afterward.

## Live re-verification (executed 2026-09-25)

A small integration program exercised each method once against the installed
CLI in a disposable workspace:

1. `Start` with a harmless prompt; returned exact `SessionID`
   `2d5ce505-aa39-415e-9ac8-02847ffd32e9` with text `ok`.
2. `Resume` with that ID and a second harmless prompt; same ID returned
   with text `ok2`.
3. `Fork` the same ID with a harmless branch prompt; new ID
   `160f4644-1de4-4ecc-8fa6-132af6e89fa5` returned with text `ok3`.
4. `Stream` (fresh) delivered 19821 bytes before exit.
5. `List` in the same workspace showed the new, forked, and streamed
   sessions (3 entries).
6. `Inspect` of the fork ID returned its JSONL transcript (146850 bytes).

Repeat with the same steps after choosing authenticated Claude credentials
and a disposable workspace.

The client does not change permission modes, delete sessions, or modify
workspace files itself. There is no documented CLI session-delete command;
remove disposable-workspace transcripts by deleting that workspace's
project directory under the store.
