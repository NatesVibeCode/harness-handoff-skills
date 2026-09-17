# Security policy

## What this repository is

A generator and seven skill trees. It ships **markdown and JSON** that an agent
harness reads as instructions, plus three Python scripts. There is no network
code, no service, no runtime dependency, and nothing that executes on behalf of a
user.

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
writes `<skill>/SKILL.md` and `<skill>/contract.json` under the paths named in
`contracts.json`. A contract whose `skill` value escapes the repository (an
absolute path, `..`) would be a path-traversal bug. The current code does not
validate that, and a report showing it writing outside the repo root is welcome.

**A leaked secret.** This is a public repository. Credentials, tokens, private
keys, customer data, or machine-specific paths in a tracked file are in scope,
including in history.

## Out of scope

- The behaviour of the harnesses themselves. This repository describes them; it
  does not control them.
- An agent misusing a skill that is working as documented. `--open`-style
  conveniences are documented as operator-only for exactly that reason.
- Prompt injection arriving from third-party content an agent fetches while
  using a skill. Report it to the harness that fetched it.
- Anything requiring an already-compromised machine.

## Reporting

Open a private security advisory on the repository, or email the address in
`LICENSE`. Include the file and line, the command you ran, and what you observed.

Please do not open a public issue for anything that would let an agent bypass an
approval step — the skill trees are read by agents on other people's machines,
and a public report is a working exploit until the trees are regenerated.

## Response

Expect an acknowledgement within a few days. A skill-level weakening is fixed by
regenerating the trees, so a fix is usually one source edit plus
`python3 scripts/build_skills.py`; a generator defect needs a test with it, since
the rules the generator enforces are the only thing keeping the trees consistent.
