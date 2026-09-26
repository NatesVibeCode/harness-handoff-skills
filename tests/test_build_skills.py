"""The generator for fourteen handoff trees and one standalone review skill.

Before it existed the trees were hand-maintained copies, and commit 9322d55 pasted
the same ``## Direct lane spawning`` block into every file five or six times
because nothing stopped it. These tests pin the properties that prevent a repeat:
one authoritative lane block, byte-exact regeneration, and a ``--check`` that
actually fails on drift rather than reporting success.

Every test works in a temporary clone of the repository's *source* layout. The
checked-in trees are never written to, so a failing assertion cannot leave the
working tree dirty.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
BUILD = REPO / "scripts" / "build_skills.py"
LANE_HEADING = "## Direct lane spawning"

sys.path.insert(0, str(REPO / "scripts"))
import build_skills  # noqa: E402  (the module under test, by path)

CONTRACT_KEYS = list(build_skills.CONTRACT_KEYS)


def _sdk(**overrides):
    sdk = {
        "kind": "library",
        "status": "stable",
        "languages": ["python"],
        "packages": {"python": "demo-sdk"},
        "entrypoints": {"python": "DemoClient"},
        "command": None,
        "repositories": {"python": "https://example.com/demo-sdk"},
        "docs": "https://example.com/docs/sdk",
        "runtimes": {"python": "python>=3.10"},
        "session": "demo-session",
        "ownership": "sdk-owned",
        "surface": "local",
        "fresh": "sdk-or-cli",
        "continuation": "sdk-or-cli",
        "history": "sdk",
        "history_scope": "either",
        "continuation_scope": "either",
        "stream": "sdk-events",
        "id_namespaces": ["demo-session"],
        "forbidden_operations": ["demo-forbidden-route"],
        "auth_channel": "api-key",
        "auth": "api-key",
        "auth_notes": "Use the provisioned demo API key; never log it.",
        "approval_notes": "Pass explicit approval options on every SDK call.",
        "evidence": {
            "docs_checked": True,
            "registry_checked": True,
            "cli_present": True,
            "sdk_smoke_passed": False,
        },
    }
    sdk.update(overrides)
    return sdk


def _entry(**overrides):
    entry = {
        "skill": "demo-harness-handoff",
        "description": "Hand work to the demo harness.",
        "title": "Demo handoff",
        "binary": "demo",
        "prompt_delivery": "argv",
        "prompt_file_flag": None,
        "parser": "plain",
        "sdk": _sdk(),
        "model_from_route": False,
        "discovery_argv": ["demo", "--version"],
        "call_workdir": False,
        "task_config_strategy": "none",
        "oneshot_argv": ["demo", "-p", "{prompt}"],
        "interactivity": "prompts",
        "credential_channel": "native-session",
        "credential_auth": "native-session",
        "references": [],
    }
    entry.update(overrides)
    return entry


def scratch_repo(tmp_path: Path, harnesses: dict, *, lane=None, body=None, write_references=True) -> Path:
    """A minimal repo with only the sources the generator reads.

    ``write_references=False`` declares each reference without creating it, which
    is how the "declared but missing" path gets exercised — the first version of
    this fixture helpfully created the file the test was asserting was absent.
    """
    root = tmp_path / "work" / "repo"
    source = root / "skills-src"
    (source / "lane-spawning").mkdir(parents=True)
    (source / "harnesses").mkdir(parents=True)
    (source / "session-review.md").write_text(
        "---\nname: harness-session-review\ndescription: Review sessions.\n---\n\nReview them.\n",
        encoding="utf-8",
    )
    (source / "session-review-output.schema.json").write_text(
        json.dumps({"type": "object", "required": ["schema_version"]}), encoding="utf-8"
    )
    (root / "scripts").mkdir(parents=True, exist_ok=True)
    (root / "scripts" / "session_review.py").write_text("#!/usr/bin/env python3\n# review helper\n", encoding="utf-8")
    document = {"version": build_skills.CONTRACT_VERSION, "harnesses": harnesses, "advisory_vocabulary": {"status": ["done"]}}
    (source / "contracts.json").write_text(json.dumps(document, indent=2), encoding="utf-8")
    for name, entry in harnesses.items():
        (source / "lane-spawning" / f"{name}.md").write_text(
            lane if lane is not None else f"{LANE_HEADING}\n\nSpawn {name} directly.\n",
            encoding="utf-8",
        )
        (source / "harnesses" / f"{name}.md").write_text(
            body if body is not None else "## Operating notes\n\nBody text.\n",
            encoding="utf-8",
        )
        # A skill value the generator refuses must not make the *fixture* fail
        # first: `/absolute/tree` would send mkdir outside the temp dir.
        skill = entry["skill"]
        usable = (
            isinstance(skill, str)
            and skill
            and skill not in {".", ".."}
            and "/" not in skill
            and "\\" not in skill
            and not Path(skill).is_absolute()
        )
        skill_dir = root / skill
        if usable:
            skill_dir.mkdir(parents=True, exist_ok=True)
        references = skill_dir / "references"
        if entry["references"] and write_references:
            references.mkdir(exist_ok=True)
            for relative in entry["references"]:
                (skill_dir / relative).write_text("reference prose\n", encoding="utf-8")
    return root


def run_build(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(BUILD), "--repo", str(root), *args],
        capture_output=True,
        text=True,
    )


# --- the source contract -----------------------------------------------------


def test_missing_contracts_file_names_itself(tmp_path):
    (tmp_path / "repo" / "skills-src").mkdir(parents=True)
    result = run_build(tmp_path / "repo", "--check")
    assert result.returncode == 2
    assert "contracts.json" in result.stdout


def test_harnesses_must_be_a_non_empty_object(tmp_path):
    root = tmp_path / "repo"
    (root / "skills-src").mkdir(parents=True)
    (root / "skills-src" / "contracts.json").write_text('{"harnesses": {}}', encoding="utf-8")
    result = run_build(root, "--check")
    assert result.returncode == 2
    assert "non-empty object" in result.stdout


def test_every_missing_contract_key_is_named(tmp_path):
    entry = _entry()
    del entry["parser"]
    del entry["oneshot_argv"]
    root = scratch_repo(tmp_path, {"demo": entry})
    result = run_build(root, "--check")
    assert result.returncode == 2
    assert "parser" in result.stdout and "oneshot_argv" in result.stdout, (
        "the error must name the keys to add, not just say a key is missing"
    )


@pytest.mark.parametrize("key", ["interactivity", "credential_channel", "credential_auth"])
def test_every_missing_onboarding_key_is_named(tmp_path, key):
    """The F1 handoff vocabulary: admission reads these; a contract without them is incomplete."""
    entry = _entry()
    del entry[key]
    root = scratch_repo(tmp_path, {"demo": entry})
    result = run_build(root, "--check")
    assert result.returncode == 2
    assert key in result.stdout, "the error must name the key to add"


@pytest.mark.parametrize("value", ["sometimes", "", "PROMPTS"])
def test_an_unknown_interactivity_value_is_refused(tmp_path, value):
    root = scratch_repo(tmp_path, {"demo": _entry(interactivity=value)})
    result = run_build(root, "--check")
    assert result.returncode == 2
    assert "interactivity" in result.stdout and "non_interactive" in result.stdout


@pytest.mark.parametrize("value", ["telepathy", "", "env "])
@pytest.mark.parametrize("key", ["credential_channel", "credential_auth"])
def test_an_unknown_credential_channel_value_is_refused(tmp_path, key, value):
    root = scratch_repo(tmp_path, {"demo": _entry(**{key: value})})
    result = run_build(root, "--check")
    assert result.returncode == 2
    assert key in result.stdout and "native-session" in result.stdout


def test_file_flag_delivery_without_a_flag_is_refused(tmp_path):
    """The contradiction the check exists for: a delivery mode with no flag."""
    root = scratch_repo(
        tmp_path,
        {"demo": _entry(prompt_delivery="file_flag", prompt_file_flag=None)},
    )
    result = run_build(root, "--check")
    assert result.returncode == 2
    assert "prompt_file_flag" in result.stdout


def test_workdir_placeholder_requires_staging_directory(tmp_path):
    root = scratch_repo(tmp_path, {"demo": _entry(oneshot_argv=["--output", "<workdir>/final.md"], call_workdir=False)})
    result = run_build(root, "--check")
    assert result.returncode == 2
    assert "<workdir>" in result.stdout and "call_workdir" in result.stdout


def test_a_missing_sdk_binding_is_named(tmp_path):
    entry = _entry()
    del entry["sdk"]
    root = scratch_repo(tmp_path, {"demo": entry})
    result = run_build(root, "--check")
    assert result.returncode == 2
    assert "sdk" in result.stdout


@pytest.mark.parametrize("field", ["kind", "status", "docs", "fresh", "continuation", "history"])
def test_an_invalid_sdk_route_value_is_refused(tmp_path, field):
    root = scratch_repo(tmp_path, {"demo": _entry(sdk=_sdk(**{field: "nonsense"}))})
    result = run_build(root, "--check")
    assert result.returncode == 2
    assert field in result.stdout


def test_a_library_must_name_matching_packages_and_entrypoints(tmp_path):
    root = scratch_repo(
        tmp_path,
        {"demo": _entry(sdk=_sdk(entrypoints={}))},
    )
    result = run_build(root, "--check")
    assert result.returncode == 2
    assert "packages and entrypoints" in result.stdout


def test_a_protocol_binding_must_name_its_command(tmp_path):
    sdk = _sdk(
        kind="protocol",
        languages=[],
        packages={},
        entrypoints={},
        command=None,
        repositories={},
        runtimes={},
        fresh="protocol-or-cli",
        continuation="protocol-or-cli",
        history="protocol",
        history_scope="native-existing-only",
        continuation_scope="native-existing-only",
        stream="protocol-events",
    )
    root = scratch_repo(tmp_path, {"demo": _entry(sdk=sdk)})
    result = run_build(root, "--check")
    assert result.returncode == 2
    assert "command" in result.stdout


def test_a_valid_protocol_binding_generates(tmp_path):
    sdk = _sdk(
        kind="protocol",
        languages=[],
        packages={},
        entrypoints={},
        command="demo agent stdio",
        repositories={},
        runtimes={"protocol": "json-rpc-stdio-client"},
        fresh="protocol-or-cli",
        continuation="protocol-or-cli",
        history="protocol",
        history_scope="native-existing-only",
        continuation_scope="native-existing-only",
        stream="protocol-events",
    )
    root = scratch_repo(tmp_path, {"demo": _entry(sdk=sdk)})
    assert run_build(root).returncode == 0
    payload = json.loads(
        (root / "demo-harness-handoff" / "contract.json").read_text(encoding="utf-8")
    )
    assert payload["sdk"]["command"] == "demo agent stdio"


def test_an_unsupported_contract_version_is_refused(tmp_path):
    root = scratch_repo(tmp_path, {"demo": _entry()})
    document_path = root / "skills-src" / "contracts.json"
    document = json.loads(document_path.read_text(encoding="utf-8"))
    document["version"] = build_skills.CONTRACT_VERSION + 1
    document_path.write_text(json.dumps(document, indent=2), encoding="utf-8")
    result = run_build(root, "--check")
    assert result.returncode == 2
    assert "version" in result.stdout


def test_a_skill_path_that_escapes_the_repository_is_refused(tmp_path):
    """`skill` becomes an output directory, so it must stay inside the repo.

    Nothing checked this: a contract entry of `"skill": "../../../ESCAPED"` made
    the generator create SKILL.md and contract.json above the repository root. An
    agent editing contracts.json could write it without meaning any harm.
    """
    root = scratch_repo(tmp_path, {"demo": _entry(skill="../../ESCAPED")})
    result = run_build(root)
    assert result.returncode == 2
    assert "plain" in result.stdout and "directory name" in result.stdout
    assert not (tmp_path / "work" / "ESCAPED").exists(), "nothing above the repo"
    assert not (tmp_path / "ESCAPED").exists(), "and nothing above that either"


def test_symlinked_generated_directory_cannot_redirect_writes(tmp_path):
    root = scratch_repo(tmp_path, {"demo": _entry()})
    outside = tmp_path / "outside"
    outside.mkdir()
    skill_dir = root / "demo-harness-handoff"
    skill_dir.rmdir()
    skill_dir.symlink_to(outside, target_is_directory=True)
    result = run_build(root)
    assert result.returncode == 2
    assert "symlinked generated output path" in result.stdout
    assert not (outside / "SKILL.md").exists()


@pytest.mark.parametrize("skill", ["/absolute/tree", "a/b", "..", ".", ""])
def test_other_unusable_skill_values_are_refused(tmp_path, skill):
    root = scratch_repo(tmp_path, {"demo": _entry(skill=skill)})
    result = run_build(root)
    assert result.returncode == 2, f"{skill!r} must be refused"
    assert "ERROR" in result.stdout


# --- the lane block: one source, one copy -----------------------------------


def test_the_generated_skill_carries_exactly_one_lane_block(tmp_path):
    """The original defect, stated as a test: the block was pasted 5-6 times."""
    root = scratch_repo(tmp_path, {"demo": _entry()})
    assert run_build(root).returncode == 0
    skill = (root / "demo-harness-handoff" / "SKILL.md").read_text(encoding="utf-8")
    assert skill.count(LANE_HEADING) == 1


def test_a_lane_source_with_two_copies_is_refused(tmp_path):
    root = scratch_repo(
        tmp_path,
        {"demo": _entry()},
        lane=f"{LANE_HEADING}\n\nFirst copy.\n\n{LANE_HEADING}\n\nSecond copy.\n",
    )
    result = run_build(root, "--check")
    assert result.returncode == 2
    assert "2 copies" in result.stdout


def test_a_lane_source_without_the_heading_is_refused(tmp_path):
    root = scratch_repo(tmp_path, {"demo": _entry()}, lane="Just a paragraph.\n")
    result = run_build(root, "--check")
    assert result.returncode == 2
    assert LANE_HEADING in result.stdout


def test_authoring_the_lane_block_in_the_body_is_refused(tmp_path):
    """The body is the authored remainder; the lane block is generated."""
    root = scratch_repo(
        tmp_path,
        {"demo": _entry()},
        body=f"## Notes\n\n{LANE_HEADING}\n\nSpawn it here too.\n",
    )
    result = run_build(root, "--check")
    assert result.returncode == 2
    assert "must not be authored by hand" in result.stdout


def test_a_missing_source_file_is_named(tmp_path):
    root = scratch_repo(tmp_path, {"demo": _entry()})
    (root / "skills-src" / "harnesses" / "demo.md").unlink()
    result = run_build(root, "--check")
    assert result.returncode == 2
    assert "missing source" in result.stdout


# --- rendering ---------------------------------------------------------------


def test_the_skill_is_frontmatter_title_lane_then_body(tmp_path):
    root = scratch_repo(tmp_path, {"demo": _entry()})
    assert run_build(root).returncode == 0
    skill = (root / "demo-harness-handoff" / "SKILL.md").read_text(encoding="utf-8")
    assert skill.startswith("---\nname: demo-harness-handoff\ndescription: Hand work to the demo harness.\n---\n")
    assert re.search(r"---\n\n# Demo handoff\n\n## Direct lane spawning", skill), (
        "title sits between frontmatter and the lane block"
    )
    assert skill.index(LANE_HEADING) < skill.index("## Operating notes")
    assert skill.endswith("Body text.\n")


def test_regenerating_writes_nothing_and_check_is_clean(tmp_path):
    """Byte-exact on a second pass: the trees are derived, so they are stable."""
    root = scratch_repo(tmp_path, {"demo": _entry()})
    first = run_build(root)
    assert first.returncode == 0 and "wrote 5 file(s)" in first.stdout

    skill_before = (root / "demo-harness-handoff" / "SKILL.md").read_text(encoding="utf-8")
    second = run_build(root)
    assert second.returncode == 0 and "wrote 0 file(s)" in second.stdout
    assert (root / "demo-harness-handoff" / "SKILL.md").read_text(encoding="utf-8") == skill_before

    checked = run_build(root, "--check")
    assert checked.returncode == 0
    assert "match skills-src/" in checked.stdout


def test_the_review_skill_and_schema_are_generated_from_their_sources(tmp_path):
    root = scratch_repo(tmp_path, {"demo": _entry()})
    built = run_build(root)
    assert built.returncode == 0
    output = root / "harness-session-review"
    assert (output / "SKILL.md").read_text(encoding="utf-8").startswith("---\nname: harness-session-review\n")
    assert json.loads((output / "review-output.schema.json").read_text(encoding="utf-8"))["required"] == ["schema_version"]
    assert (output / "session_review.py").read_text(encoding="utf-8") == (root / "scripts" / "session_review.py").read_text(encoding="utf-8")
    (root / "skills-src" / "session-review.md").write_text(
        "---\nname: harness-session-review\ndescription: Review sessions.\n---\n\nChanged prose.\n",
        encoding="utf-8",
    )
    checked = run_build(root, "--check")
    assert checked.returncode == 1
    assert "harness-session-review/SKILL.md" in checked.stdout

    (root / "harness-session-review" / "session_review.py").write_text("operator edit\n", encoding="utf-8")
    checked = run_build(root, "--check")
    assert checked.returncode == 1
    assert "harness-session-review/session_review.py" in checked.stdout


def test_check_reports_drift_without_writing(tmp_path):
    """--check is the gate: it must fail, name the file, and change nothing."""
    root = scratch_repo(tmp_path, {"demo": _entry()})
    run_build(root)
    stale_path = root / "demo-harness-handoff" / "SKILL.md"
    stale_path.write_text("hand-edited, wrong\n", encoding="utf-8")

    result = run_build(root, "--check")
    assert result.returncode == 1
    assert "STALE" in result.stdout
    assert "demo-harness-handoff/SKILL.md" in result.stdout
    assert "build_skills.py" in result.stdout, "it must say how to fix it"
    assert stale_path.read_text(encoding="utf-8") == "hand-edited, wrong\n", (
        "--check must not write"
    )


def test_a_missing_generated_file_counts_as_drift(tmp_path):
    root = scratch_repo(tmp_path, {"demo": _entry()})
    run_build(root)
    (root / "demo-harness-handoff" / "contract.json").unlink()
    result = run_build(root, "--check")
    assert result.returncode == 1
    assert "contract.json" in result.stdout


def test_generation_creates_a_directory_that_does_not_exist_yet(tmp_path):
    root = scratch_repo(tmp_path, {"demo": _entry()})
    shutil.rmtree(root / "demo-harness-handoff")
    assert run_build(root).returncode == 0
    assert (root / "demo-harness-handoff" / "SKILL.md").is_file()


# --- generated contracts -----------------------------------------------------


def test_the_contract_carries_every_declared_key_and_its_provenance(tmp_path):
    entry = _entry(adapter="demo-adapter")
    root = scratch_repo(tmp_path, {"demo": entry})
    assert run_build(root).returncode == 0
    payload = json.loads((root / "demo-harness-handoff" / "contract.json").read_text(encoding="utf-8"))

    assert payload["harness"] == "demo"
    assert payload["skill"] == "demo-harness-handoff"
    assert payload["generated_by"] == "scripts/build_skills.py"
    assert payload["generated_from"] == "skills-src/contracts.json"
    assert payload["adapter"] == "demo-adapter"
    for key in CONTRACT_KEYS:
        assert key in payload, f"contract.json dropped {key}"
    assert payload["advisory_vocabulary"] == {"status": ["done"]}


def test_the_contract_carries_the_onboarding_vocabulary(tmp_path):
    root = scratch_repo(tmp_path, {"demo": _entry(interactivity="non_interactive", credential_channel="env", credential_auth="keychain")})
    assert run_build(root).returncode == 0
    payload = json.loads((root / "demo-harness-handoff" / "contract.json").read_text(encoding="utf-8"))
    assert payload["interactivity"] == "non_interactive"
    assert payload["credential_channel"] == "env"
    assert payload["credential_auth"] == "keychain"


def test_an_adapter_key_is_optional(tmp_path):
    root = scratch_repo(tmp_path, {"demo": _entry()})
    assert run_build(root).returncode == 0
    payload = json.loads((root / "demo-harness-handoff" / "contract.json").read_text(encoding="utf-8"))
    assert "adapter" not in payload


# --- references --------------------------------------------------------------


def test_a_declared_reference_that_is_missing_is_reported(tmp_path):
    entry = _entry(references=["references/history-and-continuation.md"])
    root = scratch_repo(tmp_path, {"demo": entry})
    (root / "demo-harness-handoff" / "references" / "history-and-continuation.md").unlink()
    result = run_build(root, "--check")
    assert result.returncode == 2
    assert "declared but missing" in result.stdout


def test_an_undeclared_reference_file_is_reported(tmp_path):
    entry = _entry(references=[])
    root = scratch_repo(tmp_path, {"demo": entry})
    references = root / "demo-harness-handoff" / "references"
    references.mkdir(exist_ok=True)
    (references / "stray.md").write_text("prose\n", encoding="utf-8")
    result = run_build(root, "--check")
    assert result.returncode == 2
    assert "present but undeclared" in result.stdout
    assert "contracts.json" in result.stdout, "it must say where to declare it"


# --- the real repository -----------------------------------------------------


def test_the_checked_in_trees_match_their_source():
    """The gate a contributor runs before committing: trees are not hand-edited."""
    result = subprocess.run(
        [sys.executable, str(BUILD), "--check"], cwd=REPO, capture_output=True, text=True
    )
    assert result.returncode == 0, f"generated trees are stale:\n{result.stdout}{result.stderr}"


def test_every_harness_in_the_contract_has_a_generated_tree():
    document = json.loads((REPO / "skills-src" / "contracts.json").read_text(encoding="utf-8"))
    assert document["version"] == build_skills.CONTRACT_VERSION
    harnesses = document["harnesses"]
    assert set(harnesses) == {
        "amp",
        "antigravity",
        "claude",
        "cline",
        "codex",
        "copilot",
        "cursor",
        "droid",
        "gemini",
        "grok",
        "junie",
        "muse",
        "opencode",
        "openhands",
    }, "adding or dropping a harness must be an explicit contract change"

    for name, entry in harnesses.items():
        skill_dir = REPO / entry["skill"]
        assert (skill_dir / "SKILL.md").is_file(), f"{entry['skill']}/SKILL.md is missing"
        assert (skill_dir / "contract.json").is_file(), f"{entry['skill']}/contract.json is missing"
        skill = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
        assert skill.count(LANE_HEADING) == 1, f"{entry['skill']}: lane block duplicated"
        assert skill.startswith(f"---\nname: {entry['skill']}\n"), f"{entry['skill']}: wrong frontmatter name"

        payload = json.loads((skill_dir / "contract.json").read_text(encoding="utf-8"))
        assert payload["harness"] == name
        assert payload["skill"] == entry["skill"]
        for key in CONTRACT_KEYS:
            assert payload[key] == entry[key], f"{entry['skill']}/contract.json disagrees on {key}"


def test_the_real_harness_onboarding_vocabulary_is_closed():
    """Every shipped contract declares the F1 approval posture and credential channel."""
    document = json.loads((REPO / "skills-src" / "contracts.json").read_text(encoding="utf-8"))
    for name, entry in document["harnesses"].items():
        assert entry["interactivity"] in ("non_interactive", "prompts"), name
        for key in ("credential_channel", "credential_auth"):
            assert entry[key] in ("env", "stdin", "file", "keychain", "native-session"), f"{name}: {key}"
    assert document["harnesses"]["codex"]["interactivity"] == "non_interactive", (
        "the dispatched Codex lane runs autonomously without per-action approval prompts"
    )


def test_the_real_sdk_routes_match_policy():
    """SDK bindings must preserve fresh-only Codex and Grok's protocol-only reality."""
    document = json.loads((REPO / "skills-src" / "contracts.json").read_text(encoding="utf-8"))
    harnesses = document["harnesses"]
    assert harnesses["codex"]["sdk"]["continuation"] == "forbidden"
    assert harnesses["codex"]["sdk"]["continuation_scope"] == "none"
    assert harnesses["grok"]["sdk"]["kind"] == "protocol"
    assert harnesses["grok"]["sdk"]["packages"] == {}
    assert harnesses["antigravity"]["sdk"]["continuation"] == "cli"
    assert harnesses["antigravity"]["sdk"]["continuation_scope"] == "native-existing-only"
    assert harnesses["gemini"]["sdk"]["kind"] == "none"
    assert harnesses["junie"]["sdk"]["kind"] == "none"
    assert harnesses["openhands"]["interactivity"] == "non_interactive"
    assert harnesses["copilot"]["sdk"]["status"] == "preview"
    for name, entry in harnesses.items():
        sdk = entry["sdk"]
        assert sdk["docs"].startswith("https://"), name
        assert sdk["auth_notes"] and sdk["approval_notes"], name
        assert sdk["id_namespaces"], name
        if name != "codex":
            assert sdk["continuation"] != "forbidden", name


def test_skill_prose_names_the_contract_sdk_surface():
    """The machine contract and the human prose must not drift apart."""
    document = json.loads((REPO / "skills-src" / "contracts.json").read_text(encoding="utf-8"))
    for name, entry in document["harnesses"].items():
        skill = (REPO / entry["skill"] / "SKILL.md").read_text(encoding="utf-8")
        sdk = entry["sdk"]
        assert sdk["docs"] in skill, f"{name}: contract docs URL missing from prose"
        if sdk["kind"] == "library":
            for package in sdk["packages"].values():
                assert package in skill, f"{name}: contract package {package} missing from prose"
        if sdk["kind"] == "protocol":
            assert sdk["command"] in skill, f"{name}: contract command missing from prose"


def test_one_lane_block_source_per_harness_and_no_extras():
    document = json.loads((REPO / "skills-src" / "contracts.json").read_text(encoding="utf-8"))
    names = set(document["harnesses"])
    for kind in ("lane-spawning", "harnesses"):
        present = {path.stem for path in (REPO / "skills-src" / kind).glob("*.md")}
        assert present == names, f"skills-src/{kind}/ must hold exactly the contracted harnesses"


def test_the_shared_vocabulary_is_the_one_work_coordination_fans_out_on():
    """The seam with the coordination package: these two lists are load-bearing.

    work-coordination's drift test reads this file when the checkouts sit side by
    side, and its CLI validates `--status` against the same words. Changing them
    here changes what every harness may report.
    """
    document = json.loads((REPO / "skills-src" / "contracts.json").read_text(encoding="utf-8"))
    vocabulary = document["advisory_vocabulary"]
    assert vocabulary["status"] == ["started", "milestone", "blocked", "done"]
    assert vocabulary["fan_out"] == ["blocked", "done"]
    assert vocabulary["implemented_by"] == "work-coordination"
