Use this skill only when the operator explicitly selects DeepSeek Harness (DSH) or asks to hand work to it. DSH is a local agent harness driven through profiles; its automation surface is **Agent Client Protocol (ACP) v1 over stdio**, not a vendor SDK. Do not assume an ACP client library, a `dsh --once` flag, or a hosted endpoint exists.

Contract source: https://github.com/deepseek-ai/deepseek-harness

## Capability probing

Probe before driving. A DSH app profile prints its own help and exits without taking over stdio:

```sh
command -v dsh
dsh --version
dsh --help
dsh --profile acp --help
dsh --profile headless --help
```

Profiles are selected by name and resolved from the operator's DSH state. Profile names seen locally include `acp`, `headless`, `sdk`, `sdk-minimal`, `web`, `tui`, `open-design`. Do not invent a profile name; if the requested one is absent, report the names that are actually installed.

## ACP protocol route

The `acp` profile serves the automation-only ACP surface: newline-delimited JSON-RPC 2.0 over stdio, with **stdout reserved for protocol frames**. Diagnostics belong on stderr. An agent that writes non-protocol bytes to stdout corrupts the transport for every consumer.

Method matrix on the checked surface:

| Method | Role |
| --- | --- |
| `initialize` | handshake; returns agent capabilities and `sessionCapabilities` |
| `session/new` | create a session in a workspace; returns the session id |
| `session/prompt` | deliver one turn; returns a result with `stopReason` |
| `session/list` | enumerate persisted, resumable root sessions (newest first) |
| `session/resume` | reopen an existing session by exact id |
| `session/close` | close a session |
| `session/update` | notification: streamed assistant text, usage, and tool state |

`initialize` advertises `sessionCapabilities` of `{"close": {}, "list": {}, "resume": {}}` on the checked version. Treat a missing capability as unavailable rather than assuming it.

Fresh conversation:

```text
initialize -> session/new -> session/prompt -> session/close
```

Continuation of an exact session:

```text
initialize -> session/resume -> session/prompt -> session/close
```

Retain the returned session id and resume only with that exact id. Assert `stopReason` is `end_turn`; any other value is a failed turn, not a partial success.

Two behaviours matter for correctness:

- **Resume does not replay history.** A resumed session restores its persisted log without re-emitting earlier `session/update` messages. Do not expect, request, or synthesize replay; do not infer "nothing happened" from an empty replay.
- **Resume is workspace-scoped.** The session's workspace must match the requested one, or the server refuses the resume. Never point a resume at a different directory to make it succeed, and never select "the newest session" as an exact-id substitute.

Persisted sessions live under the DSH state root, keyed per workspace. `session/list` spans every workspace in that root; use it to locate a session id, never as evidence that the id may be continued. For the printed Node, continuation is decided by the process-owned workspace ledger, not by this listing and not by the caller.

## Model route pinning

The inference route comes from the profile's agent-model configuration, not from prompt text. The printed DSH Process takes `route_provider`, `route_model`, `route_overlay_path`, and `route_overlay_digest` as separate typed inputs. This lets a caller change the route without rebuilding the Process while keeping the exact patch bytes pinned.

```sh
dsh --profile acp --patch /path/to/route-overlay.json
```

The overlay is a JSON patch list (JSON is valid YAML) with exactly one `acp` row and only its provider and model fields:

```json
[{"id":"acp","config":{"provider":"sail","model":"deepseek-ai/DeepSeek-V4.1-Flash-1017"}}]
```

Supply the sha256 of those exact bytes. The runner rejects a digest mismatch, another target row, extra configuration keys, or provider/model values that differ from the typed inputs. It snapshots the validated bytes and passes that snapshot with `--patch`. After `session/new` or `session/resume`, it reads the returned `configOptions` model `currentValue`, verifies the actual provider/model, and preserves requested, configured, observed, and overlay identity separately in the result. A mismatch fails before `session/prompt`; no profile default or alternate provider is accepted as a fallback.

Rules for the route:

- Treat the overlay as a content-pinned artifact. Record its digest with the result and require the same digest when resuming that session.
- Never inject provider or model through an environment variable, a rewritten settings file, or a patched profile in place of the overlay.
- Never silently fall back to a different provider when the requested route is unavailable. Report the route that actually ran.
- Credentials are resolved by DSH from its own settings, which name the environment variable holding the key. Do not pass key material in argv, prompt text, or an overlay.

## CLI route

`headless` is a one-shot route: it answers one task, streams reasoning to stderr, prints the final message to stdout, and exits.

```sh
dsh --profile headless "Perform the scoped task."
```

Launcher help also documents `dsh --profile tui --resume <session>` and the same flag for other app profiles; that is an interactive continuation route and was not exercised here. A `headless` run is not a continuation route — do not present it as one, and do not claim a durable session from an exited one-shot process.

## Independent local launches

When the operator requests a **new independent local task**, create one fresh ACP session in the selected workspace and keep its session id with the lane. Do not route lanes through a shared broker, a single ACP connection multiplexed across tasks, or a parent agent. Existing-session continuation is allowed only for an exact session id recorded in the selected workspace's process-owned ledger; a caller naming a session does not authorize continuation.

## Handoff workflow

When the user redirects this task here, stop advancing the superseded attempt and deliver the handoff; do not finish your own approach first. Preserve the goal, state, constraints, and requested outputs without prescribing the sender's tool recipe unless the user chose that method.

1. Resolve the installed launcher and the requested profile; read that profile's own help before sending frames.
2. Decide the operation explicitly: a fresh session, or continuation of an exact session id recorded in the selected workspace's process-owned ledger.
3. Supply the workspace and route deliberately: the selected directory, separate provider/model values, an overlay path, and its expected sha256 digest.
4. Drive the ACP sequence, retaining the exact session id, requested/configured/observed route values, and overlay digest. Observation comes from that session's returned ACP config options.
5. Verify the result: `end_turn`, the assistant text actually produced, and any requested artifact on disk. Transport success and process exit do not establish that the work succeeded.
6. Report the exact session id and operation. If the effective route differs from the requested one, say so instead of reporting success.

Progress advisories. While running, a lane may report milestones against the packet's expected result as advisory messages carrying an optional status: `started`, `milestone`, `blocked`, or `done`. Status is self-reported presence, never proof of completion — the activating agent reads it to understand progress without parsing prose, and verifies the result itself. This shared advisory vocabulary carries no control state and never blocks the lane. A spawner that wants these reports subscribes to the lane; `blocked` and `done` reports fan out to subscribers, and anyone may subscribe.

## DSH-specific boundaries

- Do not invent a DSH profile, flag, profile row id, session id, provider, or model.
- Do not treat the ACP surface as a vendor SDK, and do not import a third-party ACP client in place of the documented frames.
- Do not write diagnostics to stdout on the ACP route.
- Do not claim transcript replay, forking, or session-listing-as-exact-selection; the checked surface offers resume, not replay.
- Do not substitute another harness when DSH is unavailable.
