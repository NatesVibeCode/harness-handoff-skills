"""Resolved-effect authorization with the real local evaluator and local children."""
import asyncio
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
import sys

import pytest

from mcp_bridge import cli_executor, contracts, control, launch_plan, model_settings, sdk_executors, server
from test_control_recovery import real_host


@pytest.fixture
def governed(real_host, tmp_path, monkeypatch):
    config_path, cfg = real_host
    policy = {"schema": "abac.policyfile.v1", "realm": cfg["access_context"]["realm"], "policies": [
        {"id": "projection", "effect": "allow", "priority": 1, "scope": {
            "action.operation": "handoff.project", "resource.labels.repo_id": "work"}},
        {"id": "exact-model-cli", "effect": "allow", "priority": 1, "scope": {
            "action.operation": "handoff.launch", "resource.ref": "harness-handoff/codex",
            "resource.labels.execution_route": "cli", "resource.labels.resolved_model": '"approved-model"'}},
        {"id": "claude-cli", "effect": "allow", "priority": 1, "scope": {
            "action.operation": "handoff.launch", "resource.ref": "harness-handoff/claude",
            "resource.labels.execution_route": "cli"}},
    ]}
    Path(cfg["policy_files"][0]).write_text(json.dumps(policy))
    child = tmp_path / "native-child"
    child.write_text(f'#!{sys.executable}\nimport sys,os,json\nprint(json.dumps({{"argv":sys.argv[1:],"cwd":os.getcwd()}}))\n')
    child.chmod(0o700)
    monkeypatch.setattr(launch_plan.shutil, "which", lambda _: str(child))
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex-home"))
    return cfg, child


def resolve(cfg, *, workspace=None, harness="codex", model="approved-model", prompt="private prompt", capabilities=None):
    workspace = workspace or cfg["repositories"]["work"]["path"]
    requested = {"model": model, "reasoning_effort": None, "approval": "restricted", "use": "auto"}
    context = control.access_gate(harness, workspace, action="project", controls=requested)
    return launch_plan.resolve(contracts.get_harness(harness), route="cli", prompt=prompt, workspace=workspace,
        requested=requested, native_settings={"model": model, "reasoning_effort": None, "sandbox": "read-only", "approval": "on-request"},
        extra_argv=["--model", model, "--sandbox", "read-only", "-c", 'approval_policy="on-request"'], extra_at=1,
        context=context, model_capabilities=capabilities)


def test_exact_plan_is_approved_and_consumed_by_real_child(governed):
    cfg, child = governed
    plan = resolve(cfg)
    authorization = control.authorize_launch_plan(plan)
    assert authorization["launch_plan_digest"] == plan.plan_digest
    assert authorization["effect"]["verdict"]["policy_digest"]
    receipt = cli_executor.run_cli(plan, authorization=authorization)
    actual = json.loads(receipt["output"])
    assert actual["argv"] == list(plan.argv)
    assert actual["cwd"] == plan.workspace
    assert receipt["binary"] == str(child.resolve())
    assert receipt["launch_plan"]["digest"] == receipt["access_control"]["launch_plan_digest"]
    assert receipt["access_control"]["rechecked_before_dispatch"]
    assert "private prompt" not in json.dumps(receipt["launch_plan"])


def test_actual_model_is_a_policy_attribute(governed):
    cfg, _ = governed
    plan = resolve(cfg, model="other-model")
    try:
        with pytest.raises(control.ControlError, match="ABAC denies"):
            control.authorize_launch_plan(plan)
    finally:
        plan.cleanup()


@pytest.mark.parametrize("change", ["argv", "workspace", "native_settings", "context", "adapter", "prompt"])
def test_plan_changes_cannot_reuse_approval(governed, change):
    cfg, _ = governed
    plan = resolve(cfg)
    authorization = control.authorize_launch_plan(plan)
    replacements = {
        "argv": {"argv": plan.argv + ("--model", "other-model")},
        "workspace": {"workspace": str(Path(plan.workspace).parent)},
        "native_settings": {"native_json": '{"model":"other-model"}'},
        "context": {"context_json": '{"permission_context":"other-access"}'},
        "adapter": {"adapter": "cli.other.fresh"},
        "prompt": {"prompt": "different request"},
    }
    changed = replace(plan, **replacements[change])
    with pytest.raises(cli_executor.ExecutionError, match="does not match"):
        cli_executor.run_cli(changed, authorization=authorization)


def test_plan_is_immutable_and_public_values_are_copies(governed):
    cfg, _ = governed
    plan = resolve(cfg)
    try:
        with pytest.raises(FrozenInstanceError):
            plan.workspace = "other"
        exposed = plan.public()
        exposed["native_settings"]["model"] = "other"
        assert plan.native_settings["model"] == "approved-model"
        assert plan.resolved_digest == plan.plan_digest
    finally:
        plan.cleanup()


def test_rehashed_inconsistent_native_arguments_are_not_authorized(governed):
    cfg, _ = governed
    plan = resolve(cfg)
    changed = replace(plan, argv=plan.argv + ("--model", "other-model"))
    changed = replace(changed, resolved_digest=changed.plan_digest)
    try:
        with pytest.raises(ValueError, match="arguments differ"):
            control.authorize_launch_plan(changed)
    finally:
        plan.cleanup()


def test_workspace_alias_retarget_cannot_change_execution(governed, tmp_path):
    cfg, _ = governed
    alias = tmp_path / "alias"
    alias.symlink_to(cfg["repositories"]["work"]["path"], target_is_directory=True)
    other = tmp_path / "other"
    other.mkdir()
    plan = resolve(cfg, workspace=str(alias))
    authorization = control.authorize_launch_plan(plan)
    alias.unlink()
    alias.symlink_to(other, target_is_directory=True)
    receipt = cli_executor.run_cli(plan, authorization=authorization)
    actual = json.loads(receipt["output"])
    assert actual["cwd"] == cfg["repositories"]["work"]["path"]
    assert actual["argv"][actual["argv"].index("-C") + 1] == plan.workspace


def test_executable_alias_and_path_lookup_are_not_repeated(governed, tmp_path, monkeypatch):
    cfg, child = governed
    alias = tmp_path / "executable-alias"
    alias.symlink_to(child)
    monkeypatch.setattr(launch_plan.shutil, "which", lambda _: str(alias))
    plan = resolve(cfg)
    authorization = control.authorize_launch_plan(plan)
    alias.unlink()
    alias.symlink_to(sys.executable)
    monkeypatch.setattr(launch_plan.shutil, "which", lambda _: pytest.fail("PATH resolved after authorization"))
    receipt = cli_executor.run_cli(plan, authorization=authorization)
    assert receipt["binary"] == str(child.resolve())


def test_executable_content_change_refuses_before_dispatch(governed, monkeypatch):
    cfg, child = governed
    plan = resolve(cfg)
    authorization = control.authorize_launch_plan(plan)
    child.write_text(child.read_text() + "# changed\n")
    monkeypatch.setattr(cli_executor.subprocess, "run", lambda *a, **k: pytest.fail("changed executable was invoked"))
    with pytest.raises(cli_executor.ExecutionError, match="input changed"):
        cli_executor.run_cli(plan, authorization=authorization)


def test_old_receipt_and_raw_inputs_are_not_an_execution_interface():
    with pytest.raises(TypeError):
        cli_executor.run_cli(contracts.get_harness("codex"), prompt="task", extra_argv=["--model", "other"])
    with pytest.raises(cli_executor.ExecutionError, match="LaunchPlan"):
        cli_executor.run_cli({"requested_controls": {"model": "approved-model"}})


def test_sdk_auto_route_is_resolved_before_effect_authorization(governed, monkeypatch):
    cfg, _ = governed
    async def forbidden(*args):
        pytest.fail("SDK executed despite CLI-only policy")
    monkeypatch.setattr(sdk_executors, "available", lambda _: True)
    monkeypatch.setitem(sdk_executors.EXECUTORS["claude"], "fresh", forbidden)
    result = asyncio.run(server.handoff_fresh("claude", "task", workspace=cfg["repositories"]["work"]["path"], use="auto"))
    assert result["refused"] and "ABAC denies launch" in result["reason"]


def test_sdk_consumes_captured_callable_and_canonical_options(governed, monkeypatch):
    cfg, _ = governed
    policy_path = Path(cfg["policy_files"][0])
    policy = json.loads(policy_path.read_text())
    policy["policies"][2]["scope"]["resource.labels.execution_route"] = "sdk"
    policy_path.write_text(json.dumps(policy))
    seen = []
    async def capture(prompt, workspace, model, approval):
        seen.append((prompt, workspace, model, approval))
        return {"route": "sdk", "session_id": "local-fake"}
    monkeypatch.setitem(sdk_executors.EXECUTORS["claude"], "fresh", capture)
    requested = {"model": None, "approval": "default", "use": "auto"}
    workspace = cfg["repositories"]["work"]["path"]
    context = control.access_gate("claude", workspace, action="project", controls=requested)
    plan = launch_plan.resolve(contracts.get_harness("claude"), route="sdk", prompt="SDK request", workspace=workspace,
        requested=requested, native_settings={"model": None}, context=context)
    authorization = control.authorize_launch_plan(plan)
    result = asyncio.run(sdk_executors.run_plan(plan, authorization=authorization))
    assert seen == [("SDK request", str(Path(workspace).resolve()), None, "default")]
    assert result["launch_plan"]["adapter"] == "sdk.claude.fresh"
    assert result["launch_plan"]["executable_kind"] == "python_runtime"


def test_model_evidence_is_rechecked_after_plan_was_held(governed, tmp_path, monkeypatch):
    cfg, _ = governed
    cache = tmp_path / "models.json"
    cache.write_text(json.dumps({"fetched_at": datetime.now(timezone.utc).isoformat(),
        "models": [{"slug": "approved-model", "supported_reasoning_levels": [{"effort": "high"}]}]}))
    plan = resolve(cfg, capabilities=str(cache))
    authorization = control.authorize_launch_plan(plan)
    class Later(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.now(tz) + timedelta(days=2)
    monkeypatch.setattr(model_settings, "datetime", Later)
    with pytest.raises(cli_executor.ExecutionError, match="stale"):
        cli_executor.run_cli(plan, authorization=authorization)


def test_context_or_policy_change_cannot_reuse_plan_authority(governed):
    cfg, _ = governed
    plan = resolve(cfg)
    authorization = control.authorize_launch_plan(plan)
    path = Path(cfg["policy_files"][0])
    path.write_text(path.read_text() + "\n")
    with pytest.raises(cli_executor.ExecutionError, match="host changed"):
        cli_executor.run_cli(plan, authorization=authorization)
