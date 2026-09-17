# Agent instructions — harness-handoff

Portable handoff skills for seven coding-agent harnesses. One authored source,
seven **generated** skill trees.

```text
skills-src/contracts.json          per-harness CLI contract (machine-readable)
skills-src/lane-spawning/<h>.md    the one authoritative lane-spawning block
skills-src/harnesses/<h>.md        the authored remainder of that skill's body
        │
        │  scripts/build_skills.py
        ▼
<harness>-harness-handoff/SKILL.md      GENERATED — never hand-edit
<harness>-harness-handoff/contract.json GENERATED — never hand-edit
<harness>-harness-handoff/references/*  authored prose, verified against the contract
```

## The one rule

**Edit `skills-src/`, then regenerate. Never hand-edit a generated tree.**

Commit `9322d55` pasted the same `## Direct lane spawning` block into every file
five or six times because there was nothing to stop it. The generator exists to
make that impossible, and `--check` is what makes it stick.

```sh
python3 scripts/build_skills.py            # write the trees
python3 scripts/build_skills.py --check    # fail if a tree is stale (exit 1)
python3 -m pytest                          # 22 tests: the generator's rules
```

`--check` compares every generated file byte-for-byte. Run it before committing;
a hand-edit is reverted by the next build and caught by the check.

## What the generator refuses

Each of these is a test in `tests/test_build_skills.py`, not just a convention:

- a lane source with **zero or two or more** `## Direct lane spawning` headings
- the lane block **authored by hand** in `skills-src/harnesses/<h>.md` (it is
  generated; authoring it means the next build deletes your text)
- a contract entry missing any of the required keys — the error names them
- `prompt_delivery: file_flag` with no `prompt_file_flag` (a delivery mode with
  no flag is a contradiction, not a default)
- a declared reference that is missing, or a `.md` file in `references/` that no
  contract declares

A rejection prints one `ERROR  …` line and exits 2. It must never traceback: the
whole point of this script is to tell a contributor which file to fix.

## The shared vocabulary is a contract with another repo

`skills-src/contracts.json` carries `advisory_vocabulary` — the statuses and the
fan-out rule. `work-coordination` implements it, validates `--status` against it,
and has a drift test that reads this file when the checkouts sit side by side.
Changing the status list here changes what every harness may report and breaks
that package's tests. `test_the_shared_vocabulary_is_the_one_work_coordination_fans_out_on`
pins it.

## Layout

| Path | Notes |
| --- | --- |
| `scripts/build_skills.py` | the generator (the only thing that writes trees) |
| `scripts/extract_skill_sources.py` | one-time provenance: how `skills-src/` was derived. **Not** part of the build; re-running it against generated output would strip the lane block |
| `scripts/codex-task-bridge` | helper for the Codex handoff |
| `tests/` | pytest; every fixture works in a temp dir, never in the trees |
| `EVIDENCE.md` | what was verified and how |

## When you finish

Run `--check` and `pytest`, and say what they printed. If you changed a skill's
prose, say which harness trees moved — the generated files are the artifact users
copy, so a source edit that was not regenerated is an incomplete change.
