# Conformance

**Checked:** 2026-09-25  
**Installed CLI:** `codex-cli 0.157.0`  
**Implementation route:** documented `codex exec` subprocess surface
(`exec -C … --json`, `exec resume`, `exec fork`, stdin prompt via `-`)
plus the documented local session store (`$CODEX_HOME/sessions`) for
list/inspect. No Codex SDK or app-server client is included.

## Capability status

| Capability | Implemented surface | Verification status |
| --- | --- | --- |
| Fresh session | `codex exec -C <dir> --json --skip-git-repo-check -` with prompt on stdin | Argument construction, stdin delivery, and JSONL decoding are covered by offline wrapper tests. Flags, event shapes, and a live fresh run were verified against the installed CLI before package-level live checks were deferred (see below). |
| Explicit-ID resume | `codex exec resume <id> --json --skip-git-repo-check -` with prompt on stdin | Argument construction is covered offline; a live explicit-ID resume was verified against the installed CLI (same thread ID returned). |
| Deliberate fork | `codex exec fork <id> --json --skip-git-repo-check -` with prompt on stdin | Argument construction is covered offline; flags confirmed in installed help. No live fork was run. |
| Streaming output | Same `exec --json` argv with raw JSONL pass-through | Raw byte pass-through is covered offline. No live stream was run through the package. |
| Session list | Walk `$CODEX_HOME/sessions` (or `~/.codex/sessions`) `*.jsonl`, parse leading `session_meta` | Store walking, metadata parsing, and workspace filtering are covered offline against a temp store. Layout and metadata shape were verified against real stored files. |
| Session inspect | Return the stored JSONL file matching the session ID | File matching and pass-through are covered offline. Transcript layout was verified against real stored files. |

The offline tests use a local fake executable and synthetic fixtures plus
a temp session store. They verify argument construction, stdin prompt
delivery, thread ID extraction, output pass-through, store walking, and ID
validation.

## Installed surface checks

These read-only commands were run against the installed binary:

```text
codex --version
codex --help
codex exec --help
codex exec resume --help
codex exec fork --help
codex agents --help
codex login status
```

The installed help exposes `exec -C/--json/-o/--skip-git-repo-check`,
`exec resume <id>`, `exec fork <id>`, and `-` stdin prompt delivery on all
three. `codex login status` reported ChatGPT login.

Live shape probes (trivial prompts, disposable cwd, before live checks
were deferred):

```text
echo "Reply with exactly: ok" | codex exec -C <ws> --json --skip-git-repo-check -
echo "Reply with exactly: ok-resume" | codex exec resume <id> --json --skip-git-repo-check -
```

Observed: `--json` emits JSONL with `thread.started` (carrying
`thread_id`), `turn.started`, `item.completed` (agent_message text), and
`turn.completed` with usage; resume continues in place (same thread ID
returned); each run persists a JSONL file under the session store whose
first line is `session_meta` with `session_id` and `cwd`.

## Public sources checked

- [Codex SDK](https://developers.openai.com/codex/sdk)
- [App-server protocol](https://developers.openai.com/codex/app-server)
- [Non-interactive mode](https://developers.openai.com/codex/non-interactive-mode)
- [Codex auth](https://developers.openai.com/codex/auth)
- [Codex open source](https://developers.openai.com/codex/open-source)
- [openai/codex repo](https://github.com/openai/codex)

The official docs were reviewed on 2026-09-25. They document `codex exec`
for scripts and CI with `--json` JSONL events, `resume`/`fork` by session
ID, the SDK-vs-CLI-vs-app-server boundary, and thread persistence under
the local session store.

## Discrepancies and limits

- `codex agents` is an interactive TUI browser with no machine-readable
  output flag on the installed version, so `List` reads the session store
  instead of shelling out. The walk assumes no sub-layout: it matches any
  `*.jsonl` file whose leading `session_meta` line carries the workspace.
- `exec resume` and `exec fork` accept no `-C` flag on the installed
  version; the client runs them with the process cwd set to the workspace.
- Documented failure events (`turn.failed`, `error`) are converted to
  errors carrying the raw event; their exact field shapes were not observed
  live and are not parsed beyond the event type.
- Store scans are capped at 5000 files and the metadata line read at 1
  MiB; larger stores may list incompletely.
- Package-level live calls (one program exercising all six methods) were
  deferred at the operator's request on 2026-09-25: all further CLI
  execution was suspended. The recon probes above predate the suspension.
  See the live re-verification steps below.

## Live re-verification (pending)

After the operator re-allows CLI execution, choose authenticated Codex
credentials and a disposable workspace, then run a small integration
program using each method:

1. `Start` with a harmless prompt; record the returned exact thread ID
   and final text.
2. `Resume` with that ID and a second harmless prompt; confirm the same ID
   is returned.
3. `Fork` the same ID with a harmless branch prompt; verify a new ID is
   returned and the source history is unchanged.
4. `Stream` a prompt and confirm JSONL bytes arrive before the command
   exits.
5. `List` in the same workspace and confirm the new and forked sessions
   appear.
6. `Inspect` the fork ID and confirm stored JSONL output is returned.

The client does not change sandbox, approval, or model settings, delete
sessions, or modify workspace files itself. Recon probe sessions from
2026-09-25 remain in the local store; remove them with `codex delete <id>`
once CLI execution is re-allowed.
