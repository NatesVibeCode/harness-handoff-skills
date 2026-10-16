# Fresh SDK Nodes, Blocks, and Processes

This directory contains **eleven authored development plans**. Each plan composes
one SDK Node into a reusable Block and one-operation Process. All operations start
a fresh session. The current plans are **unprinted and unadmitted**: the supported
Forge front door rejects the experimental SDK mechanism declarations. Three
selected CLI contracts also use unsupported parser names. Historical experimental prints are not qualification of these sources.

## One declaration

[`mcp_bridge/sdk_bindings.json`](../../../mcp_bridge/sdk_bindings.json) declares
exact SDK versions, public archive URLs and SHA-256 hashes, licenses, declared
dependencies, runtime minimums, supported fresh operations, and closed settings
schemas. Nonempty settings strings are an explicit binding rule enforced by the
runners; the emitted field types use Forge’s supported schema vocabulary. Both authoring generators and printed runners consume it. The generated
`*-sdk-pins.json` files are projections of that declaration.

The Node, Block and Process each expose `prompt`, `workspace` and typed `settings`.
The calling Process supplies settings explicitly. Missing fields, undeclared
options, wrong types, resume/history requests and old flat model/approval inputs
are refused before SDK import. Configuring permissions does not authorize a run.

| Harness | Distribution | Version | Explicit settings |
| --- | --- | --- | --- |
| Claude Code | `claude-agent-sdk` | 0.2.166 | model, permission mode, allowed/disallowed tools |
| Cursor | `cursor-sdk` | 1.0.37 | model, auto review, sandbox enabled |
| Copilot | `github-copilot-sdk` | 1.0.18 | model, permission-request handling; workspace is bound |
| Muse | `muse-code-sdk` | 1.4.7 | provider, model, approval mode, offered permission-profile ID |
| Antigravity | `google-antigravity` | 0.1.22 | model, native/unattended policy, recovery directories |
| OpenHands | `openhands-sdk` | 1.54.0 | model and tools; this implementation supports an empty tool list |
| Amp | `@ampcode/sdk` | 0.1.0-20260918210405-g81edbf0 | mode, visibility, allow-all flag, tool permission rules |
| Cline | `@cline/sdk` | 0.0.93 | provider/model, tool policies, unmatched approval handling, tool/spawn/team switches |
| Codex | `@openai/codex-sdk` | 0.162.1 | model, sandbox mode, approval policy, network access, web search mode |
| Droid | `@factory/droid-sdk` | 0.9.1 | model, native autonomy/interaction mode, permission-request handling |
| OpenCode | `@opencode-ai/sdk` | 1.19.0 | provider/model and permission rules; both session requests bind the workspace |

Muse also pins `muse-code-msp` 1.4.7 as supplemental material because the SDK
imports it without declaring it in its published dependency metadata. The runner
checks that supplemental version before importing the SDK.

These schemas describe the implemented subset of each SDK. Other vendor options
require extending the declaration and implementation together. No model name or
permission-profile name is selected by an adapter. Muse verifies that its selected
profile was applied. Codex uses the caller's thread options, with no hardcoded
`audit`, `:read-only` or other named profile.

## Completion and integrity

A successful receipt requires a fresh session identity and completed assistant
output. Copilot waits for the root session to become idle; Claude, Cursor, Cline,
Droid, Muse and OpenHands require their SDK's successful completion signal.
Incomplete streams, cancellation, failed terminal results, empty output and send
acknowledgments cannot become successful receipts. OpenCode checks assistant
errors. Owned sessions/servers are closed on the supported cleanup paths.

Runners verify their own source, adapter, validator and declaration digests before
SDK import, then check the installed distribution version and declared entrypoint.
SDK stdout is routed to diagnostics; stdout carries the final JSON receipt.
Receipts preserve assistant output and bind the selected settings with a digest. No runner installs packages,
selects a CLI fallback, or resubmits a failed/uncertain invocation.

A minimum runtime version and a package version are **not a sealed runtime**.
The archive pins currently describe the published top-level SDK artifacts (the
captured binary Python wheels target macOS arm64). Transitive dependencies,
interpreter/executable bytes, licenses throughout the closure, SDK-managed worker
binaries and target-specific material still need qualification. Credentials stay
in the selected runtime's environment; they never enter the public declaration.
An interrupted invocation can have remote effects: the owning Process must retain
its original identity and diagnostics and reconcile before deciding recovery.

## Local checks and factory diagnostics

From the repository root:

```sh
python3 praxis/handoff/sdk/authoring/build_sdk_plans.py
python3 praxis/handoff/sdk/authoring/build_ts_sdk_plans.py
python3 scripts/build_skills.py --check
python3 -m pytest
python3 scripts/check_sdk_plans.py --out /path/to/new-diagnostics
python3 scripts/fetch_sdk_material.py --out /path/to/sdk-archives
```

The last command retrieves and checks public SDK archives without installing or
executing them. The check command captures all eleven native factory results,
including refusals. Each plan uses its own `stores-<capability>.json`, so an
unrelated harness contract cannot prevent checking that capability. These commands never admit, sign or invoke a Node. Local
fixtures prove mapping and refusal mechanics; they are not real-use evidence.

## Work remaining before release

1. A supported factory route must accept and print these project-owned SDK
   implementations, passing typed settings and source pins without choosing
   harness behavior. The installed command currently rejects `handoff.executor` /
   `handoff.sdk`, requires an explicit egress declaration, and reports an
   unsupported compiled mechanism. Amp, Cline and
   OpenHands also have unsupported CLI parser names. The typed needs themselves
   pass the native `blank` validation; that does not establish execution support.
   Updating factory transport is a separate owner change, not implemented here.
2. Freeze and verify each target runtime's complete material, including worker
   executables and dependency licenses. The declaration marks closure unqualified.
3. Obtain authorized harness account/model scope, then retain representative
   real-use success, safe failure and interrupted-run evidence per capability.
   No harness provider calls or remote writes were made for this repair.
4. Bind that evidence to exact sources/tests, admit and release through Forge,
   then prove standalone consumption through Atlas and native AO.

Gemini and Junie have no SDK binding in the selected contracts; Grok uses its
protocol/CLI route. They are not counted among the eleven SDK implementations.
