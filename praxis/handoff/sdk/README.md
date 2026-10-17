# Fresh SDK Nodes, Blocks, and Processes

This directory contains **eleven fresh SDK Nodes and eleven reusable pinned
Blocks**. Each has passed the native plan checks and built a standalone unsigned
Process package through the SDK support branch of `forge-author`.
[`capabilities.json`](capabilities.json) records the exact Node, Block and Process
revisions; [`blocks/`](blocks/) contains the Forge-produced Block artifacts.
Admission and release remain separate from unsigned development execution.
All eleven declarations are published in the local Atlas catalogue and resolve
through its ordinary stores manifest. Live development calls through Claude, Codex, Copilot, Droid, OpenCode,
OpenHands and Cline have completed using existing account routes. Exact attempt evidence is recorded in EVIDENCE.md.

The generic SDK executor is implemented in Forge branch
`codex/harness-sdk-support-20261016`, integrated into the local factory checkout,
and installed through its normal tool installer. The entry point is
`/Users/nate/.local/bin/forge-author`. The factory validates package/entrypoint contracts, material
and interpreter hashes, then launches one project-owned runner. SDK names,
operations, settings and permission choices remain here.

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
| Copilot | `github-copilot-sdk` | 1.0.18 | model, permission handling, optional typed custom provider; workspace supplied per call |
| Muse | `muse-code-sdk` | 1.4.10 | provider, model, approval mode, offered permission-profile ID |
| Antigravity | `google-antigravity` | 0.1.22 | model, native/unattended policy, recovery directories |
| OpenHands | `openhands-sdk` | 1.54.0 | model and tools; this implementation supports an empty tool list |
| Amp | `@ampcode/sdk` | 0.1.0-20260918210405-g81edbf0 | mode, visibility, allow-all flag, tool permission rules |
| Cline | `@cline/sdk` | 0.0.93 | provider/model, tool policies, unmatched approval handling, tool/spawn/team switches |
| Codex | `@openai/codex-sdk` | 0.162.1 | model, sandbox mode, approval policy, network access, web search mode, optional Git-check control |
| Droid | `@factory/droid-sdk` | 0.9.1 | model, native autonomy/interaction mode, permission handling, optional SDK transport choice |
| OpenCode | `@opencode-ai/sdk` | 1.19.0 | provider/model and permission rules; both session requests bind the workspace |

Muse also pins `muse-code-msp` 1.4.10 as supplemental material because the SDK
imports it without declaring it in its published dependency metadata. The runner
checks that supplemental version before importing the SDK.

These schemas describe the implemented subset of each SDK. Other vendor options
require extending the declaration and implementation together. No model name or
permission-profile name is selected by an adapter. Muse verifies that its selected
profile was applied. Codex uses the caller's thread options, with no hardcoded
`audit`, `:read-only` or other named profile.

## Completion and integrity

The generic launcher records startup, diagnostics, source/runtime digests and
unknown effect outcomes on failure. Failure details survive in the printed
worker's typed failure record; declared credential values are redacted there.
Each Node has private material paths, so SDK implementations can compose without
sharing mutable runner files.

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

Each printed package now carries a target-pinned runtime archive: portable Python
3.13.13 or Node 24.22.0, the selected SDK and transitive dependencies, their
installed metadata/licenses, and required native executables. Exact archive and
executable hashes are in `authoring/runtime-pins.json`. A build-time capture
manifest records every selected file and mode. The launcher authenticates and
extracts the archive into private invocation custody; it never installs packages
at runtime. TypeScript dependencies resolve inside this captured root, independently
of the caller's workspace. SDK-managed native executable selection is captured
as implementation material.

`python3 scripts/capture_sdk_runtime.py --input SELECTION.json --out MATERIAL_DIR`
captures explicitly selected installed directories/files. A selection declares
`target`, `sources` (each with `source` and package-relative `destination`),
`runtime` (`binary`, `arguments`), `configuration` (runner dependency/native
paths), and `provenance`. It refuses escaping links and changed source bytes.
Place each resulting content-addressed archive under
`authoring/assets/runtime/` before building. These large local build artifacts
are not stored in Git. Source generation and unit checks use the committed pins;
Forge requires and authenticates actual bytes for every build and invocation.

Only the environment names declared per binding are passed alongside the native
session base environment (`PATH`, `HOME`, `TMPDIR`). Credential values stay in
execution custody and never enter the public declaration. SDKs may use a native
login, a supported custom provider, or no credentials where supported. Neither
vendor accounts nor Git trees are prerequisites for authoring Nodes.
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
python3 scripts/publish_sdk_nodes.py --root /path/to/atlas/data --evidence /path/to/new-publication
```

The fetch command retrieves and checks public SDK archives without installing or
executing them. Publication validates exact Node declarations and their local
dispatch-test pins, then adds them to the selected Atlas data root. It does not
execute a provider or grant admission. The check command captures all eleven native factory results,
including refusals. Each plan uses its own `stores-<capability>.json`, so an
unrelated harness contract cannot prevent checking that capability. These commands never admit, sign or invoke a Node. Local
fixtures prove mapping and refusal mechanics; they are not real-use evidence.

## Qualification and release

The installed factory supports SDK Harness authoring, publication, development
execution and native qualification. The Harness custody boundary owns network
use; unknown CLI parsers cannot select or block the explicit SDK executor.

Runtime capture and relocation checks cover all eleven Darwin ARM64 capsules.
Those checks prove captured material and import mechanics; the declaration keeps
vendor qualification separate. The committed proof test checks that direct Go
dispatch cannot bypass the printed runtime. Its empty behavior declaration does
not claim real provider qualification.

For admission, author representative success, held-out and safe-failure cases
for the selected operation/configuration. Supply exact material and explicit
execution-owner custody through `create.harness_sdk`; credentials are optional,
according to the selected SDK route. Forge observes the ordinary printed SDK
launcher twice and evaluates the results independently. Candidate-authored test
reports cannot provide the observations. Admission, release and native AO evidence
remain factory-owned stages for each exact qualified scope.

Gemini and Junie have no SDK binding in the selected contracts; Grok uses its
protocol/CLI route. They are not counted among the eleven SDK implementations.
