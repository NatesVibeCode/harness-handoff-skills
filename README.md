# Harness handoff skills

Portable agent instructions for handing work to Muse, Google Antigravity, OpenCode, Grok, and Cursor.

Each folder contains a standalone `SKILL.md`. Add the desired folder to your agent's supported skill directory, or provide its contents as instructions if your agent does not load skill files. Skill installation and discovery depend on the host application.

## Included skills

- `muse-harness-handoff`
- `antigravity-harness-handoff`
- `opencode-harness-handoff`
- `grok-harness-handoff`
- `cursor-harness-handoff`

## Usage

Ask your agent: "Use the Cursor handoff skill to hand this work to my selected Cursor workspace. Include the current state, relevant files, constraints, and next action."

The instructions guide the agent to discover available native capabilities, select the intended destination, and transfer a concise handoff packet. When direct delivery is unavailable, they produce text for manual pasting.

Each skill includes a history and continuation reference: native session commands, local storage discovery, read-only database inspection, transcript lookup, and continuation mechanics. Muse and Antigravity references preserve version-specific findings from existing adapter guides. OpenCode and Cursor command references link official documentation. Cursor database paths are discovery candidates, and Grok history depends on the application that owns it.

These are instruction templates, not executable integrations. They do not install CLIs or supply credentials. Live delivery has not been tested across all five products; agents must consult installed help before using version-sensitive commands. In these files, "operator" means the person requesting the work.

The skills contain no required private services, personal filesystem paths, or account configuration. Product names belong to their respective owners; this is an independent community project.
