# Security policy

## What this repository is

A generator, fourteen handoff skill trees, a session-review skill, seven Go
session clients, and an optional Python MCP bridge. The generated skills are
instructions and contracts; the clients and bridge can execute harness calls
when an operator selects them. The session-review helper reads local session
stores and can emit matching text when excerpts are explicitly requested.

That shapes what a vulnerability means here.

## In scope

**A skill that would make an agent do something unsafe.** These files are
instructions an AI agent follows. A change that weakens a harness's approval
gate, or that instructs an agent to skip a confirmation step, act without
authorization, or exfiltrate context, is the most serious kind of bug this
repository can have — more serious than a code defect.

**A contract that misdescribes a harness's CLI.** `contracts.json` declares each
harness's binary, argv template, parser and prompt delivery. If it names a flag
that does not exist, or a delivery mode that drops the prompt, an agent will
follow it — and the failure is silent, because the agent has no way to tell the
description from reality.

**A generator that can be made to write outside its output.** `build_skills.py`
validates each contracted skill directory name and rejects symlinked generated
output paths before writing files. A bypass of those checks, or a generated file
that escapes the selected repository, is in scope.

**An execution or review control failure.** The MCP bridge and Go clients can
launch or continue harness sessions. Session IDs, prompt delivery, approval
posture, temporary files, and receipts are in scope. The review helper's
filetree filtering, read-only database access, and transcript output boundary
are also in scope.

The MCP bridge uses local stdio and trusts the MCP host that starts it. It has
no per-user authentication. Copilot and OpenHands unattended routes also require
a server-side per-harness allowlist; that allowlist does not replace task-level
approval in the host. Codex's fresh handoff is autonomous, and the MCP host
must enforce the operator's request to dispatch it.

**A leaked secret.** This is a public repository. Credentials, tokens, private
keys, customer data, or machine-specific paths in a tracked file are in scope,
including in history.

## Out of scope

- The behaviour of third-party harness implementations outside the code this
  repository ships.
- An agent misusing a skill that is working as documented. `--open`-style
  conveniences are documented as operator-only for exactly that reason.
- Prompt injection arriving from third-party content an agent fetches while
  using a skill. Report it to the harness that fetched it.
- Anything requiring an already-compromised machine.

## Reporting

Open a private security advisory on the repository. Include the file and line,
the command you ran, and what you observed.

Please do not open a public issue for anything that would let an agent bypass an
approval step — the skill trees are read by agents on other people's machines,
and a public report is a working exploit until the trees are regenerated.

## Response

Expect an acknowledgement within a few days. A skill-level weakening is fixed by
regenerating the trees, so a fix is usually one source edit plus
`python3 scripts/build_skills.py`; a generator defect needs a test with it, since
the rules the generator enforces are the only thing keeping the trees consistent.
