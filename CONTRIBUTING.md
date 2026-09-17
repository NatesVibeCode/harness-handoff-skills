# Contributing

One authored source, seven generated skill trees. The single rule:

**Edit `skills-src/`, then regenerate. Never hand-edit a generated tree.**

A hand-edit is reverted by the next build and caught by `--check`, so it will not
survive a commit — and if it somehow did, the next contributor's rebuild would
delete the work.

## Setup

Python 3.9 or newer. No runtime dependencies; tests need pytest.

```sh
python3 -m pip install -e ".[dev]"
```

## The loop

```sh
# 1. Edit the source, never the output
$EDITOR skills-src/contracts.json
$EDITOR skills-src/lane-spawning/codex.md
$EDITOR skills-src/harnesses/codex.md

# 2. Regenerate
python3 scripts/build_skills.py

# 3. Prove it is current and the rules hold
python3 scripts/build_skills.py --check   # exit 1 if a tree is stale
python3 -m pytest                         # 22 tests
```

Both commands must pass before a change is finished. `--check` is the gate the
generator exists for: it compares every `SKILL.md` and `contract.json`
byte-for-byte against what the sources produce.

## Where a change belongs

| You want to change | Edit |
| --- | --- |
| A harness's CLI invocation, parser, discovery or one-shot argv | `skills-src/contracts.json` |
| How lanes are spawned (the block every skill must carry identically) | `skills-src/lane-spawning/<harness>.md` |
| The rest of a skill's body | `skills-src/harnesses/<harness>.md` |
| Prose references (history, operating guides) | `<harness>-harness-handoff/references/*.md`, then declare it in `contracts.json` |
| The generator's rules | `scripts/build_skills.py`, with a test |

References are the one authored thing that lives inside a generated tree. They
are checked both ways: a declared reference must exist, and an undeclared `.md`
in `references/` is an error.

## What the generator refuses

All of these are tests, not conventions:

- a lane source with zero, or two or more, `## Direct lane spawning` headings
- the lane block authored by hand in a harness body
- a contract entry missing a required key (the error names the keys)
- `prompt_delivery: file_flag` with no `prompt_file_flag`
- a missing declared reference, or an undeclared file in `references/`

A rejection prints one `ERROR  …` line naming the file that has to change, and
exits 2. If you ever see a traceback instead, that is a bug in the generator —
please report it with the source that triggered it.

## The shared vocabulary

`skills-src/contracts.json` carries `advisory_vocabulary`: the statuses a session
may report and which of them fan out. `work-coordination` implements it and has a
drift test reading this file, so changing the list here changes what every
harness may report and breaks that package. Treat it as a cross-repository
contract, not a local constant.

## Commits and releases

- One concern per commit, and say which harness trees moved. The generated trees
  are the artifact users copy, so a source edit that was not regenerated is an
  incomplete change.
- Do not rewrite published history; `main` is pushed and cloned from.
- Nothing is tagged yet. The version lives in `pyproject.toml`; if you bump it,
  say so in the commit subject.

## Reporting a problem

Include the command you ran and its output. For a generator refusal, the source
file that triggered it is the useful part — the error text alone usually is not
enough to reproduce.
