#!/usr/bin/env python3
"""Generate the fourteen handoff skill trees and the session review skill.

The fourteen handoff trees are generated from their authored source; the standalone
review workflow and helper are also copied into a self-contained generated skill.
Before this existed the handoff trees were hand-maintained copies, and commit 9322d55
pasted the same ``## Direct lane spawning`` block into every file five or six times.
The lane block is now emitted exactly once from its source, and every generated file
is compared byte-for-byte on ``--check``.

Sources (author these)
    skills-src/session-review.md       cross-harness session review workflow
    scripts/session_review.py         authored metadata/health helper
    skills-src/contracts.json          per-harness execution contract, machine-readable
    skills-src/lane-spawning/<h>.md    the one authoritative lane-spawning block
    skills-src/harnesses/<h>.md        the authored remainder of the skill body

Generated (never hand-edit)
    harness-session-review/*           skill, output schema, and helper copy
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
CONTRACT_VERSION = 2
REVIEW_SKILL = "harness-session-review"
REVIEW_SKILL_SOURCE = "session-review.md"
REVIEW_SCHEMA_SOURCE = "session-review-output.schema.json"
REVIEW_SCHEMA_OUTPUT = "review-output.schema.json"
REVIEW_TOOL_SOURCE = "scripts/session_review.py"
REVIEW_TOOL_OUTPUT = "session_review.py"
CONTRACT_KEYS = (
    "binary",
    "prompt_delivery",
    "prompt_file_flag",
    "parser",
    "sdk",
    "model_from_route",
    "discovery_argv",
    "call_workdir",
    "task_config_strategy",
    "oneshot_argv",
    "interactivity",
    "credential_channel",
    "credential_auth",
)

# The approval posture of the pinned oneshot argv.
INTERACTIVITY_VALUES = ("non_interactive", "prompts")
# How the harness reaches its credentials. The pinned argv passes no
# credential values, so these name the onboarding channel, not a secret.
CREDENTIAL_CHANNELS = ("env", "stdin", "file", "keychain", "native-session")
SDK_KINDS = ("library", "protocol", "none")
SDK_STATUSES = ("stable", "preview", "beta")
SDK_LANGUAGES = ("typescript", "python")
FRESH_ROUTES = ("sdk", "sdk-or-cli", "protocol-or-cli", "cli")
CONTINUATION_ROUTES = ("sdk", "sdk-or-cli", "protocol-or-cli", "cli", "forbidden")
HISTORY_ROUTES = ("sdk", "sdk-or-cli", "protocol", "protocol-or-cli", "cli")
SESSION_OWNERSHIP = ("sdk-owned", "native-owned", "mixed")
SESSION_SCOPES = ("sdk-owned-only", "native-existing-only", "either", "none")
SURFACES = ("local", "cloud", "mixed")
EVIDENCE_KEYS = ("docs_checked", "registry_checked", "cli_present", "sdk_smoke_passed")
SDK_CREDENTIAL_VALUES = CREDENTIAL_CHANNELS + (
    "api-key",
    "oauth",
    "service-account",
    "gcp-adc",
    "meta-credential",
    "mixed",
)
SDK_REQUIRED_KEYS = (
    "kind",
    "status",
    "languages",
    "packages",
    "entrypoints",
    "command",
    "repositories",
    "docs",
    "runtimes",
    "session",
    "ownership",
    "surface",
    "fresh",
    "continuation",
    "history",
    "history_scope",
    "continuation_scope",
    "stream",
    "id_namespaces",
    "forbidden_operations",
    "auth_channel",
    "auth",
    "auth_notes",
    "approval_notes",
    "evidence",
)


class SourceError(ValueError):
    """skills-src/ is unusable, naming the file that has to change."""


def _validate_sdk(name: str, sdk: object, contract_path: Path) -> None:
    """Require a complete SDK/protocol binding beside the CLI fallback."""
    prefix = f"{contract_path}: {name} declares an unusable sdk"
    if not isinstance(sdk, dict):
        raise SourceError(f"{prefix}; sdk must be an object")
    missing = [key for key in SDK_REQUIRED_KEYS if key not in sdk]
    if missing:
        raise SourceError(f"{prefix}; sdk is missing {', '.join(missing)}")

    kind = sdk["kind"]
    if kind not in SDK_KINDS:
        raise SourceError(f"{prefix}; kind {kind!r} is not one of {', '.join(SDK_KINDS)}")
    if sdk["status"] not in SDK_STATUSES:
        raise SourceError(
            f"{prefix}; status {sdk['status']!r} is not one of {', '.join(SDK_STATUSES)}"
        )

    languages = sdk["languages"]
    packages = sdk["packages"]
    entrypoints = sdk["entrypoints"]
    command = sdk["command"]
    if not isinstance(languages, list) or any(
        not isinstance(language, str) or language not in SDK_LANGUAGES for language in languages
    ):
        raise SourceError(
            f"{prefix}; languages must be a list containing only {', '.join(SDK_LANGUAGES)}"
        )
    if not isinstance(packages, dict) or not isinstance(entrypoints, dict):
        raise SourceError(f"{prefix}; packages and entrypoints must be objects")
    if kind == "library":
        if not languages:
            raise SourceError(f"{prefix}; a library must name at least one language")
        if set(packages) != set(languages) or set(entrypoints) != set(languages):
            raise SourceError(
                f"{prefix}; packages and entrypoints must each name every language in languages"
            )
        if any(
            not isinstance(value, str) or not value
            for value in (*packages.values(), *entrypoints.values())
        ):
            raise SourceError(f"{prefix}; packages and entrypoints must name non-empty values")
        if command is not None:
            raise SourceError(f"{prefix}; a library must leave command null")
    else:
        if languages or packages or entrypoints:
            raise SourceError(
                f"{prefix}; a {kind} binding must leave languages, packages, and entrypoints empty"
            )
        if kind == "protocol" and (not isinstance(command, str) or not command):
            raise SourceError(f"{prefix}; a protocol binding must name its command")
        if kind == "none" and command is not None:
            raise SourceError(f"{prefix}; a none binding must leave command null")

    repositories = sdk["repositories"]
    docs = sdk["docs"]
    runtimes = sdk["runtimes"]
    if not isinstance(repositories, dict) or not isinstance(runtimes, dict):
        raise SourceError(f"{prefix}; repositories and runtimes must be objects")
    if kind == "library":
        if set(repositories) != set(languages) or set(runtimes) != set(languages):
            raise SourceError(
                f"{prefix}; repositories and runtimes must each name every language in languages"
            )
        if any(
            not isinstance(value, str) or not value.startswith("https://")
            for value in repositories.values()
        ):
            raise SourceError(f"{prefix}; repositories must map languages to https URLs")
        if any(not isinstance(value, str) or not value for value in runtimes.values()):
            raise SourceError(f"{prefix}; runtimes must map languages to non-empty values")
    elif kind == "protocol":
        if repositories or set(runtimes) != {"protocol"}:
            raise SourceError(
                f"{prefix}; a protocol binding must leave repositories empty and name one protocol runtime"
            )
        if not isinstance(runtimes["protocol"], str) or not runtimes["protocol"]:
            raise SourceError(f"{prefix}; the protocol runtime must be a non-empty string")
    elif repositories or runtimes:
        raise SourceError(f"{prefix}; a none binding must leave repositories and runtimes empty")
    if not isinstance(docs, str) or not docs.startswith("https://"):
        raise SourceError(f"{prefix}; docs must be an https URL")
    for key in ("session", "stream", "auth_notes", "approval_notes"):
        if not isinstance(sdk[key], str) or not sdk[key]:
            raise SourceError(f"{prefix}; {key} must be a non-empty string")
    for key, allowed in (
        ("ownership", SESSION_OWNERSHIP),
        ("surface", SURFACES),
        ("history_scope", SESSION_SCOPES),
        ("continuation_scope", SESSION_SCOPES),
    ):
        if sdk[key] not in allowed:
            raise SourceError(
                f"{prefix}; {key} {sdk[key]!r} is not one of {', '.join(allowed)}"
            )
    for key in ("id_namespaces", "forbidden_operations"):
        if not isinstance(sdk[key], list) or any(
            not isinstance(value, str) or not value for value in sdk[key]
        ):
            raise SourceError(f"{prefix}; {key} must be a list of non-empty strings")
    if not sdk["id_namespaces"]:
        raise SourceError(f"{prefix}; id_namespaces must name at least one namespace")
    evidence = sdk["evidence"]
    if not isinstance(evidence, dict) or set(evidence) != set(EVIDENCE_KEYS):
        raise SourceError(
            f"{prefix}; evidence must name exactly {', '.join(EVIDENCE_KEYS)}"
        )
    if any(not isinstance(value, bool) for value in evidence.values()):
        raise SourceError(f"{prefix}; evidence values must be booleans")
    routes = (
        ("fresh", sdk["fresh"], FRESH_ROUTES),
        ("continuation", sdk["continuation"], CONTINUATION_ROUTES),
        ("history", sdk["history"], HISTORY_ROUTES),
    )
    for field, value, allowed in routes:
        if value not in allowed:
            raise SourceError(
                f"{prefix}; {field} {value!r} is not one of {', '.join(allowed)}"
            )
    if sdk["fresh"].startswith("sdk") and kind != "library":
        raise SourceError(f"{prefix}; fresh {sdk['fresh']!r} requires kind 'library'")
    if sdk["continuation"].startswith("sdk") and kind != "library":
        raise SourceError(
            f"{prefix}; continuation {sdk['continuation']!r} requires kind 'library'"
        )
    if sdk["history"].startswith("sdk") and kind != "library":
        raise SourceError(f"{prefix}; history {sdk['history']!r} requires kind 'library'")
    if sdk["fresh"].startswith("protocol") and kind != "protocol":
        raise SourceError(f"{prefix}; fresh {sdk['fresh']!r} requires kind 'protocol'")
    if sdk["continuation"].startswith("protocol") and kind != "protocol":
        raise SourceError(
            f"{prefix}; continuation {sdk['continuation']!r} requires kind 'protocol'"
        )
    if sdk["history"].startswith("protocol") and kind != "protocol":
        raise SourceError(f"{prefix}; history {sdk['history']!r} requires kind 'protocol'")
    if kind == "none" and (
        sdk["fresh"] != "cli"
        or sdk["continuation"] not in ("cli", "forbidden")
        or sdk["history"] != "cli"
    ):
        raise SourceError(f"{prefix}; a none binding must use CLI routes")

    for key in ("auth_channel", "auth"):
        if sdk[key] not in SDK_CREDENTIAL_VALUES:
            raise SourceError(
                f"{prefix}; {key} {sdk[key]!r} is not one of "
                f"{', '.join(SDK_CREDENTIAL_VALUES)}"
            )


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
    if document.get("version") != CONTRACT_VERSION:
        raise SourceError(
            f"{contract_path}: version {document.get('version')!r} is not supported; "
            f"expected {CONTRACT_VERSION}"
        )
    for name, entry in harnesses.items():
        missing = [k for k in CONTRACT_KEYS if k not in entry]
        if missing:
            raise SourceError(f"{contract_path}: {name} is missing {', '.join(missing)}")
        _validate_skill_path(name, entry, contract_path)
        _validate_sdk(name, entry["sdk"], contract_path)
        if entry["prompt_delivery"] == "file_flag" and not entry.get("prompt_file_flag"):
            raise SourceError(
                f"{contract_path}: {name} uses prompt_delivery=file_flag "
                "but declares no prompt_file_flag"
            )
        argv = entry["oneshot_argv"]
        if not isinstance(argv, list) or not argv or any(not isinstance(token, str) or not token for token in argv):
            raise SourceError(f"{contract_path}: {name} oneshot_argv must be a non-empty list of strings")
        if any("<workdir>" in token for token in argv) and not entry["call_workdir"]:
            raise SourceError(f"{contract_path}: {name} uses <workdir> without call_workdir")
        if entry["interactivity"] not in INTERACTIVITY_VALUES:
            raise SourceError(
                f"{contract_path}: {name} declares interactivity "
                f"{entry['interactivity']!r}; expected one of "
                f"{', '.join(INTERACTIVITY_VALUES)}"
            )
        for key in ("credential_channel", "credential_auth"):
            if entry[key] not in CREDENTIAL_CHANNELS:
                raise SourceError(
                    f"{contract_path}: {name} declares {key} {entry[key]!r}; "
                    f"expected one of {', '.join(CREDENTIAL_CHANNELS)}"
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
    if "bundled_files" in entry:
        payload["bundled_files"] = entry["bundled_files"]
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


def load_review_skill_sources(source_root: Path) -> tuple[str, str, str]:
    """Load the independently scoped session-review skill and its output contract."""
    skill_path = source_root / REVIEW_SKILL_SOURCE
    schema_path = source_root / REVIEW_SCHEMA_SOURCE
    tool_path = source_root.parent / REVIEW_TOOL_SOURCE
    if not skill_path.is_file():
        raise SourceError(f"missing source {skill_path.relative_to(source_root.parent)}")
    if not schema_path.is_file():
        raise SourceError(f"missing source {schema_path.relative_to(source_root.parent)}")
    if not tool_path.is_file():
        raise SourceError(f"missing source {tool_path.relative_to(source_root.parent)}")
    skill = skill_path.read_text(encoding="utf-8")
    if not skill.startswith(f"---\nname: {REVIEW_SKILL}\n"):
        raise SourceError(f"{skill_path.relative_to(source_root.parent)} must declare name: {REVIEW_SKILL} in frontmatter")
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SourceError(f"{schema_path.relative_to(source_root.parent)} is not valid JSON: {exc.msg}") from exc
    if not isinstance(schema, dict):
        raise SourceError(f"{schema_path.relative_to(source_root.parent)} must contain a JSON object")
    required = schema.get("required")
    if schema.get("type") != "object" or not isinstance(required, list) or not required:
        raise SourceError(f"{schema_path.relative_to(source_root.parent)} must define an object schema with required fields")
    return skill, json.dumps(schema, indent=2) + "\n", tool_path.read_text(encoding="utf-8")


def unsafe_output_reason(repo: Path, target: Path) -> str | None:
    """Reject symlinked output paths before reading or writing generated files."""
    if target.parent.is_symlink() or target.is_symlink():
        return f"{target.relative_to(repo)} is a symlinked generated output path"
    if target.parent.exists() and not target.parent.is_dir():
        return f"{target.parent.relative_to(repo)} is not a directory"
    try:
        target.resolve().relative_to(repo)
    except (ValueError, OSError, RuntimeError):
        return f"{target.relative_to(repo)} resolves outside the repository"
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--check", action="store_true", help="report drift, write nothing")
    args = parser.parse_args()

    repo = args.repo.resolve()
    source_root = repo / "skills-src"
    try:
        document, harnesses = load_sources(source_root)
        review_skill_text, review_schema_text, review_tool_text = load_review_skill_sources(source_root)
    except SourceError as exc:
        print(f"ERROR  {exc}")
        return 2

    problems: list[str] = []
    stale: list[str] = []
    written = 0
    bundles = {}
    for name, entry in harnesses.items():
        bundles[name] = []
        mapping = entry.get("bundled_files", {})
        if not isinstance(mapping, dict):
            problems.append(f"{name}: bundled_files must be an object")
            continue
        for filename, source in mapping.items():
            if (not isinstance(filename, str) or Path(filename).name != filename
                    or filename in {"SKILL.md", "contract.json"} or not isinstance(source, str)):
                problems.append(f"{name}: invalid bundled file mapping")
                continue
            source_path = repo / source
            try:
                source_path.resolve().relative_to(repo)
                bundles[name].append((filename, source_path.read_text(encoding="utf-8")))
            except (ValueError, OSError) as exc:
                problems.append(f"{name}: cannot read bundled source {source}: {exc}")

    for name, entry in harnesses.items():
        for filename in ("SKILL.md", "contract.json", *(row[0] for row in bundles[name])):
            reason = unsafe_output_reason(repo, repo / entry["skill"] / filename)
            if reason:
                problems.append(reason)
    for filename in ("SKILL.md", REVIEW_SCHEMA_OUTPUT, REVIEW_TOOL_OUTPUT):
        reason = unsafe_output_reason(repo, repo / REVIEW_SKILL / filename)
        if reason:
            problems.append(reason)
    if problems:
        for problem in problems:
            print(f"ERROR  {problem}")
        return 2

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

        for filename, expected in (("SKILL.md", skill_text), ("contract.json", contract_text), *bundles[name]):
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

    review_dir = repo / REVIEW_SKILL
    review_artifacts = (
        ("SKILL.md", review_skill_text),
        (REVIEW_SCHEMA_OUTPUT, review_schema_text),
        (REVIEW_TOOL_OUTPUT, review_tool_text),
    )
    for filename, expected in review_artifacts:
        target = review_dir / filename
        current = target.read_text(encoding="utf-8") if target.is_file() else None
        if current == expected:
            continue
        if args.check:
            stale.append(f"{REVIEW_SKILL}/{filename}")
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
        print(f"OK     {len(harnesses)} handoff skill trees + 1 review skill match skills-src/")
        return 0

    print(f"OK     wrote {written} file(s) across {len(harnesses)} handoff skill trees + 1 review skill")
    return 0


if __name__ == "__main__":
    sys.exit(main())
