#!/usr/bin/env python3
"""Generate the seven handoff skill trees from skills-src/.

One authored source, seven generated trees. Before this existed the trees were
hand-maintained copies, and commit 9322d55 pasted the same ``## Direct lane spawning``
block into every file five or six times because nothing stopped it. The lane block is
now emitted exactly once, from ``skills-src/lane-spawning/<harness>.md``, and every
generated file is compared byte-for-byte on ``--check``.

Sources (author these)
    skills-src/contracts.json          per-harness CLI contract, machine-readable
    skills-src/lane-spawning/<h>.md    the one authoritative lane-spawning block
    skills-src/harnesses/<h>.md        the authored remainder of the skill body

Generated (never hand-edit)
    <skill>/SKILL.md                   frontmatter + title + lane block + body
    <skill>/contract.json              this harness's contract, for tooling

References stay authored: ``<skill>/references/*.md`` are prose, not duplicated across
harnesses, and this script only verifies that they match ``contracts.json``.

Usage
    python3 scripts/build_skills.py            # write
    python3 scripts/build_skills.py --check    # fail if checked-in output is stale
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

CONTRACT_FILE = "contracts.json"
LANE_HEADING = "## Direct lane spawning"
CONTRACT_KEYS = (
    "binary",
    "prompt_delivery",
    "prompt_file_flag",
    "parser",
    "model_from_route",
    "discovery_argv",
    "call_workdir",
    "task_config_strategy",
    "oneshot_argv",
)


class SourceError(ValueError):
    """skills-src/ is unusable, naming the file that has to change."""


def _validate_skill_path(name: str, entry: dict, contract_path: Path) -> None:
    """`skill` becomes an output directory, so it must be a plain name inside the repo.

    Nothing checked this. A contract entry of ``"skill": "../../../ESCAPED"`` — which
    an agent editing contracts.json could write without meaning any harm — made the
    generator create ``SKILL.md`` and ``contract.json`` above the repository root.
    The value is refused rather than sanitised: silently rewriting it would put a
    tree somewhere its author did not name.
    """
    skill = entry.get("skill")
    if not isinstance(skill, str) or not skill:
        raise SourceError(f"{contract_path}: {name} has no 'skill' directory name")
    if skill in {".", ".."} or "/" in skill or "\\" in skill or Path(skill).is_absolute():
        raise SourceError(
            f"{contract_path}: {name} declares skill {skill!r}, which is not a plain "
            "directory name inside the repository"
        )


def load_sources(source_root: Path) -> tuple[dict, dict[str, dict]]:
    contract_path = source_root / CONTRACT_FILE
    if not contract_path.is_file():
        raise SourceError(f"missing {contract_path}")
    document = json.loads(contract_path.read_text(encoding="utf-8"))
    harnesses = document.get("harnesses")
    if not isinstance(harnesses, dict) or not harnesses:
        raise SourceError(f"{contract_path}: 'harnesses' must be a non-empty object")
    for name, entry in harnesses.items():
        missing = [k for k in CONTRACT_KEYS if k not in entry]
        if missing:
            raise SourceError(f"{contract_path}: {name} is missing {', '.join(missing)}")
        _validate_skill_path(name, entry, contract_path)
        if entry["prompt_delivery"] == "file_flag" and not entry.get("prompt_file_flag"):
            raise SourceError(
                f"{contract_path}: {name} uses prompt_delivery=file_flag "
                "but declares no prompt_file_flag"
            )
    return document, harnesses


def render_skill(name: str, entry: dict, lane_block: str, body: str) -> str:
    lane = lane_block.strip("\n")
    if not lane.startswith(LANE_HEADING):
        raise SourceError(f"skills-src/lane-spawning/{name}.md must start with {LANE_HEADING!r}")
    if lane.count(LANE_HEADING) != 1:
        raise SourceError(
            f"skills-src/lane-spawning/{name}.md contains {lane.count(LANE_HEADING)} "
            f"copies of {LANE_HEADING!r}; exactly one is required"
        )
    if LANE_HEADING in body:
        raise SourceError(
            f"skills-src/harnesses/{name}.md contains {LANE_HEADING!r}; "
            "the lane block is generated and must not be authored by hand"
        )
    frontmatter = f"---\nname: {entry['skill']}\ndescription: {entry['description']}\n---\n"
    return f"{frontmatter}\n# {entry['title']}\n\n{lane}\n\n{body.strip()}\n"


def render_contract(name: str, entry: dict, source_document: dict) -> str:
    payload = {
        "version": source_document.get("version", 1),
        "harness": name,
        "skill": entry["skill"],
        "generated_by": "scripts/build_skills.py",
        "generated_from": "skills-src/contracts.json",
        **{key: entry[key] for key in CONTRACT_KEYS},
        "references": list(entry.get("references", [])),
        "advisory_vocabulary": source_document.get("advisory_vocabulary", {}),
    }
    if "adapter" in entry:
        payload["adapter"] = entry["adapter"]
    return json.dumps(payload, indent=2) + "\n"


def check_references(skill_dir: Path, entry: dict, name: str) -> list[str]:
    """Every declared reference must exist; no undeclared .md may sit in references/."""
    problems: list[str] = []
    declared = set(entry.get("references", []))
    references_dir = skill_dir / "references"
    present = (
        {f"references/{p.name}" for p in sorted(references_dir.glob("*.md"))}
        if references_dir.is_dir()
        else set()
    )
    for relative in sorted(declared - present):
        problems.append(f"{skill_dir.name}: declared but missing: {relative}")
    for relative in sorted(present - declared):
        problems.append(
            f"{skill_dir.name}: present but undeclared: {relative} "
            f"(add it to {CONTRACT_FILE})"
        )
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--check", action="store_true", help="report drift, write nothing")
    args = parser.parse_args()

    repo = args.repo.resolve()
    source_root = repo / "skills-src"
    try:
        document, harnesses = load_sources(source_root)
    except SourceError as exc:
        print(f"ERROR  {exc}")
        return 2

    problems: list[str] = []
    stale: list[str] = []
    written = 0

    for name, entry in sorted(harnesses.items()):
        skill_dir = repo / entry["skill"]
        lane_path = source_root / "lane-spawning" / f"{name}.md"
        body_path = source_root / "harnesses" / f"{name}.md"
        absent = [path for path in (lane_path, body_path) if not path.is_file()]
        for path in absent:
            problems.append(f"missing source {path.relative_to(repo)}")
        # This harness only, not the accumulating `problems` list: skip the
        # harness whose own source is missing, and keep examining the rest.
        if absent:
            continue

        try:
            skill_text = render_skill(
                name,
                entry,
                lane_path.read_text(encoding="utf-8"),
                body_path.read_text(encoding="utf-8"),
            )
        except SourceError as exc:
            # Rejecting bad authorship is this script's job, so it reports one
            # line and moves on. It used to raise: a duplicated lane block, a
            # missing heading, or a hand-written block in the body produced a
            # traceback instead of the file that has to change.
            problems.append(str(exc))
            continue
        contract_text = render_contract(name, entry, document)
        problems.extend(check_references(skill_dir, entry, name))

        for filename, expected in (("SKILL.md", skill_text), ("contract.json", contract_text)):
            target = skill_dir / filename
            current = target.read_text(encoding="utf-8") if target.is_file() else None
            if current == expected:
                continue
            if args.check:
                stale.append(f"{entry['skill']}/{filename}")
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(expected, encoding="utf-8")
                written += 1

    for problem in problems:
        print(f"ERROR  {problem}")
    if problems:
        return 2

    if args.check:
        if stale:
            print(f"STALE  {len(stale)} generated file(s) differ from skills-src/:")
            for item in stale:
                print(f"  {item}")
            print("Run: python3 scripts/build_skills.py")
            return 1
        print(f"OK     {len(harnesses)} skill trees match skills-src/")
        return 0

    print(f"OK     wrote {written} file(s) across {len(harnesses)} skill trees")
    return 0


if __name__ == "__main__":
    sys.exit(main())
