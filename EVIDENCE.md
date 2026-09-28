# Evidence and limits

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
