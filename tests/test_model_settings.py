"""Capability evidence gates launches; recorded requests do not prove runtime."""
import asyncio
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
import subprocess
import sys

import pytest

from mcp_bridge import cli_executor, contracts, model_settings, server
from plan_helpers import make_cli_plan


@pytest.fixture
def evidence(tmp_path):
    path = tmp_path / "capabilities.json"
    path.write_text(json.dumps({"fetched_at": datetime.now(timezone.utc).isoformat(),
        "client_version": "test", "models": [{"slug": "selected-model",
        "supported_reasoning_levels": [{"effort": "high"}]}]}))
    return path


def test_pointed_pair_is_bound_to_exact_bytes(evidence):
    result = model_settings.preflight("selected-model", "high", evidence)
    assert result["status"] == "validated"
    assert result["source"]["kind"] == "supplied_file"
    assert len(result["source"]["sha256"]) == 64
    assert result["effective_runtime_state"] == "not_observed"


@pytest.mark.parametrize("change", ["stale", "future", "missing", "duplicate", "malformed", "unsupported"])
def test_invalid_evidence_refuses_pair_before_any_launch(evidence, monkeypatch, change):
    data = json.loads(evidence.read_text())
    if change in {"stale", "future"}:
        offset = timedelta(days=-2 if change == "stale" else 2)
        data["fetched_at"] = (datetime.now(timezone.utc) + offset).isoformat()
    elif change == "missing":
        data["models"] = []
    elif change == "duplicate":
        data["models"] *= 2
    elif change == "malformed":
        data["models"][0]["supported_reasoning_levels"] = None
    elif change == "unsupported":
        data["models"][0]["supported_reasoning_levels"] = [{"effort": "low"}]
    evidence.write_text(json.dumps(data))
    monkeypatch.setattr(cli_executor.shutil, "which", lambda _: sys.executable)
    monkeypatch.setattr(cli_executor.subprocess, "run", lambda *a, **k: pytest.fail("launched with invalid evidence"))
    with pytest.raises(ValueError, match="preflight failed"):
        make_cli_plan(contracts.get_harness("codex"), prompt="task", workspace="/tmp",
            extra_argv=["--model", "selected-model", "-c", 'model_reasoning_effort="high"'],
            extra_at=1, model_capabilities=str(evidence))


def test_missing_cache_does_not_invent_native_defaults(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    assert model_settings.preflight()["status"] == "inherited"
    assert model_settings.preflight("selected-model")["status"] == "unknown"
    with pytest.raises(ValueError, match="explicit model"):
        model_settings.preflight(None, "high")
    with pytest.raises(ValueError, match="preflight failed"):
        model_settings.preflight("selected-model", "high")


def test_receipt_does_not_promote_prompt_or_request_to_observation():
    argv = ["--model", "selected-model", "-c", 'model_reasoning_effort="high"']
    prose = json.dumps({"type": "item.completed", "item": {"text": "model: selected-model; effort: high"}})
    receipt = model_settings.launch_receipt(argv, prose)
    assert receipt["requested"] == {"model": "selected-model", "reasoning_effort": "high"}
    assert receipt["observed"] == {}
    assert not receipt["effective_settings_verified"]
    assert receipt["matches_request"] is None
    partial = model_settings.launch_receipt(argv, json.dumps({"type": "turn_context", "payload": {"model": "other-model"}}))
    assert not partial["effective_settings_verified"]
    assert partial["matches_request"] is False


def test_only_returned_thread_journal_supplies_effective_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    session_id = "12345678-1234-1234-1234-123456789abc"
    folder = tmp_path / "sessions" / "2026" / "09" / "30"
    folder.mkdir(parents=True)
    journal = folder / f"rollout-date-{session_id}.jsonl"
    journal.write_text(json.dumps({"type": "session_meta", "payload": {"id": session_id}}) + "\n" +
        json.dumps({"type": "turn_context", "payload": {"model": "selected-model", "effort": "high"}}) + "\n")
    (folder / "unrelated.jsonl").write_text("private unrelated transcript")
    context = model_settings.owned_context(session_id)
    receipt = model_settings.launch_receipt(["--model", "selected-model", "-c", 'model_reasoning_effort="high"'], context)
    assert receipt["effective_settings_verified"]
    assert receipt["matches_request"]
    journal.write_text(json.dumps({"type": "session_meta", "payload": {"id": "different"}}) + "\n" + context)
    assert model_settings.owned_context(session_id) == ""
    assert model_settings.owned_context("../unrelated") == ""


def test_bridge_binds_explicit_effort_and_reports_unobserved_runtime(evidence, monkeypatch):
    monkeypatch.setattr(cli_executor.shutil, "which", lambda _: sys.executable)
    seen = {}
    def execute(argv, **kwargs):
        seen["argv"] = argv
        return subprocess.CompletedProcess(argv, 0, '{"type":"thread.started","thread_id":"own-thread"}', "")
    monkeypatch.setattr(cli_executor.subprocess, "run", execute)
    receipt = asyncio.run(server.handoff_fresh("codex", "task", workspace="/tmp", use="cli",
        model="selected-model", reasoning_effort="high", model_capabilities=str(evidence)))
    assert 'model_reasoning_effort="high"' in seen["argv"]
    assert receipt["model_preflight"]["status"] == "validated"
    assert receipt["session_id"] == "own-thread"
    assert receipt["model_settings"]["observed"] == {}
    assert receipt["effective_settings_verified"] is False


def test_standalone_skill_helper_runs_outside_checkout(evidence, tmp_path):
    import shutil
    root = Path(__file__).resolve().parents[1]
    copied = tmp_path / "portable"
    shutil.copytree(root / "codex-harness-handoff", copied)
    result = subprocess.run([sys.executable, str(copied / "model_settings.py"),
        "--model", "selected-model", "--reasoning-effort", "high", "--capabilities", str(evidence)],
        cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["status"] == "validated"
    assert (copied / "settings.json").is_file()


@pytest.mark.parametrize("filename", ["model_settings.py", "settings.json"])
def test_bundle_drift_is_checked(tmp_path, filename):
    import shutil
    root = Path(__file__).resolve().parents[1]
    checkout = tmp_path / "checkout"
    shutil.copytree(root, checkout, ignore=shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache", ".venv"))
    (checkout / "codex-harness-handoff" / filename).write_text("# drift\n")
    result = subprocess.run([sys.executable, str(checkout / "scripts/build_skills.py"), "--check"], capture_output=True, text=True)
    assert result.returncode == 1
    assert "codex-harness-handoff/" + filename in result.stdout
