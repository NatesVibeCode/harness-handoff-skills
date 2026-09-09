# Harness handoff skills

Portable agent instructions for handing work to Muse, Google Antigravity, OpenCode, Grok Build, Cursor, Codex, and Claude Code.

Each folder contains a `SKILL.md` entrypoint and supporting references. Copy the whole desired folder, including `references/`, into your agent's supported skill directory. If your agent does not load skills, provide the entrypoint and the references relevant to the task as instructions. Skill installation and discovery depend on the host application.

## Included skills

- `muse-harness-handoff`
- `antigravity-harness-handoff`
- `opencode-harness-handoff`
- `grok-harness-handoff`
- `cursor-harness-handoff`
- `codex-harness-handoff`
- `claude-harness-handoff`

## Usage

Ask your agent: "Use the Cursor handoff skill to hand this work to my selected Cursor workspace. Include the current state, relevant files, constraints, and next action."

The instructions guide the agent to discover available native capabilities, select the intended destination, and transfer a concise handoff packet. When direct delivery is unavailable, they produce text for manual pasting.

Each skill includes a history and continuation reference: native session commands, local storage discovery, read-only database inspection, transcript lookup, and continuation mechanics. Muse and Antigravity references preserve version-specific findings from existing adapter guides. OpenCode and Cursor command references link official documentation. Cursor database paths are discovery candidates, and Grok history depends on the application that owns it.

Each entrypoint includes harness-specific CLI recipes for discovery, execution, continuation, and approval controls. Muse and Antigravity also include detailed operating guides with native message schemas, worktree behavior, and recorded recovery lessons. The approval controls are deliberately different: a `--yolo` recipe from one CLI must not be copied into another.

These are operational instructions with runnable command examples, not installed integrations. They do not install CLIs or supply credentials. Live delivery has not been tested across all seven harnesses; agents must consult installed help before using version-sensitive commands. In these files, "operator" means the person requesting the work.

See [evidence and limits](EVIDENCE.md) for checked versions, historical successes, failures, and untested paths. The skills contain no required private services, personal filesystem paths, or account configuration. Product names belong to their respective owners; this is an independent community project.
