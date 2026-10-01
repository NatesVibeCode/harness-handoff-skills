"""Product/profile isolation and dispatch checks; no provider or live host use."""
import asyncio
import copy
import json
from pathlib import Path
import subprocess
import sys

import pytest

from mcp_bridge import cli_executor, contracts, control, server, launch_plan
from plan_helpers import make_cli_plan


@pytest.fixture(autouse=True)
def hermetic_cli_resolution(monkeypatch):
    monkeypatch.setattr(cli_executor.shutil, "which", lambda _: sys.executable)


@pytest.fixture
def product_host(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    other = tmp_path / "other"
    other.mkdir()
    path = tmp_path / "profiles.json"
    state = {"schema": "harness.launch_profiles.v1", "revision": 1, "profiles": {
        "codex/build": {"repo": "work", "settings": {"sandbox": "read-only", "approval": "on-request", "native_profile": "codex-build"}},
        "muse/build": {"repo": "work", "settings": {"disable_sandbox": False, "disable_approval": True}},
        "claude/build": {"repo": "work", "settings": {"permission_mode": "plan"}},
        "claude/private": {"repo": "work", "settings": {"permission_mode": "bypassPermissions"}},
        "claude/other-repo": {"repo": "other", "settings": {"permission_mode": "acceptEdits"}}
    }}
    path.write_text(json.dumps(state))

    class ProductHost:
        config = {"access_context": {"product_ref": "FL", "permission_context": "AO-FL-A", "realm": "factlens"},
                  "repositories": {"work": {"path": str(repo), "status": "active"},
                                  "other": {"path": str(other), "status": "active"}}}
        binding = {"host": "test-host", "catalog": "test-catalog"}
        denied = set()
        surface_denied = set()
        calls = []
        state_path = path

        def state(self):
            raw = path.read_bytes()
            return json.loads(raw), control._digest(raw)

        def authorize(self, operation, harness, profile, repo, setting="", value=None):
            call = (operation, harness, profile, repo, setting, value)
            self.calls.append(call)
            effect = "deny" if (harness, profile, operation) in self.denied else "allow"
            return {"request_digest": control._digest(call), "operation": operation,
                    "setting": setting or None, "verdict": {"effect": effect}}

        def unchanged(self):
            pass

        def authorize_surface(self, harness, action, repo=None, profile=None, session_id=None, controls=None, resolved=None):
            effect = "deny" if (harness, action) in self.surface_denied else "allow"
            return {"request_digest": control._digest([harness, action, repo, profile, session_id, controls]),
                    "operation": "handoff." + action, "verdict": {"effect": effect}}

    instance = ProductHost()
    monkeypatch.setattr(control, "Host", lambda: instance)
    monkeypatch.setenv(control.CONFIG_ENV, str(tmp_path / "host.json"))
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex-home"))
    return instance, repo, state


def run(coro):
    return asyncio.run(coro)


def test_inventory_is_exact_product_repo_and_read_permission(product_host):
    host, _, _ = product_host
    host.denied.add(("claude", "private", "settings.get"))
    result = control.profiles("claude", "work")
    assert [(row["harness"], row["profile"], row["repo"]) for row in result["profiles"]] == [("claude", "build", "work")]
    assert not any(call[1] in {"muse", "codex"} or call[3] == "other" for call in host.calls)
    assert "bypassPermissions" not in json.dumps(result)
    assert "private" not in json.dumps(result)
    assert run(server.settings_profiles("claude", "work"))["profiles"] == result["profiles"]


def test_same_profile_name_keeps_distinct_native_controls(product_host):
    _, repo, _ = product_host
    codex, c = control.launch_settings("codex", "build", str(repo))
    muse, m = control.launch_settings("muse", "build", str(repo))
    claude, a = control.launch_settings("claude", "build", str(repo))
    assert "--profile" in codex and "codex-build" in codex
    assert "--sandbox" in codex and 'approval_policy="on-request"' in codex
    assert muse == ["--disable-approval"]
    assert claude == ["--permission-mode", "plan"]
    assert len({c["profile_digest"], m["profile_digest"], a["profile_digest"]}) == 3
    assert [r["harness"] for r in (c, m, a)] == ["codex", "muse", "claude"]


@pytest.mark.parametrize("settings", [{"native_profile": "codex-build"}, {"sandbox": "read-only"}, {"disable_sandbox": True}])
def test_product_specific_catalog_refuses_foreign_controls(settings):
    with pytest.raises(control.ControlError, match="unsupported setting"):
        control._settings("claude", settings)


@pytest.mark.parametrize("use", ["cli", "sdk", "auto"])
def test_configured_bridge_cannot_bypass_access_gate_or_override_saved_settings(product_host, monkeypatch, use):
    host, repo, _ = product_host
    host.surface_denied.add(("codex", "launch"))
    monkeypatch.setattr(cli_executor, "run_cli", lambda *a, **k: pytest.fail("profile bypass launched CLI"))
    monkeypatch.setattr(server.sdk_executors, "available", lambda _: False)
    assert run(server.handoff_fresh("codex", "task", workspace=str(repo), use=use, model="override"))["refused"]
    host.surface_denied.clear()
    assert run(server.handoff_fresh("codex", "task", workspace=str(repo), use=use, settings_profile="build", model="override"))["refused"]
    assert run(server.handoff_fresh("claude", "task", workspace=str(repo), use=use, settings_profile="build", approval="unattended"))["refused"]


def test_configured_continuation_has_no_profile_bypass(product_host, monkeypatch):
    host, repo, _ = product_host
    host.surface_denied.add(("claude", "continue"))
    monkeypatch.setattr(server, "_cli_continue", lambda *a, **k: pytest.fail("continued without selected profile"))
    assert run(server.handoff_continue("claude", "exact-session", "task", workspace=str(repo)))["refused"]


@pytest.mark.parametrize("harness", ["codex", "muse", "claude"])
def test_per_product_denial_launches_nothing(product_host, monkeypatch, harness):
    host, repo, _ = product_host
    host.denied.add((harness, "build", "handoff.launch_settings"))
    monkeypatch.setattr(cli_executor, "run_cli", lambda *a, **k: pytest.fail("denied launch executed"))
    result = run(server.handoff_fresh(harness, "task", workspace=str(repo), settings_profile="build"))
    assert result["refused"] and "ABAC denies" in result["reason"]


def test_missing_product_profile_does_not_borrow_another(product_host, monkeypatch):
    _, repo, _ = product_host
    monkeypatch.setattr(cli_executor, "run_cli", lambda *a, **k: pytest.fail("substituted another product/profile"))
    result = run(server.handoff_fresh("muse", "task", workspace=str(repo), settings_profile="private"))
    assert result["refused"] and "unknown saved launch profile" in result["reason"]
    assert run(server.settings_profiles("cursor", "work"))["refused"]


def test_workspace_must_be_absolute_existing_and_inside_selected_repo(product_host):
    _, repo, _ = product_host
    for workspace in ("relative", str(repo / "missing"), str(repo.parent / "other")):
        with pytest.raises(control.ControlError, match="outside"):
            control.launch_settings("claude", "build", workspace)


@pytest.mark.parametrize("change", ["settings", "host", "argv", "product", "denial"])
def test_recheck_refuses_change_between_authorization_and_dispatch(product_host, change):
    host, repo, state = product_host
    argv, receipt = control.launch_settings("claude", "build", str(repo))
    harness = "claude"
    if change == "settings":
        state["profiles"]["claude/build"]["settings"]["permission_mode"] = "bypassPermissions"
        host.state_path.write_text(json.dumps(state))
    elif change == "host":
        host.binding = {"host": "different-host"}
    elif change == "argv":
        argv.extend(["--permission-mode", "bypassPermissions"])
    elif change == "product":
        harness = "muse"
    elif change == "denial":
        host.denied.add(("claude", "build", "handoff.launch_settings"))
    with pytest.raises(control.ControlError):
        control.recheck_launch(receipt, harness=harness, workspace=str(repo), argv=argv)


@pytest.mark.parametrize("harness", ["codex", "muse", "claude"])
def test_authorized_product_profile_reaches_local_child_unchanged(product_host, monkeypatch, tmp_path, harness):
    _, repo, state = product_host
    # A representative local child records argv and stdin; it is not a native
    # harness acceptance test or a provider/session launch.
    executable = tmp_path / "argv-child"
    capture = tmp_path / "capture.json"
    executable.write_text(f"#!{sys.executable}\nimport json,sys\nfrom pathlib import Path\nPath({str(capture)!r}).write_text(json.dumps({{'argv':sys.argv[1:], 'stdin':sys.stdin.read()}}))\nprint('{{\"session_id\":\"local-child\"}}')\n")
    executable.chmod(0o700)
    monkeypatch.setattr(cli_executor.shutil, "which", lambda _: str(executable))
    original = contracts.get_harness
    def contract(name):
        entry = copy.deepcopy(original(name))
        entry["binary"] = str(executable)
        return entry
    monkeypatch.setattr(contracts, "get_harness", contract)
    result = run(server.handoff_fresh(harness, "selected task", workspace=str(repo), settings_profile="build"))
    assert result["exit_code"] == 0
    receipt = result["settings_control"]
    assert receipt["harness"] == harness and receipt["profile"] == "build"
    assert receipt["requested_settings"] == state["profiles"][harness + "/build"]["settings"]
    assert receipt["rechecked_before_dispatch"]
    assert result["access_control"]["access_context"]["permission_context"] == "AO-FL-A"
    assert result["access_control"]["rechecked_before_dispatch"]
    assert not result["effective_settings_verified"]
    actual = json.loads(capture.read_text())["argv"]
    expected, _ = control.launch_settings(harness, "build", str(repo))
    offset = 1 if harness in {"codex", "muse"} else 0
    assert actual[offset:offset + len(expected)] == expected
    assert "--dangerously-bypass-approvals-and-sandbox" not in actual


def test_executor_rechecks_even_when_initial_bridge_authorization_was_valid(product_host, monkeypatch):
    host, repo, _ = product_host
    argv, receipt = control.launch_settings("claude", "build", str(repo))
    monkeypatch.setattr(cli_executor.shutil, "which", lambda _: sys.executable)
    plan = make_cli_plan(contracts.get_harness("claude"), prompt="task", workspace=str(repo),
        extra_argv=argv, settings_control=receipt)
    auth = control.authorize_launch_plan(plan)
    host.denied.add(("claude", "build", "handoff.launch_settings"))
    monkeypatch.setattr(cli_executor.subprocess, "run", lambda *a, **k: pytest.fail("late denial launched child"))
    with pytest.raises(cli_executor.ExecutionError, match="ABAC denies"):
        cli_executor.run_cli(plan, authorization=auth)


def test_access_profile_is_separate_from_optional_launch_settings(product_host, monkeypatch):
    _, repo, _ = product_host
    seen = {}
    def execute(entry, **kwargs):
        seen["plan"] = entry
        return {"route": "cli", "access_control": kwargs["authorization"]}
    monkeypatch.setattr(cli_executor, "run_cli", execute)
    receipt = run(server.handoff_fresh("codex", "task", workspace=str(repo), use="cli", model="selected-model"))
    assert seen["plan"].settings_control is None
    assert receipt["access_control"]["settings_profile"] is None
    assert receipt["access_control"]["access_context"]["permission_context"] == "AO-FL-A"
    assert receipt["access_control"]["requested_controls"]["model"] == "selected-model"


def test_projection_hides_denied_surfaces(product_host):
    host, _, _ = product_host
    host.surface_denied.update((name, "project") for name in contracts.load_contracts()["harnesses"] if name != "claude")
    assert [row["harness"] for row in server.list_harnesses()] == ["claude"]
    assert set(server.settings_describe()["harnesses"]) == {"claude"}
    assert server.get_contract("codex")["reason"] == "not available in this session"


def test_projection_denial_precedes_launch_or_settings_lookup(product_host, monkeypatch):
    host, repo, _ = product_host
    host.surface_denied.add(("claude", "project"))
    monkeypatch.setattr(control, "launch_settings", lambda *a, **k: pytest.fail("unprojected profile was read"))
    result = run(server.handoff_fresh("claude", "task", workspace=str(repo), settings_profile="private"))
    assert result["reason"] == "not available in this session"


def test_history_requires_review_grant_before_sdk_lookup(product_host, monkeypatch):
    host, repo, _ = product_host
    host.surface_denied.add(("claude", "review"))
    monkeypatch.setattr(server.sdk_executors, "available", lambda _: pytest.fail("history route inspected before grant"))
    assert run(server.session_history("claude", "exact-session", workspace=str(repo)))["refused"]


def test_access_context_change_invalidates_dispatch(product_host):
    host, repo, _ = product_host
    receipt = control.access_gate("claude", str(repo))
    # Host contexts are copied into receipts; changing the host cannot rewrite
    # an already issued identity binding.
    host.config = copy.deepcopy(host.config)
    host.config["access_context"]["permission_context"] = "AO-FL-B"
    with pytest.raises(control.ControlError, match="changed"):
        control.recheck_access(receipt, harness="claude", workspace=str(repo), action="launch")


def test_sdk_launch_rechecks_access_before_invocation(product_host, monkeypatch):
    host, repo, _ = product_host
    def available(_):
        host.surface_denied.add(("claude", "launch"))
        return True
    async def execute(*args):
        pytest.fail("SDK invoked after final access denial")
    monkeypatch.setattr(server.sdk_executors, "available", available)
    monkeypatch.setitem(server.sdk_executors.EXECUTORS["claude"], "fresh", execute)
    result = run(server.handoff_fresh("claude", "task", workspace=str(repo), use="sdk"))
    assert "ABAC denies launch" in result["reason"]


def test_governed_sdk_continuation_preserves_context_and_exact_session(product_host, monkeypatch):
    _, repo, _ = product_host
    seen = []
    async def resume(session_id, prompt, workspace):
        seen.append((session_id, prompt, workspace))
        return {"route": "sdk", "session_id": session_id}
    monkeypatch.setattr(server.sdk_executors, "available", lambda _: True)
    monkeypatch.setitem(server.sdk_executors.EXECUTORS["claude"], "resume", resume)
    receipt = run(server.handoff_continue("claude", "exact-session", "task", workspace=str(repo)))
    assert seen == [("exact-session", "task", str(repo))]
    assert receipt["access_control"]["action"] == "continue"
    assert receipt["access_control"]["session_id"] == "exact-session"
    assert receipt["access_control"]["rechecked_before_dispatch"]


def test_governed_cli_continuation_rechecks_before_child(product_host, monkeypatch):
    host, repo, _ = product_host
    receipt = control.access_gate("claude", str(repo), action="continue", session_id="exact-session", controls={"approval": "default"})
    host.surface_denied.add(("claude", "continue"))
    monkeypatch.setattr(server.shutil, "which", lambda _: "/bin/claude")
    monkeypatch.setattr(server.subprocess, "run", lambda *a, **k: pytest.fail("late denial executed continuation"))
    result = server._cli_continue(contracts.get_harness("claude"), "claude", "exact-session", "task", str(repo), access_control=receipt)
    assert "ABAC denies continue" in result["error"]
