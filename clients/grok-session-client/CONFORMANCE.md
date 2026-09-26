# Conformance

**Checked:** 2026-09-25  
**Installed CLI:** `grok 1.0.41 (4220f3b224a6) [stable]`  
**Implementation route:** documented Grok Build CLI subprocess surface; no xAI
model API client is included.

## Capability status

| Capability | Implemented surface | Verification status |
| --- | --- | --- |
| Fresh session | `grok --output-format json --prompt-file <file>` | Verified live 2026-09-25: `Start` returned session `01a0dae3-38c7-…` for a trivial prompt in a disposable cwd. Offline wrapper tests cover argument construction and JSON decoding. |
| Explicit-ID resume | `grok --output-format json --resume <session-id> --prompt-file <file>` | Verified live 2026-09-25: `Resume` on the fresh ID returned the same ID (in-place continue). |
| Deliberate fork | `grok --output-format json --resume <session-id> --fork-session --prompt-file <file>` | Verified live 2026-09-25: `Fork` returned a distinct ID `01a0dae3-5327-…`; source session unchanged. |
| Streaming output | `grok --output-format streaming-json --prompt-file <file>` | Verified live 2026-09-25: fresh stream delivered 6595 bytes of NDJSON before exit. |
| Session list | `grok sessions list [--limit N]` | Verified live 2026-09-25: new and forked sessions appeared in the workspace listing (2386 bytes). |
| Session inspect | `grok export <session-id>` | Verified live 2026-09-25: fork transcript returned as Markdown (156 bytes). |

The offline tests use a local fake executable and synthetic output fixtures.
They verify argument construction, prompt-file handling, session ID extraction,
and output pass-through. They do **not** establish successful provider behavior
or exact response formatting from a live session.

## Installed surface checks

These read-only commands were run against the installed binary:

```text
grok --version
grok --help
grok agent --help
grok agent stdio --help
grok sessions --help
grok sessions list --help
grok sessions search --help
grok export --help
grok usage --help
```

The installed help exposes `--resume`, `--fork-session`, `--prompt-file`,
`--output-format` (`plain`, `json`, `streaming-json`), `sessions list` with
`--limit`, and `export <session-id>`. The package uses `--resume`, never
`--session-id`, for continuation.

## Public sources checked

- [Grok Build overview](https://docs.x.ai/build/overview)
- [Headless & Scripting](https://docs.x.ai/build/cli/headless-scripting)
- [CLI Reference](https://docs.x.ai/build/cli/reference)
- [Sessions](https://docs.x.ai/build/features/sessions)
- [Enterprise Deployments](https://docs.x.ai/build/enterprise)

The official docs were reviewed on 2026-09-25. They document headless JSON and
streaming JSON, extract `sessionId` from JSON output, describe exact-ID resume
and `--fork-session`, and list/export session history.

## Discrepancies and limits

- The official headless guide currently documents `--no-auto-update`, but
  `grok 1.0.41 --help` did not list it. The client does not send that
  unadvertised flag. The same guide documents `[cli] auto_update = false` in
  `~/.grok/config.toml`; users can apply that setting before using the client.
- The official headless guide's option table describes `--session-id` as
  creating or resuming a named session. The sessions guide and installed help
  say it names a **new** session and does not resume one. The client follows
  installed help and uses `--resume <id>` for continuation.
- Installed help includes `streaming-messages-json` and
  `--include-partial-messages`; these are outside this package's requested
  surface and are not used.
- ACP (`grok agent stdio`) is documented for `initialize`, authentication,
  `session/new`, `session/prompt`, and streamed `session/update` messages. This
  package uses the CLI route because the installed/documented CLI surface also
  provides the requested explicit resume, fork, list, and transcript export
  operations. It does not claim ACP resume, fork, or list support.
- Live session calls use provider credits and invoke workspace tools under the
  user's configured Grok permissions. The 2026-09-25 live run below used
  trivial "Reply with exactly: …" prompts in a disposable cwd; all three
  probe sessions were deleted afterward.

## Live re-verification (executed 2026-09-25)

A small integration program exercised each method once against the installed
CLI in a disposable workspace:

1. `Start` with a harmless prompt; returned exact `SessionID`
   `01a0dae3-38c7-77b0-9251-63feaa8d6fa1`.
2. `Resume` with that ID and a second harmless prompt; same ID returned.
3. `Fork` the same ID with a harmless branch prompt; new ID
   `01a0dae3-5327-7dd1-975b-8862995ea40e` returned.
4. `Stream` (fresh) delivered 6595 bytes of NDJSON before exit.
5. `List` in the same workspace showed the new, forked, and streamed
   sessions (2386 bytes).
6. `Inspect` of the fork ID returned its Markdown transcript (156 bytes).

Repeat with the same steps after choosing an authenticated Grok account and
a disposable workspace; disable background updates via `[cli]
auto_update = false` in `~/.grok/config.toml` if required.

The client does not enable auto-approval, change Grok permissions, delete
sessions, or modify workspace files itself.

## ACP route (live-verified 2026-09-25)

Transport: `grok agent stdio` (JSON-RPC 2.0 over stdin/stdout,
newline-delimited), run from an empty disposable cwd with installed CLI
`grok 1.0.41` and `grok login` cached-token auth. No credential values were
read; authentication used the CLI's own cached session via method
`cached_token`.

Sequence verified end-to-end with one minimal prompt ("Say hello in one
short sentence." → "Hello.", `stopReason: end_turn`):

1. `initialize` with `{protocolVersion: 1, clientCapabilities:
   {fs: {readTextFile, writeTextFile}, terminal: true}}` returns
   `protocolVersion`, `agentCapabilities` (`loadSession`,
   `promptCapabilities`, `mcpCapabilities`, session `list`/`resume`/`close`,
   `auth`), `authMethods[]`, and `_meta` (`agentVersion 1.0.41`,
   `modelState` for `grok-4.7`, vendor extensions).
2. `authenticate` with `{methodId, _meta: {headless: true}}` returns ok
   (`auth_mode: Oidc` for the login session).
3. `session/new` with `{cwd, mcpServers: []}` returns `{sessionId}`.
4. `session/prompt` with `{sessionId, prompt: [{type: "text", text}]}` returns
   completion metadata (`stopReason`, token usage); assistant text arrives as
   `session/update` notifications with
   `params.update.sessionUpdate == "agent_message_chunk"` and
   `update.content.text`.

Observed `session/update` types for the hello prompt:
`available_commands_update`, `agent_thought_chunk`, `agent_message_chunk`.

Cost of the hello call: 1 model call, 19517 input / 29 output tokens,
~2 s API time.

Drift: the official docs example prefers an `xai.api_key` auth method when
`XAI_API_KEY` is set, but installed 1.0.41 advertises only `cached_token`
and `grok.com` in `init.authMethods`. Clients must select from the
advertised methods dynamically and must not hardcode the docs' list.

Cleanup: the probe session was deleted with `grok sessions delete` and
confirmed absent from `grok sessions list`. The probe script is throwaway
tooling kept outside this repo.

Scope note: this package uses the CLI-subprocess route, not ACP. ACP is
recorded here as the verified documented alternative; an ACP client would
be a separate package.
