# Evidence and limits

## Product access profiles and bridge governance — 2026-09-30

Added a required product/access/realm binding in `harness.control_host.v2`,
separate from saved harness launch settings and native named configuration.
ABAC's existing native Request evaluator governs bridge projection, launch,
continuation, review, and settings. Requests use the existing handoff resource
vocabulary; the host does not implement a second policy engine or manufacture
product permissions. The inspected Fact Lens policy's AO-FL-A context remains
an FL/OE authorization context, not a generic harness grant.

The [access-profile map](docs/access-profiles.md) lists every bridge door,
current native settings adapters, migration fields, and enforcement limits.
Added per-harness/repository readable profile inventory, optional Codex native
profile selection, exact settings/argument/context receipt bindings, and policy
rechecks before CLI/SDK effects. Direct model overrides and omitted saved
settings still pass the access gate when a host configuration is selected.
Projection denies hide unavailable harnesses. Configured governance requires an
absolute selected workspace with one unambiguous trusted repository mapping.

Validation used the existing local ABAC source through `ABAC_SOURCE`, building
the evaluator into temporary test directories. `python3 -m pytest` with that
source selected reported `203 passed in 6.97s`, with no skips. Real evaluator
checks cover exact model/permission-context/realm isolation, absent host binding,
and the existing Fact Lens policy refusing Codex projection even with the FL A
principal, role and AO-FL-A context. Representative local child programs verify
unchanged native argv and receipts for Codex/Muse/Claude; SDK calls and late
denials are simulated. These child checks are not native harness/provider
acceptance tests. No model provider, live access profile, native global config,
FL policy or external service was changed. `go test ./...` in the ABAC dependency
also passed.

Generated-tree checking reports all fourteen trees and the review skill match
their sources; only the Codex generated tree moved. Package manifest paths
exist and include the public-facing access-profile guide. Whitespace checking
is clean. Old host configuration schemas deliberately refuse; no live host
configuration was migrated or activated.

## Portable Codex model/settings preflight — 2026-09-30

The Codex skill now bundles its syntax catalog and standalone read-only helper,
with a relative [model/settings entrypoint](codex-harness-handoff/references/model-and-settings.md).
Capability evidence can be selected with `--capabilities` or MCP
`model_capabilities`. Exact effort pairs require a named model and fresh native
model-specific support evidence. The bridge validates rendered argv before
launch and distinguishes requested settings from native observations, including
the owned fresh thread journal when available. Profile authorization still uses
the existing ABAC path; capability evidence itself grants no permission.

Observed locally: installed `codex-cli 0.159.2` help exposes `--model` and `-c`;
the portable helper validated `gpt-6.1-sol` with `high` against current local
native metadata and rejected that model with `none`, exiting 2. No worker,
provider inference call, profile update, or external write was made. Current
official Codex configuration and CLI reference pages were opened to check the
public reference pointers. Private metadata and identity fields were not copied
into the skill package.

`python3 scripts/build_skills.py --check` reports
`OK 14 handoff skill trees + 1 review skill match skills-src/`.
`python3 -m pytest` reports `165 passed, 4 skipped in 3.25s`.
The new checks cover copied-skill operation outside the checkout, exact evidence
binding, unsupported/missing/stale/future/duplicate/malformed evidence, refusal
before launch, requested-vs-observed receipts, returned-thread journal identity,
and generated helper/catalog drift. Child launches and native journal metadata
in these tests are simulated; a new live worker's effective configuration was
not exercised. `git diff --check` is clean. Only the Codex generated tree changed.

## Optional Jev recovery — 2026-09-26

Added `resolve` and catch-all `recover` commands, asynchronous MCP wrappers,
an optional bounded Decisions worker, and offline recovery tasks. Reviewer
configuration is opt-in. Ordinary settings operations have no reviewer
dependency. The transport follows the existing local Jev Decisions client
shape; no provider calls, credential reads or live permission changes were made
during initial implementation. Initial evidence was compilation and generated
tree integrity only. The subsequent operator-requested review added 25 focused
offline regressions covering outages, malformed responses, exact-request bypass,
final ABAC denial, immediate contention, persistent episode bounds, independent
work and event-loop responsiveness. The full repository suite passes: 155 tests
in 4.52 seconds. Valid recovery receipts also exit the CLI successfully, so
callers can branch on status rather than retrying them as process failures.
The ABAC package suite also passes. Focused checks include real local ABAC
plan/apply and canonical-path checks against temporary stores. Provider failures
are injected; real provider acceptance and native approval callbacks remain
unverified. Per-process review limits are not global spend quotas. Persistent
recovery accounting bounds router issuance; individual tool actions still need
the owning native host's enforcement.

## Saved launch settings — 2026-09-26

Added an authored settings catalog, `scripts/harness-control` and MCP
describe/get/plan/apply tools for saved Codex, Muse and Claude launch profiles.
The opt-in fresh-handoff profile path evaluates policy using the companion
ABAC native-request CLI. See [control design and limits](docs/harness-control.md).

Observed locally: Python compilation succeeds; the CLI `describe` command lists
three supported harnesses and eleven unsupported harnesses; generated-tree
checking reports `OK 14 handoff skill trees + 1 review skill match skills-src/`;
the companion ABAC checkout builds with `GOPROXY=off GOSUMDB=off go build ./...`.
Whitespace checking is clean. These are compilation and source-integrity checks,
not functional or security acceptance evidence. No automated test suite was run,
no live profile applied, and no native settings or approval-hook behavior exercised.
Native approval auto-response and latency targets remain proposed work.

Reviewed 2026-09-08; command and approval-control recovery expanded 2026-09-09. Contract version 2 added SDK/protocol bindings on 2026-09-25. Installed CLI help was checked without launching new model work. Historical records informed the portable lessons below; private transcripts, paths, session IDs, and project-specific configuration are not distributed.

## Contract version 2 verification — 2026-09-25

`python3 scripts/build_skills.py` wrote 28 files across fourteen skill trees. `python3 scripts/build_skills.py --check` reported that all fourteen skill trees match `skills-src/`. `python3 -m pytest` passed 55 tests. `python3 scripts/check_harness_sources.py` reports installed binaries without launching model work; `git diff --check` is clean.

Installed CLIs observed without launching model work:

| Harness | Installed version |
| --- | --- |
| Antigravity | `agy 1.2.5` |
| Claude Code | `2.1.270` |
| Codex CLI | `codex-cli 0.156.1` |
| Cursor | `2026.07.23-e383d2b` |
| Gemini CLI | `0.56.0` |
| Grok Build | `grok 1.0.41` |
| Muse Code | `Muse Code 1.4.0` |
| OpenCode | `1.18.32` |
| Amp, Cline, Copilot, Droid, Junie, OpenHands | not installed on this machine |

Public registry-index observations, checked without installing packages or using credentials:

| SDK | Registry observation |
| --- | --- |
| `google-antigravity` | PyPI index listed `0.1.18` |
| `@anthropic-ai/claude-agent-sdk` | npm view listed `0.3.282`, engines `node>=18` |
| `claude-agent-sdk` | PyPI index listed `0.2.159` |
| `@openai/codex-sdk` | npm view listed `0.157.0`, engines `node>=18` |
| `openai-codex` | PyPI index listed `0.157.0`; available but intentionally unauthorized for this fresh-only Codex skill because it drives the app-server protocol |
| `@cursor/sdk` | npm view listed `1.0.32`, engines `node>=22.13` |
| `cursor-sdk` | PyPI index listed `1.0.32` |
| `@muse-code/sdk` | npm view listed `1.3.0`, engines `node>=20` |
| `muse-code-sdk` and `muse-code-msp` | PyPI index listed `1.3.1`; package metadata identifies the official Muse SDK repository and preview status |
| `@opencode-ai/sdk` | npm view listed `1.18.32` |
| `xai-sdk` | PyPI index listed `1.20.0`; this is a separate xAI model API SDK, not native Grok Build session control |
| `@github/copilot-sdk` | npm view listed `1.0.14`, engines `node>=20.19`; official docs mark the SDK family technical preview |
| `github-copilot-sdk` | PyPI index listed `1.0.14`, requires Python 3.11+ |
| `@cline/sdk` | npm view listed `0.0.86`, engines `node>=22` |
| `cline` CLI | npm view listed `3.0.65` |
| `@factory/droid-sdk` | npm view listed `0.8.0`, engines `node>=18` |
| `droid-sdk` | PyPI index listed `0.5.0`, described as the Factory Droid Python SDK; the TypeScript SDK is the authorized binding until the Python surface is verified |
| `openhands-sdk` | PyPI index listed `1.49.6` |
| `@ampcode/sdk` | npm view listed a dated `0.1.0` build, engines `node>=18` |
| `amp-sdk` | PyPI index listed a dated `0.1.2026` build |
| `@google/gemini-cli-sdk` | not found on npm; Gemini CLI ships as CLI-only in this contract until a published SDK is verified |

Popularity triangulation used the JetBrains Developer Ecosystem Survey 2026 (May–July 2026, 15,000+ professional developers) for work-use ranking, Stack Overflow 2025 for baseline adoption and trust, and GitHub stars, CLI directories, registries, and vendor docs for implementation availability only. The survey's top tier is Claude Code 39%, GitHub Copilot 21%, Codex 16%, Cursor 12%, JetBrains AI/Junie 9%, OpenCode 7%, and Antigravity 6%.

No SDK package was installed in the working environment, and no SDK session was executed with credentials. The installed Python and Node environments did not resolve the contract's SDK imports at check time. Registry versions are observations only and are not pinned in `contracts.json`.

Official SDK/protocol sources consulted for the version-2 bindings:

- Antigravity SDK overview
- Claude Agent SDK overview and session documentation
- OpenAI Codex SDK documentation
- Cursor TypeScript/Python SDK and bridge documentation
- xAI Grok Build headless-scripting and ACP documentation
- Muse SDK repository, quickstart, and Python package metadata
- OpenCode SDK and server documentation

Remaining live-test gaps: per-harness SDK smoke runs, exact session-ID capture/resume/fork behavior, SDK/host schema compatibility for Muse preview, owned-versus-shared server behavior for OpenCode, and busy-session behavior for Cursor and Muse. The new Amp, Cline, Copilot, Droid, Gemini, Junie, and OpenHands trees are docs- and registry-checked only; none of those six binaries is installed here and no SDK session was executed. Downstream consumers of `contract.json` must handle contract version 2 themselves; the separate harness-fleet refactor is out of scope for this package.

## MCP bridge verification — 2026-09-25

`mcp_bridge/` is operator-side tooling, not a generated skill. `python3 -m pytest tests/test_mcp_bridge.py` passes 19 offline tests: mocked subprocesses, fake SDK module probes, contract-driven route selection, Codex continuation refusal, exact-ID requirements, secret redaction, and refusal of unverified CLI continuation shapes. The FastMCP server boots and lists five tools (`list_harnesses`, `get_contract`, `handoff_fresh`, `handoff_continue`, `session_history`). No live harness was launched, no SDK session executed, and no credentials used; every contract entry still carries `sdk_smoke_passed: false`.

| Harness | Evidence used | What it supports | Remaining limit |
| --- | --- | --- | --- |
| Muse | Existing CLI/schema guide and retained 1.0.3-R2198.1 live-test report | History/export mechanics; child follow-up with unique command identity | Cross-session ingress failed in that test |
| Antigravity | Existing CLI guide and retained 1.1.26 live-test report | Native child messaging, streaming turns, exact-ID resume | No arbitrary busy-process attachment proof |
| OpenCode | Installed 1.18.28 help, resolved paths, historical worker result reports | Session run/export syntax; successful smoke report and separate auth failure | Historical report is not a new end-to-end test |
| Grok Build | Installed 1.0.0 help; historical structured handback and failure reports | Native list/search/export/resume; output-format lesson | Current resume and live transport not exercised |
| Cursor | Installed 2026.07.23-e383d2b help; local SQLite schema; retained resume attempt | Separate CLI store; exact-ID resume syntax; Keychain failure lesson | Inspected attempt does not establish successful continuation |
| Codex | Installed 0.153.2 help; existing delegation skill and historical transport/worktree notes | Exec/resume mechanics, app/native routing distinctions | Every app-server mode was not retested |
| Claude Code | Installed 2.1.251 help; existing delegation skill and exact-ID handoff records | Print/resume, background controls, transcript discovery | Historical handoff instructions alone do not prove each execution path |

Older instructions can conflict with current versions. Use help for the exact installed subcommand, retain the user's scope and configuration, and distinguish history inspection, resumed execution, message acceptance, and completed work.

The core handoff lesson from prior use is to provide the goal, current state, constraints, and expected output. Let the receiving agent use its native tools. Preserve outcome checks without copying private orchestration services or personal launch defaults.

## Recovered operating details

- Muse: full operating guide, `--yolo` and separate approval/sandbox/trust flags, three worktree strategies, offline export and folded history, cross-session ingress versus parent-owned child messaging versus MSP root turns, follow-up command identity, and the recorded closed-ingress failure.
- Antigravity: full operating guide, exact conversation continuation, caller-owned streaming envelopes, child messaging and transcript locations, approval bypass versus sandbox settings, workspace/project distinctions, and successful process exit with soft-denied work.
- Codex: exec/resume/fork controls, YOLO alias and explicit bypass, sandbox versus approval policy, native queue and agent discovery, local/app/remote distinctions, process handles, and worktree recovery.
- Claude Code: print/resume/fork, native background IDs and logs, streaming input, permission bypass versus enabling bypass, tool grants, authentication effects of bare mode, and nonpersistent sessions.
- Cursor: exact chat continuation, CLI versus IDE history, headless output, force/YOLO versus sandbox and workspace trust, worktree options, and the recorded Keychain authentication failure.
- Grok Build: native discovery/export/resume, new-session ID semantics, approval controls, conversation-only versus code restoration, distinct streaming formats and transports, and process/result disagreement.
- OpenCode: session/export/run/attach, headless auto-approval of non-denied tools, directory semantics for remote attachment, model/provider selection, and auth/process failures.

Help validation establishes accepted syntax and documented behavior, not a successful inference or handoff. Historical live-test findings remain labeled by their original versions and dates. No claim is made that every launch, permission mode, transport, or installed host skill-discovery path has been exercised end to end.

## Source-recovery disposition

The recovery compared the original authoring record, the Muse and Antigravity operating/live-test guides, existing Codex/Claude/OpenCode delegation guides, cross-harness handoff lessons, and retained command/failure reports against the published package. Current help and official documentation resolve version conflicts. The portable operating details are included in each skill and its references; the original private transcripts are not redistributed.

Preserved lessons include respecting a redirect immediately, sending outcomes rather than imposing the sender's tool recipe, retaining existing authorization without broadening it, relaying new approval questions, preventing duplicate workers, separating session/process/worktree identity, and independently checking resulting artifacts.

Not carried forward as current facts: universal PTY/tmux requirements, blanket print-mode permission approval, mandatory Git initialization, Claude having no native messaging, treating an agent browser as a JSON session index, fixed historical model/cost defaults, private coordination services, and speculative context-percentage thresholds. Product-specific project policy and unrelated hook/plugin tutorials are not portable handoff mechanics. Discovery paths and schemas remain version-sensitive, and bounded historical retrieval cannot certify that deleted or unindexed records have been recovered.


## Resolved launch-plan boundary — 2026-09-30

Fresh CLI and SDK launches resolve one immutable private plan before final ABAC
approval. Execution consumes the captured adapter, executable, canonical
workspace and native inputs. Public metadata uses `harness.launch_plan.v1`;
ABAC receipts use `harness.launch_authorization.v1` and bind the plan digest.
The internal raw CLI arguments/receipt execution interface was removed.

Validation: `ABAC_SOURCE=... python3 -m pytest -o addopts='' -q` passed **221
tests** using the real local ABAC evaluator. The 18 launch-plan cases cover a
representative local child consuming approved argv/cwd, resolved model and route
policy, immutable snapshots, changed-plan receipt rejection, rehashed mismatched
model arguments, canonical workspace/executable aliases, changed executable
bytes, policy changes, held model-evidence freshness, captured SDK dispatch and
refusal of the former raw interface. Local children and SDK callback fixtures
exercise the bridge boundary; no vendor inference, credentials or live sessions
were used.

`python3 scripts/build_skills.py --check` confirmed all fourteen generated
handoff trees and the review tree match authored sources. This launch-plan
change required no additional generated skill-tree edits. `git diff --check`
passed. The package manifest includes the resolver and public launch-plan guide.

SDK pins cover the Python runtime and bridge callable/options, not SDK-managed
worker binaries or vendor configuration. File identity checks are pre-dispatch
checks, not an atomic filesystem lock. Session-ID ownership, timeout descendant
cleanup and per-profile revision isolation remain separate follow-ups. No live
host configuration or policy was activated or changed.


## Connected access product scope — 2026-09-30

`docs/connected-access-scope.md` records the selected thin connection host plus
standalone printed operation Process architecture. It defines the first-release
boundary, proposed contracts, reuse map, permission freshness/recovery behavior,
exclusions and real-use readiness gates. It is a proposal, not implemented or
admitted access machinery. README and package manifest point to the scope.

Documentation links and packaged-file inclusion checked successfully;
`git diff --check` passed. `python3 scripts/build_skills.py --check` confirmed
fourteen handoff trees and the review tree remain current. No generated skill
files changed for this scope. The existing suite, using the real local ABAC
source, passed **221 tests in 13.42s**. These checks do not qualify the proposed
product, authenticate a connection or exercise any live system integration.

## Fresh SDK Node source repair — 2026-10-16

The isolated SDK authoring set now has eleven fresh-only Node/Block/Process plans.
`mcp_bridge/sdk_bindings.json` owns their supported typed settings and package
bindings. The project captures SHA-256 pins for eleven published SDK archives and
the supplemental Muse protocol archive; this does not qualify their full runtime
closures. Codex no longer selects a permission profile in its adapter. Completion
checks reject send-only acknowledgments, unsuccessful terminal results and empty
assistant output. Muse distinguishes a resolved turn from a successful turn.

Local verification with the actual local ABAC evaluator source passed **323 tests
with no skips**. This includes Python adapters, TypeScript adapter checks, and
subprocess runner fixtures checking source drift, settings refusal before vendor
import, and the JSON stdout channel. These SDK fixtures prove local mechanics;
they do not represent provider success or admission evidence. The wheel builds,
and inspection confirms exactly eleven fresh plans and all project runtime files.
The skill generator's `--check` and `git diff --check` pass. Only Cline's generated
contract changed; skill prose trees remain unchanged.

All eleven supported `forge-author plan -check` attempts refused the current
contract store (`harness contract: parser`). No revised SDK Process was printed,
invoked, admitted or released, and no native AO consumption was claimed. No
provider calls or remote job writes were made. Remaining work is documented in
[`praxis/handoff/sdk/README.md`](praxis/handoff/sdk/README.md): supported factory
SDK execution/contract acceptance; sealed target runtime material; authorized
real-use success, safe-failure and interruption evidence; then exact-source
admission, release and standalone consumption. Historical experimental prints
are retained separately and are not qualification of these revised sources.

### Correction using the installed authoring front door

Follow-up checks confirmed that the installed `forge-author` is current. The
previous common parser refusal hid project authoring defects: unsupported
`minLength`/`pattern` schema keywords, an empty item enum for OpenHands, and an
OpenCode required dictionary key absent from its fixed properties. These were
repaired using the supported type vocabulary. Nonempty settings remain an
explicit declaration rule enforced by both runners; array enums compare values
structurally. Each plan now selects only its own contract store and shipped
contract asset, preventing unrelated CLI parsers from poisoning its diagnostics.

All eleven typed needs pass actual installed `forge-author blank` validation.
That records missing implementation boundaries and does not assert executable
Nodes. Independent plan checks now reveal the unsupported experimental
`handoff.sdk` / `handoff.executor` declarations, missing egress operation
declarations and unsupported compiled source mechanism.
Amp, Cline and OpenHands also retain unsupported CLI parser names. No parser was
renamed to bypass that refusal and no Forge implementation was edited.

The suite passes **346 tests with no skips**, including native type-vocabulary
checks for all eleven plans and preserved nonempty-setting refusal checks.
Skill generation and diff checks pass. The package includes a separate store
and contract asset for each capability. These results supersede the earlier
shared-store diagnosis; no revised SDK print or real provider run is claimed.


## 2026-10-16 — Implemented generic Forge SDK execution

The operator clarified that adding missing SDK execution support was part of the
requested build. Forge support was implemented in an isolated worktree and
branch `codex/harness-sdk-support-20261016`; no shared source checkout or global
installed command was changed.

The earlier "experimental/unsupported" assessment described an unfinished local
prototype. The new generic executor validates the project-pinned package and
entrypoint contract, every project runtime source, and interpreter bytes. It
forwards typed inputs, supplies only declared credential environment names,
retains failed diagnostics and partial output with those credential values
redacted, and kills the local child process group on an authored timeout. It
contains no vendor list, model choice, permission profile, or fresh/resume policy.
Harness custody continues to own network use; Forge's contradictory generic
HTTP-egress requirement was corrected. Unknown CLI parsers remain refused on the
CLI route and do not select SDK behavior.

All eleven native plan checks pass and all eleven standalone unsigned packages
build. Each SDK has private material paths. Eleven native Block artifacts and
`praxis/handoff/sdk/capabilities.json` retain their exact revisions. The project
suite passes **347 tests, no skips**; generator `--check` passes for 14 handoff
trees and one review tree. Forge's Harness/SDK, compiled-source and compiler
checks pass, as do the author-plan tests. The wheel includes all eleven Blocks,
the revision index, runtime pins and source helpers.

Each exact development package was invoked with an empty SDK workspace, empty
credential environment and a separate empty home. All eleven correctly failed
before vendor imports because the selected dependencies were absent. The driver
receipts retained the runtime/request digests and dependency error details.
These are startup mechanics checks, not real-use SDK success or admission proof.
Local SDK simulations additionally cover successful settings forwarding, failure
retention, runtime/source drift and local descendant cancellation.

Evidence: `/Users/nate/Documents/Codex/2026-10-16/harness-handoff-correction/`:
`sdk-support-checks-final`, `sdk-development-pinned`,
`sdk-safe-startup-final/checked-summary.json`, `sdk-pytest-final.txt`, and
`sdk-support-result.json`. The result record identifies the final worker build,
source commits and artifact pins. Earlier attempts are retained as earlier
attempts; no source or readiness observation was relabeled.

The globally installed factory has not been replaced. Full vendor runtime
closure, authorized account success/safe failure and interruption recovery,
admission/release, Atlas catalogue promotion and native AO consumption remain
unproven. No harness provider calls, remote jobs, spend or FL work occurred.


## 2026-10-16 — Captured SDK runtimes, installed factory and Atlas publication

All eleven fresh SDK Nodes and pinned Blocks build through the installed
`/Users/nate/.local/bin/forge-author`. The generic SDK support was integrated
into the factory checkout with three-way merges preserving existing edits, then
installed through `scripts/install-tools.sh`. `forge-author status -summary`
reports all three installed factory tools current. Forge implementation commits
are `ea319d9` and `baee098` on `codex/harness-sdk-support-20261016`.

Each Node now carries a SHA-256-pinned Darwin ARM64 runtime capsule: portable
Python 3.13.13 or Node 24.22.0, its SDK dependencies and metadata, and required
native executables. All eleven relocated SDK imports pass. Capture records file
hashes/modes; the launcher verifies the bytes read while extracting and checks
its executable before launch. SDK imports resolve inside the capsule, independently
of the caller's working directory. Large runtime archives remain local material,
outside Git and the Python wheel; their exact pins are committed.

Native `node` authoring and `catalog` publication pass for all eleven declarations.
They are published into the local Atlas data root; its ordinary stores manifest
includes their contract and dispatch-test references. A subsequent native `reuse`
returns all eleven exact Node revisions, all reusable, with no inventory gaps.
The pinned Go test checks the dispatch boundary only. Empty vendor behavior
case declarations do not assert qualification or admission.

Current-source development calls passed for **Claude, Codex, Copilot, Droid,
OpenCode, Cline and OpenHands**. Each returned independently expected
`SDK_QUALIFIED` output, a fresh session identity distinct from previous attempts,
and the exact current Node pin in its Process receipt. Working directories were
empty, non-Git directories. Copilot used its supported custom-provider option;
Droid used its supported `ProcessTransport` stdio route with a native custom
model. Neither required a separate GitHub or Factory credential. Claude used the
existing bearer-token route after adding the missing declared
`ANTHROPIC_AUTH_TOKEN` variable. Codex used the existing native account.

Real execution exposed and repaired three mistakes hidden by local fixtures:
Droid exports message discriminants rather than the invented message enum;
OpenCode SDK 1.19.0 needs its matching official executable rather than an ambient
similarly named package; and Muse enforces its exact host/MSP fingerprint and a
machine-safe client name. Muse SDK/MSP 1.4.10 now match the captured host, and
its actual handshake/model listing passes. Claude error details are retained,
and its stream drains before raising a failed terminal result. Failed attempts
remain separate evidence and were not relabeled as successes.

The project suite passes **350 tests, no skips**. Skill generation prints
`OK 14 handoff skill trees + 1 review skill match skills-src/`. Focused integrated
Forge checks pass in `forge`, `proof`, `forge/egress_bundle` and
`cmd/forge-author`; the final runtime/observer recheck also passes. The wheel
contains all eleven Blocks, runtime pins, capture/publication tools and the
pinned dispatch test. Diff checks pass. No skill prose changed.

Evidence root:
`/Users/nate/Documents/Codex/2026-10-16/harness-handoff-correction/`.
The final records are `sdk-completion-report.json`,
`sdk-development-auth-binding/summary.json`, `sdk-catalog-auth-binding/`,
`sdk-pytest-auth-binding.txt`, `sdk-integrated-go-checks.txt`,
`sdk-final-proof-checks.txt`, `sdk-installed-status.txt`, and the named
`sdk-live-debug/*-current-source` captures plus `claude-auth-binding`.
The observed aggregate OpenRouter account usage increased by about **$0.13**
against the authorized $5 ceiling; the ledger records settlement snapshots and
keeps native harness account routes separate. No new accounts were created.

These are unsigned development and catalogue results. Native SDK proof mechanics
are implemented and checked with explicitly owned local fixtures; real vendor
admission, release and native AO qualification have not been asserted. The
readiness flags retain those distinctions. No FL implementation or data changed.
