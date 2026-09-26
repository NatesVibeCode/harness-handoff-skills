# Harness handoff skills

Portable agent instructions for handing work to Amp, Muse, Google Antigravity, OpenCode, Grok Build, Cursor, Codex, Claude Code, Cline, GitHub Copilot, Factory Droid, Gemini CLI, JetBrains Junie, and OpenHands.

Each folder contains a `SKILL.md` entrypoint and supporting references. Copy the whole desired folder, including `references/`, into your agent's supported skill directory. If your agent does not load skills, provide the entrypoint and the references relevant to the task as instructions. Skill installation and discovery depend on the host application.

## Included skills

- `amp-harness-handoff`
- `muse-harness-handoff`
- `antigravity-harness-handoff`
- `opencode-harness-handoff`
- `grok-harness-handoff`
- `cursor-harness-handoff`
- `codex-harness-handoff`
- `claude-harness-handoff`
- `cline-harness-handoff`
- `copilot-harness-handoff`
- `droid-harness-handoff`
- `gemini-harness-handoff`
- `junie-harness-handoff`
- `openhands-harness-handoff`
- `harness-session-review` — a separate read-only Codex/Muse/OpenCode review workflow

The cross-harness review has a local metadata/health helper and a fixed output
contract. From a checkout, run:

```sh
python3 scripts/session_review.py doctor
python3 scripts/session_review.py inventory \
  --from 2026-09-01 --through 2026-09-25 \
  --timezone America/Los_Angeles
python3 scripts/session_review.py search "invoice workflow" --mode all \
  --from 2026-09-16 --through 2026-09-26 \
  --timezone America/Los_Angeles
```

The default scope is the current filetree (current directory plus descendants),
not every session in the harness. Use `--tree /path` to choose another tree,
`--scope all` to opt into all local trees, or set `HARNESS_SESSION_REVIEW_SCOPE`
as the default. Dates are inclusive in the requested IANA timezone (UTC by default).
Inventory and default search results print metadata only. Search uses a transient,
in-memory SQLite FTS5 index; `--show-excerpts` explicitly includes short matching
text that may contain sensitive content. It does not save transcripts or call a
provider. Modes are `all` (terms across a session), `any`, `phrase` (within a
message), and raw FTS5 `fts`. Codex discovery
streams every JSONL file in the active and
archived session roots. Muse uses its local `session-index.db` in read-only mode;
OpenCode resolves its database through `opencode db path` and queries session
metadata read-only, avoiding the CLI list-output cap. Use `--muse-index` or
`--opencode-db` for non-default local stores. No session-count cap is applied.
The helper never invokes an inference API or continues a session. The generated report contract is in
`harness-session-review/review-output.schema.json`; the skill separates those
observations from human/model judgments and reports gaps explicitly.

## Usage

Ask your agent: "Use the Cursor handoff skill to hand this work to my selected Cursor workspace. Include the current state, relevant files, constraints, and next action."

The instructions guide the agent to discover available native capabilities, select the intended destination, and transfer a concise handoff packet. When direct delivery is unavailable, they produce text for manual pasting.

Each handoff skill includes a history and continuation reference: native session commands, local storage discovery, read-only database inspection, transcript lookup, and continuation mechanics. Muse and Antigravity references preserve version-specific findings from existing adapter guides. OpenCode and Cursor command references link official documentation. Cursor database paths are discovery candidates, and Grok history depends on the application that owns it. The standalone session-review skill uses a separate contract and does not authorize continuation.

Each entrypoint includes harness-specific SDK, protocol, and CLI recipes for discovery, execution, continuation, and approval controls. Muse and Antigravity also include detailed operating guides with native message schemas, worktree behavior, and recorded recovery lessons. The approval controls are deliberately different: a `--yolo` recipe from one CLI must not be copied into another.

## Generated skills — edit the source, not the trees

The fourteen `*-harness-handoff/` folders and the standalone
`harness-session-review/` skill package, including its bundled helper, are
**generated**. Do not hand-edit them; a hand-edit is overwritten by the next
build and caught by `--check`.

```sh
python3 scripts/build_skills.py            # regenerate fourteen trees plus the review skill
python3 scripts/build_skills.py --check    # fail if a checked-in tree is stale
```

Author these instead:

| Source | Holds |
| --- | --- |
| `skills-src/contracts.json` | Each harness's execution contract — binary, prompt delivery, parser, SDK/protocol binding, argv template, references |
| `skills-src/lane-spawning/<harness>.md` | The one authoritative `## Direct lane spawning` block |
| `skills-src/harnesses/<harness>.md` | The authored remainder of that skill's body |
| `skills-src/session-review.md` | The cross-harness review workflow |
| `skills-src/session-review-output.schema.json` | The review report's output contract |
| `scripts/session_review.py` | Metadata inventory and local CLI/auth diagnostics; copied into the review skill |

The build emits each handoff tree's `SKILL.md` plus a `contract.json` — the same
contract in machine-readable form, so a tool that drives these harnesses can read
the contract instead of parsing prose. It also emits the review skill, its report
schema, and a self-contained helper copy. `harness-fleet`'s harness adapters cite
the handoff skills as their source of truth, and its
`scripts/check_harness_drift.py` validates each adapter against the generated
`contract.json`.

`references/*.md` stay authored — they are prose, not duplicated across harnesses — but
`contracts.json` must list them, and the build fails if a reference is present but
undeclared or declared but missing.

This layout exists because the trees used to be hand-maintained copies. Commit `9322d55`
pasted the lane-spawning block into every file five or six times without deduplicating,
which is exactly the failure a single source removes. `scripts/extract_skill_sources.py`
is kept as the one-time migration that derived `skills-src/` from those copies.

These are operational instructions with runnable command examples, not installed integrations. They do not install CLIs or supply credentials. Live delivery has not been tested across all fourteen harnesses; agents must consult installed help before using version-sensitive commands. In these files, "operator" means the person requesting the work.

## Optional MCP bridge (`mcp_bridge/`)

An operator-side MCP server that connects the v2 contracts to real execution. It is **not** part of the generated skills and it never fans out lanes: each tool call performs at most one caller-owned execution in exactly one harness.

```sh
python3 mcp_bridge/server.py   # stdio transport; wire into your MCP client config
python3 -m pytest tests/test_mcp_bridge.py  # offline tests: mocked subprocesses, no credentials
```

Tools: `list_harnesses`, `get_contract`, `handoff_fresh`, `handoff_continue`, `session_history`.

Routing per call: authorized Python SDK when importable (Claude, Cursor, Copilot, Muse, Antigravity, OpenHands), otherwise the pinned CLI fallback every harness declares. Contract and bridge guards refuse Codex continuation, require exact session IDs, reject newest/continue selectors, redact known secret patterns in receipts, and refuse unverified CLI continuation shapes (Cline, Amp, Copilot). Requires the `mcp` Python package for serving; the contract loader, CLI executor, and tests have no third-party dependencies.

`handoff_fresh` accepts `approval=default|restricted|unattended`. Codex CLI's
default is an autonomous full-access run after an explicit operator handoff;
`restricted` selects a read-only sandbox with on-request approval. OpenHands
headless CLI requires an explicit `approval=unattended` choice before launch.
Copilot uses its normal CLI route by default; its SDK `approve_all` path requires
`approval=unattended` and an explicit model, including the approval choice on
continuation. The OpenHands SDK adapter also requires an explicit model. For
other routes the bridge implements only `default`; use a native harness surface
when a specific approval policy is required. A selected workspace or model is
refused when the chosen adapter cannot bind it. Prompt staging files are
removed after execution, and the Codex final message is copied into the receipt.
Some CLI contracts put the task prompt in process arguments; keep credentials
out of prompts for those routes. Receipt redaction covers known token patterns,
not arbitrary sensitive text.

The bridge refuses Copilot and OpenHands `approval=unattended` calls unless its process has
`HARNESS_HANDOFF_UNATTENDED_HARNESSES` set to a comma-separated list containing
that harness, for example `copilot,openhands`. Codex does not require this
setting; the MCP host must enforce the operator's dispatch request. This server
setting is an allowlist,
not proof that a particular task was approved. The stdio MCP bridge has no
per-user authentication; connect it only to a trusted local MCP host and use
that host's tool approval controls for each execution.

See [evidence and limits](EVIDENCE.md) for checked versions, historical successes, failures, and untested paths. The skills contain no required private services, personal filesystem paths, or account configuration. Product names belong to their respective owners; this is an independent community project.
