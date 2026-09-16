#!/usr/bin/env python3
"""One-time migration: derive skills-src/ from the hand-maintained skill trees.

Before this script ran, every ``<harness>-harness-handoff/SKILL.md`` was authored by
hand, and commit 9322d55 ("Require direct CLI lane spawning") pasted the same
``## Direct lane spawning`` block into each file five or six times without
deduplicating. Seven hand-maintained copies with a known paste defect is the whole
reason ``build_skills.py`` exists.

This script is kept in the repository as provenance: it is how ``skills-src/`` was
produced, so the derivation is auditable rather than a claim. It is NOT part of the
build and should not be re-run against generated output — it reads the pre-generator
layout, where the lane block is duplicated. Running it after generation would strip
the single authoritative lane block and produce an empty one.

Layout it expects (pre-generator):

    <harness>-harness-handoff/SKILL.md
      --- frontmatter ---
      # <Title>
      ## Direct lane spawning      <- repeated 5-6x, each with the same paragraph
      <intro or reference-pointer paragraphs>
      ## <first real section>
      ...

It writes:

    skills-src/lane-spawning/<harness>.md   the one authoritative lane block
    skills-src/harnesses/<harness>.md       everything else, deduplicated, in order
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

LANE_HEADING = "## Direct lane spawning"
HARNESS_DIR = re.compile(r"^(?P<harness>[a-z0-9]+)-harness-handoff$")


def split_frontmatter(text: str) -> tuple[str, str]:
    """Return (frontmatter_block_including_fences, remainder)."""
    if not text.startswith("---\n"):
        raise ValueError("SKILL.md does not start with frontmatter")
    end = text.index("\n---\n", 4) + len("\n---\n")
    return text[:end], text[end:]


def paragraphs(text: str) -> list[str]:
    """Split on blank lines, preserving non-blank block content verbatim."""
    return [block for block in re.split(r"\n\s*\n", text.strip("\n")) if block.strip()]


def migrate(skill_dir: Path, source_root: Path) -> tuple[str, int, int]:
    harness = HARNESS_DIR.match(skill_dir.name)
    if harness is None:
        raise ValueError(f"{skill_dir.name} is not a <harness>-harness-handoff directory")
    name = harness.group("harness")

    text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    _, rest = split_frontmatter(text)

    blocks = paragraphs(rest)
    if not blocks or not blocks[0].startswith("# "):
        raise ValueError(f"{skill_dir}/SKILL.md: expected an H1 title as the first block")
        # Validated above; the authored source is re-titled at build time.
    _title_block, *body_blocks = blocks

    lane_indices = [i for i, b in enumerate(body_blocks) if b.strip() == LANE_HEADING]
    if not lane_indices:
        raise ValueError(f"{skill_dir}/SKILL.md: no {LANE_HEADING!r} block found")

    first_lane = lane_indices[0]
    if first_lane + 1 >= len(body_blocks):
        raise ValueError(f"{skill_dir}/SKILL.md: lane heading has no body paragraph")
    lane_para = body_blocks[first_lane + 1].strip()
    if lane_para.startswith("#"):
        raise ValueError(f"{skill_dir}/SKILL.md: lane heading is followed by another heading")

    # Every lane heading, plus every paragraph that merely repeats the lane body,
    # is machine-owned. What survives is the authored remainder, in original order.
    remaining: list[str] = []
    dropped = 0
    for i, block in enumerate(body_blocks):
        if block.strip() == LANE_HEADING:
            dropped += 1
            continue
        if block.strip() == lane_para:
            dropped += 1
            continue
        if i < first_lane:
            # Content authored above the lane block moves below it, where the
            # generator always emits the lane block. Nothing is discarded.
            remaining.append(block)
        else:
            remaining.append(block)

    lane_out = source_root / "lane-spawning" / f"{name}.md"
    lane_out.parent.mkdir(parents=True, exist_ok=True)
    lane_out.write_text(f"{LANE_HEADING}\n\n{lane_para}\n", encoding="utf-8")

    body_out = source_root / "harnesses" / f"{name}.md"
    body_out.parent.mkdir(parents=True, exist_ok=True)
    body_out.write_text("\n\n".join(remaining).rstrip("\n") + "\n", encoding="utf-8")

    return name, dropped, len(remaining)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parent.parent)
    args = parser.parse_args()

    repo = args.repo.resolve()
    source_root = repo / "skills-src"
    skill_dirs = sorted(p for p in repo.glob("*-harness-handoff") if p.is_dir())
    if not skill_dirs:
        parser.error(f"no *-harness-handoff directories under {repo}")

    print(f"repo   {repo}")
    print(f"source {source_root}")
    for skill_dir in skill_dirs:
        name, dropped, kept = migrate(skill_dir, source_root)
        print(f"  {name:12} dropped {dropped:2} duplicate block(s), kept {kept:2} authored block(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
