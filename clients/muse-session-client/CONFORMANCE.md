# Conformance

**Sources:** `harness-sdk-briefs/muse.md` (research dated 2026-09-25,
cross-checked against Muse Code 1.0.3 on 2026-09-04) plus the official
headless docs page, read 2026-09-25. No installed CLI was consulted: CLI
execution was suspended at the operator's request, so flags and behaviors
below are brief- and docs-derived only.

- Headless/CI: `https://dev.meta.ai/docs/muse-code/extending`
- Auth: `https://dev.meta.ai/docs/muse-code/auth`
- Interactive: `https://ai.developer.meta.com/docs/muse-code/interactive`
- SDK repo: `https://github.com/meta-models/muse-code-sdk`

## Surfaces

| Method | Invokes | Basis |
| --- | --- | --- |
| `Start` | `muse exec --json --workspace <abs> --worktree off --prompt-file <0600tmp>`; JSONL bytes verbatim | Brief pinned argv + extending page (`exec --json`, JSONL on stdout, exit codes) |
| `Resume` | Unsupported (`ErrUnsupported`, no CLI invocation) | Checked CLI: `exec --session-id` selects an identity for a new run and does not resume history; `muse resume` is interactive-only, so no headless resume-with-prompt is documented |
| `Stream` | Fresh argv only; JSONL pass-through; non-empty session ID refused like `Resume` | Same pages |
| `Inspect` | `muse export --session <id> --out <tmp> --redacted`; file bytes verbatim, tempfile removed | Brief export form + extending page |
| `Fork` | Unsupported | Fork exists on MSP (`session/fork`) and interactive `/fork` only |
| `List` | Unsupported | Listing exists on MSP (`session/list`) only; the on-disk index is explicitly not an official API |

## Notes

- Event envelopes are not parsed: the consulted docs confirm JSONL output
  but not envelope field names, so `Result` carries raw bytes and callers
  extract IDs per the MSP wire reference.
- Resume refusal (from the checked CLI): the earlier brief-derived claim
  that `exec --session-id` is the headless continuation route was wrong —
  the guide verified against the installed CLI states it does not resume
  history, and `muse resume` takes no headless prompt. The client refuses
  resume-with-prompt instead of mislabeling a new run as a continuation.
- Offline fixture tests cover argument construction, prompt-file delivery,
  export-file round-trip and cleanup, stream pass-through, and the
  unsupported paths. Live behavior is untested.
- Exit codes (from the docs): 0 complete, 1 failed/cancelled, 2 usage;
  exit 0 does not mean the work is correct.
