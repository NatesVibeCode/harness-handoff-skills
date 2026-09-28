"""Offline regressions: temporary stores, no live keys, no provider calls."""
import asyncio
import json
import io
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.error

import pytest

from mcp_bridge import ambiguity, control, recovery, server, jev_worker


@pytest.fixture
def host(tmp_path, monkeypatch):
    class FakeHost:
        config = {"subject": {"principal_ref": "session-a", "altitude": "run"},
                  "repositories": {"work": {"path": str(tmp_path), "status": "active"}},
                  "jev_review": {"enabled": True, "key_env": "TEST_JEV_KEY", "model": "typesafe/jev-1.13"}}
        state_path = tmp_path / "profiles.json"
        binding = {"host": "host"}
        denied = set()
        calls = []

        def state(self):
            return {"schema": "harness.launch_profiles.v1", "revision": 0, "profiles": {}}, "empty"

        def authorize(self, operation, harness, profile, repo, setting="", value=None):
            self.calls.append((operation, setting, value))
            return {"verdict": {"effect": "deny" if (operation, value) in self.denied else "allow"}}

        def unchanged(self):
            pass

    instance = FakeHost()
    monkeypatch.setattr(control, "Host", lambda: instance)
    monkeypatch.delenv("TEST_JEV_KEY", raising=False)
    monkeypatch.setattr(ambiguity, "_inflight", False)
    monkeypatch.setattr(ambiguity, "_retry_after", 0)
    monkeypatch.setattr(ambiguity, "_calls", [])
    return instance


def request(candidates=False):
    value = {"harness": "codex", "profile": "build", "repo": "work", "intent": "Use stronger reasoning"}
    if candidates:
        value["candidates"] = [
            {"id": "high", "settings": {"reasoning_effort": "high"}, "evidence": "earlier preference"},
            {"id": "max", "settings": {"reasoning_effort": "max"}, "evidence": "later suggestion"},
        ]
    return value


def test_exact_request_never_calls_reviewer_or_uses_journal(host, monkeypatch):
    req = request(True)
    req["candidates"] = req["candidates"][:1]
    monkeypatch.setattr(ambiguity, "_review", lambda *a: pytest.fail("review called"))
    host.config["jev_review"] = {"enabled": True, "timeout_ms": "broken"}
    result = ambiguity.resolve(req)
    assert result["status"] == "resolved" and result["plan"]["allowed"]
    assert not host.state_path.with_name("profiles.json.recovery.sqlite3").exists()


def test_host_errors_are_not_reinterpreted(host, monkeypatch):
    def broken():
        raise control.ControlError("policy changed")
    host.unchanged = broken
    monkeypatch.setattr(ambiguity, "recover", lambda *a: pytest.fail("authority error became ambiguity"))
    with pytest.raises(control.ControlError, match="policy changed"):
        ambiguity.resolve(request(True))


def test_invalid_shape_can_recover_without_provider(host):
    result = ambiguity.resolve(dict(request(), extra_context="supported catch-all"))
    assert result["status"] == "needs_recovery"
    assert result["recovery_task"]["route"] == "clarify_request"
    assert result["review"]["reason"] == "missing_key"


@pytest.mark.parametrize("reason", ["provider_http_401", "provider_http_402", "provider_http_429", "timeout", "provider_or_response_failure"])
def test_reviewer_outages_preserve_deterministic_work(host, monkeypatch, reason):
    monkeypatch.setattr(ambiguity, "_review", lambda *a: {"status": "unavailable", "reason": reason})
    result = ambiguity.recover(request())
    assert result["status"] == "needs_recovery"
    assert result["recovery_task"]["route"] == "gather_context"
    assert result["review"]["reason"] == reason
    exact = request(True)
    exact["candidates"] = exact["candidates"][:1]
    assert ambiguity.resolve(exact)["plan"]["allowed"]


def test_malformed_choice_falls_back(host, monkeypatch):
    monkeypatch.setattr(ambiguity, "_review", lambda *a: {"status": "complete", "answer": {"type": "choice", "choice": []}})
    result = ambiguity.recover(request())
    assert result["review"]["reason"] == "invalid_review_response"
    assert result["recovery_task"]["route"] == "gather_context"


def test_episode_stops_after_three_and_does_not_reset_for_failure_noise(host, monkeypatch):
    calls = []
    monkeypatch.setattr(ambiguity, "_review", lambda *a: calls.append(1) or {"status": "unavailable", "reason": "timeout"})
    for i in range(3):
        result = ambiguity.recover(dict(request(), failure_kind=str(i), claims=["someone says they own this"]))
        assert result["episode"]["issued"] == i + 1
        assert "owner" not in result["recovery_task"]
        assert result["recovery_task"]["coordination"]["wait_for_peer"] is False
    result = ambiguity.recover(request())
    assert result["status"] == "needs_input" and result["recovery_task"] is None
    assert len(calls) == 3
    exact = request(True)
    exact["candidates"] = exact["candidates"][:1]
    assert ambiguity.resolve(exact)["plan"]["allowed"]
    independent = dict(request(), intent="Resolve a separate question")
    assert ambiguity.recover(independent)["episode"]["issued"] == 1


def test_ambiguous_resolution_stops_before_fourth_provider_call(host, monkeypatch):
    calls = []
    monkeypatch.setattr(ambiguity, "_review", lambda *a: calls.append(1) or {"status": "unavailable", "reason": "timeout"})
    for _ in range(4):
        result = ambiguity.resolve(request(True))
    assert result["status"] == "needs_input"
    assert len(calls) == 3


def test_episode_deadline_is_terminal_not_automatically_restarted(host, monkeypatch):
    monkeypatch.setattr(recovery.time, "time", lambda: 1000)
    assert recovery.issue(host, request())["status"] == "issued"
    monkeypatch.setattr(recovery.time, "time", lambda: 1400)
    assert recovery.issue(host, request())["status"] == "exhausted"


def test_recovery_contention_returns_immediately(host):
    recovery.issue(host, request())
    db = sqlite3.connect(str(host.state_path) + ".recovery.sqlite3", timeout=0)
    try:
        db.execute("BEGIN IMMEDIATE")
        start = time.monotonic()
        result = recovery.issue(host, request())
        assert result["status"] == "busy"
        assert time.monotonic() - start < 0.5
        routed = ambiguity.recover(request())
        assert routed["status"] == "recovery_busy" and routed["question"] is None
    finally:
        db.close()


def test_settings_publication_never_waits(tmp_path):
    path = tmp_path / "profiles.json"
    with control._lock(path):
        start = time.monotonic()
        with pytest.raises(control.ControlError, match="publication is busy"):
            with control._lock(path):
                pytest.fail("second writer acquired publication gate")
        assert time.monotonic() - start < 0.5


def test_review_timeout_opens_circuit_and_sends_no_second_request(host, monkeypatch):
    monkeypatch.setenv("TEST_JEV_KEY", "test-only-not-a-credential")
    calls = []
    def timeout(*args, **kwargs):
        calls.append(kwargs)
        raise subprocess.TimeoutExpired("review", 0.1)
    monkeypatch.setattr(ambiguity.subprocess, "run", timeout)
    cfg = ambiguity._configuration(host)
    assert ambiguity._review(cfg, {})["reason"] == "timeout"
    assert ambiguity._review(cfg, {})["reason"] == "review_budget_or_circuit_open"
    assert len(calls) == 1
    assert calls[0]["timeout"] <= 5


@pytest.mark.parametrize("status", [401, 402, 429, 503])
def test_worker_http_failures_are_bounded_receipts(monkeypatch, capsys, status):
    class Input:
        buffer = io.BytesIO(b'{"model":"typesafe/jev-1.13","state":{},"questions":{}}')
    class Opener:
        def open(self, *args, **kwargs):
            raise urllib.error.HTTPError("https://example.invalid", status, "test", {}, None)
    monkeypatch.setattr(jev_worker.sys, "stdin", Input())
    monkeypatch.setattr(jev_worker.urllib.request, "build_opener", lambda *a: Opener())
    monkeypatch.setenv("HARNESS_JEV_KEY", "test-only-not-a-credential")
    jev_worker.main()
    result = json.loads(capsys.readouterr().out)
    assert result == {"status": "unavailable", "reason": "provider_http_" + str(status)}


def test_real_abac_denied_batch_publishes_nothing(real_host):
    _, cfg = real_host
    policy_path = Path(cfg["policy_files"][0])
    policy_path.write_text(json.dumps({"schema": "abac.policyfile.v1", "policies": [
        {"id": "read", "effect": "allow", "priority": 1, "scope": {"action.verb": "read"}},
        {"id": "one-write", "effect": "allow", "priority": 1, "scope": {"action.verb": "write", "resource.ref": "harness-settings/codex/one"}}]}))
    changes = [{"harness": "codex", "profile": name, "repo": "work", "settings": {"reasoning_effort": "high"}} for name in ("one", "two")]
    proposal = control.plan(changes)
    assert not proposal["allowed"]
    assert not control.apply(changes, proposal["digest"])["applied"]
    assert not Path(cfg["state_file"]).exists()


def test_final_abac_denial_survives_model_selection(host, monkeypatch):
    host.denied.add(("settings.apply", "max"))
    monkeypatch.setattr(ambiguity, "_review", lambda *a: {
        "status": "complete", "answer": {"type": "choice", "choice": "max", "confidence": 1,
        "probabilities": {"high": 0, "max": 1, "unresolved": 0}}})
    result = ambiguity.resolve(request(True))
    assert result["status"] == "denied"
    assert not result["plan"]["allowed"] and not result["execution_authorized"]
    assert result["episode"]["issued"] == 1


def test_profile_preparation_does_not_block_event_loop(monkeypatch):
    entered, release = threading.Event(), threading.Event()
    def prepare(*args):
        entered.set()
        release.wait(2)
        return [], {"profile": "build"}
    monkeypatch.setattr(control, "launch_settings", prepare)
    monkeypatch.setattr(server.cli_executor, "run_cli", lambda *a, **kw: {})
    async def scenario():
        task = asyncio.create_task(server.handoff_fresh("codex", "task", workspace="/tmp", settings_profile="build"))
        try:
            for _ in range(50):
                if entered.is_set():
                    break
                await asyncio.sleep(0.01)
            assert entered.is_set()
            assert not task.done()
        finally:
            release.set()
            await task
    asyncio.run(scenario())


@pytest.fixture
def real_host(tmp_path, monkeypatch):
    source = os.environ.get("ABAC_SOURCE")
    if not source:
        pytest.skip("set ABAC_SOURCE for real local evaluator integration")
    binary = tmp_path / "abac"
    subprocess.run(["go", "build", "-o", str(binary), "./cmd/abac"], cwd=source,
                   env=dict(os.environ, GOPROXY="off", GOSUMDB="off"), check=True, capture_output=True)
    repo = tmp_path / "repo"
    repo.mkdir()
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps({"schema": "abac.policyfile.v1", "policies": [
        {"id": "temp-allow", "effect": "allow", "priority": 1, "scope": {"resource.labels.repo_id": "work"}}]}))
    config = {"schema": "harness.control_host.v1", "abac_binary": str(binary), "policy_files": [str(policy)],
              "subject": {"principal_ref": "offline-integration", "altitude": "run"},
              "repositories": {"work": {"path": str(repo), "status": "active"},
                               "unrelated": {"path": str(tmp_path / "missing"), "status": "superseded"}},
              "state_file": str(tmp_path / "profiles.json")}
    path = tmp_path / "host.json"
    path.write_text(json.dumps(config))
    monkeypatch.setenv(control.CONFIG_ENV, str(path))
    return path, config


def test_real_abac_plan_apply_and_stale_refusal(real_host):
    path, cfg = real_host
    changes = [{"harness": "codex", "profile": "build", "repo": "work", "settings": {"reasoning_effort": "max"}}]
    plan = control.plan(changes)
    assert plan["allowed"]
    result = control.apply(changes, plan["digest"])
    assert result["applied"] and result["revision"] == 1
    with pytest.raises(control.ControlError, match="stale"):
        control.apply(changes, plan["digest"])
    assert control.get("codex", "build", "work")["profile"]["settings"]["reasoning_effort"] == "max"


def test_cli_recovery_is_a_successful_receipt_not_a_retry_signal(real_host, tmp_path):
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps(request()))
    result = subprocess.run([sys.executable, "scripts/harness-control", "recover", "--request", str(request_path)],
                            text=True, capture_output=True, check=False)
    assert result.returncode == 0
    receipt = json.loads(result.stdout)
    assert receipt["status"] == "needs_recovery" and not receipt["execution_authorized"]


def test_canonical_root_drift_invalidates_binding(real_host, tmp_path):
    config_path, cfg = real_host
    alias = tmp_path / "alias"
    alias.symlink_to(cfg["repositories"]["work"]["path"], target_is_directory=True)
    cfg["repositories"]["work"]["path"] = str(alias)
    config_path.write_text(json.dumps(cfg))
    host = control.Host()
    other = tmp_path / "other"
    other.mkdir()
    alias.unlink()
    alias.symlink_to(other, target_is_directory=True)
    with pytest.raises(control.ControlError, match="changed"):
        host.unchanged()
