# Capability matrix: skills vs clients

Two surfaces, different jobs. **Skills** (`<harness>-harness-handoff/`)
own discovery, continuation policy, the handoff packet workflow, and every
transport. **Clients** (`clients/<harness>-session-client/`) own Go
execution mechanics for the CLI route. When driving sessions from code,
prefer the client; the skill recipes remain authoritative for interactive
use, discovery, and surfaces the client does not cover.

Legend: **client** = Go client method · **skill** = skill recipe/workflow ·
**—** = no documented surface (client returns `ErrUnsupported`).

## Harnesses with clients

| Capability | grok | claude | codex | cursor | muse | opencode | antigravity |
|---|---|---|---|---|---|---|---|
| Start (fresh) | client | client | client | client | client | client | client |
| Resume (exact ID) | client | client | client | client | — | client | client |
| Fork | client | client | client | — | — | client | — |
| Stream | client | client | client | client | client | client | client |
| List | client | client | client | client (raw) | — | client | — |
| Inspect | client | client | client | — | client | client | — |
| Discovery/history policy | skill | skill | skill | skill | skill | skill | skill |
| Approval/sandbox selection | skill | skill | skill | skill | skill | skill | skill |
| Non-CLI transports | skill (ACP) | skill (SDK) | skill (SDK/app-server) | skill (SDK/Bridge/REST) | skill (MSP) | skill (SDK/HTTP) | skill (SDK/Interactions) |

Notes:

- Cursor `List` returns raw `ls` bytes; no machine-readable contract is
  documented. Muse and OpenCode run results carry raw event bytes because
  envelope field names are outside the consulted docs.
- Muse `Inspect` uses `muse export --redacted`; OpenCode `Inspect`
  deliberately omits `--sanitize` and returns bytes verbatim.
- Codex and Claude `List`/`Inspect` read documented local stores because
  their CLIs expose no scriptable list for headless sessions.
- Continuation policy differs by harness, not by table cell. Codex
  `Resume`/`Fork`/`Stream`-with-session work over the documented session
  store, but the codex handoff skill forbids them: handoff lanes use
  `Start` only (`continuation: forbidden`). Muse continuation has no
  documented headless mechanism at all, so the client itself refuses
  `Resume`/`Fork`/sessioned-`Stream` with `ErrUnsupported` — hence the
  `—` above. `client` means the method exists and can execute, not that
  the skill allows it.

## Harnesses without clients (skill-only)

amp, cline, copilot, droid, gemini, junie, openhands. Their skills keep
full CLI recipes until clients exist. Adding one: copy the nearest
`clients/*-session-client`, follow its README/CONFORMANCE shape, add the
`## Programmatic execution` section to `skills-src/harnesses/<h>.md`,
regenerate, and extend this matrix.

## Versioning

Each client is an independent Go module,
`github.com/NatesVibeCode/harness-handoff-skills/clients/<name>`,
tagged separately (`clients/<name>/vX.Y.Z`) because harnesses drift
independently. Skills pin nothing; `CONFORMANCE.md` in each client records
the CLI version it was checked against.
