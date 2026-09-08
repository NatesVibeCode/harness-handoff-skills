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

These are instruction templates, not executable integrations. They do not install CLIs, supply credentials, or guarantee cross-application messaging. Live delivery has not been tested across the five products; agents must consult the installed tool's help before using commands or flags. In these files, "operator" means the person requesting the work.

The skills contain no required private services, personal filesystem paths, or account configuration. Product names belong to their respective owners; this is an independent community project.
