"""Tests for the harness SDK bridge MCP server.

Everything here runs offline: subprocesses are mocked, SDK imports are probed
but never executed, and no credentials, sessions, or model calls are touched.
"""

from __future__ import annotations

import asyncio
import sys
import types
from pathlib import Path

import pytest

from mcp_bridge import cli_executor, contracts, sdk_executors, launch_plan
from plan_helpers import execute_cli
from mcp_bridge.server import _choose_route, _cli_continue, handoff_continue, handoff_fresh, session_history


@pytest.fixture(autouse=True)
def hermetic_cli_resolution(monkeypatch):
    monkeypatch.setattr(cli_executor.shutil, "which", lambda _: sys.executable)


def _entry(name: str) -> dict:
    return contracts.get_harness(name)


def run(coro):
    return asyncio.run(coro)


# --- contracts ------------------------------------------------------------


def test_unknown_harness_is_named():
    with pytest.raises(contracts.ContractError, match="unknown harness"):
        contracts.get_harness("not-a-harness")


def test_bridge_sees_all_fourteen_harnesses():
    rows = contracts.list_harnesses()
    assert len(rows) == 14
    assert {row["harness"] for row in rows} == {
        "amp", "antigravity", "claude", "cline", "codex", "copilot", "cursor",
        "droid", "gemini", "grok", "junie", "muse", "opencode", "openhands",
    }


# --- argv building --------------------------------------------------------


def test_stdin_delivery_keeps_prompt_out_of_argv():
    argv, stdin_text, _ = cli_executor.build_argv(
        _entry("claude"), prompt="hello", workspace="/w", model=None
    )
    assert argv == ["-p", "--output-format", "json"]
    assert stdin_text == "hello"


def test_file_flag_delivery_stages_a_prompt_file():
    argv, stdin_text, temp_dir = cli_executor.build_argv(
        _entry("grok"), prompt="hello", workspace="/w", model=None
    )
    assert stdin_text is None
    assert "--prompt-file" in argv
    prompt_file = Path(argv[argv.index("--prompt-file") + 1])
    assert prompt_file.read_text(encoding="utf-8") == "hello"
    assert temp_dir is not None


def test_routed_model_is_required_when_the_contract_says_so():
    with pytest.raises(cli_executor.ExecutionError, match="explicit model"):
        cli_executor.build_argv(_entry("cursor"), prompt="hi", workspace="/w", model=None)


def test_workspace_is_required_when_the_template_says_so():
    with pytest.raises(cli_executor.ExecutionError, match="explicit workspace"):
        cli_executor.build_argv(_entry("cursor"), prompt="hi", workspace=None, model="m")


def test_codex_output_path_renders_inside_temporary_directory():
    import shutil

    argv, stdin_text, temp_dir = cli_executor.build_argv(
        _entry("codex"), prompt="task", workspace="/w", model=None
    )
    try:
        assert temp_dir is not None
        assert argv[argv.index("-o") + 1] == str(temp_dir / "final.md")
        assert stdin_text == "task"
    finally:
        shutil.rmtree(temp_dir)


# --- CLI execution (mocked) -----------------------------------------------


class _Completed:
    def __init__(self, stdout="", stderr="", returncode=0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


def test_missing_binary_is_a_clean_error(monkeypatch):
    monkeypatch.setattr(cli_executor.shutil, "which", lambda _: None)
    with pytest.raises(cli_executor.ExecutionError, match="not installed"):
        execute_cli(_entry("amp"), prompt="hi")


def test_receipt_redacts_secrets_and_extracts_session_id(monkeypatch):
    monkeypatch.setattr(cli_executor.shutil, "which", lambda _: sys.executable)
    stdout = '{"session_id": "ses-123", "answer": "ok"} sk-SECRETSECRETSECRET'
    monkeypatch.setattr(
        cli_executor.subprocess, "run", lambda *a, **k: _Completed(stdout=stdout)
    )
    receipt = execute_cli(_entry("amp"), prompt="hi")
    assert receipt["session_id"] == "ses-123"
    assert "sk-SECRETSECRETSECRET" not in receipt["output"]
    assert "[redacted-credential]" in receipt["output"]
    assert "super secret task wording" not in " ".join(receipt["argv"])


def test_prompt_text_is_not_echoed_into_the_logged_argv(monkeypatch):
    monkeypatch.setattr(cli_executor.shutil, "which", lambda _: sys.executable)
    monkeypatch.setattr(
        cli_executor.subprocess, "run", lambda *a, **k: _Completed(stdout="{}")
    )
    receipt = execute_cli(_entry("amp"), prompt="super secret task wording")
    assert "super secret task wording" not in " ".join(receipt["argv"])


def test_cli_prompt_file_is_removed_after_execution(monkeypatch):
    monkeypatch.setattr(cli_executor.shutil, "which", lambda _: sys.executable)
    staged = {}

    def fake_run(argv, **kwargs):
        staged["path"] = Path(argv[argv.index("--prompt-file") + 1])
        assert staged["path"].read_text(encoding="utf-8") == "sensitive task"
        return _Completed(stdout="{}")

    monkeypatch.setattr(cli_executor.subprocess, "run", fake_run)
    execute_cli(_entry("grok"), prompt="sensitive task", workspace="/w")
    assert not staged["path"].exists()


def test_cli_prompt_file_is_removed_after_launch_failure(monkeypatch):
    monkeypatch.setattr(cli_executor.shutil, "which", lambda _: sys.executable)
    staged = {}

    def fake_run(argv, **kwargs):
        staged["path"] = Path(argv[argv.index("--prompt-file") + 1])
        raise OSError("launch failed")

    monkeypatch.setattr(cli_executor.subprocess, "run", fake_run)
    with pytest.raises(cli_executor.ExecutionError, match="failed to launch"):
        execute_cli(_entry("grok"), prompt="sensitive task", workspace="/w")
    assert not staged["path"].exists()


def test_codex_final_message_is_in_receipt_before_cleanup(monkeypatch):
    monkeypatch.setattr(cli_executor.shutil, "which", lambda _: sys.executable)
    staged = {}

    def fake_run(argv, **kwargs):
        staged["path"] = Path(argv[argv.index("-o") + 1])
        staged["path"].write_text("completed outcome", encoding="utf-8")
        return _Completed(stdout='{"session_id":"thr-1"}')

    monkeypatch.setattr(cli_executor.subprocess, "run", fake_run)
    receipt = execute_cli(_entry("codex"), prompt="task", workspace="/w")
    assert receipt["final_message"] == "completed outcome"
    assert not staged["path"].exists()


# --- route selection ------------------------------------------------------


def test_sdk_route_falls_back_to_cli_when_unimportable(monkeypatch):
    monkeypatch.setattr(sdk_executors, "available", lambda _: False)
    assert _choose_route(_entry("claude"), "auto") == "cli"


def test_explicit_sdk_without_package_is_refused_not_attempted(monkeypatch):
    monkeypatch.setattr(sdk_executors, "available", lambda _: False)
    with pytest.raises(RuntimeError, match="not importable"):
        _choose_route(_entry("claude"), "sdk")


def test_explicit_cli_is_always_honored():
    assert _choose_route(_entry("codex"), "cli") == "cli"


def test_available_probes_imports_without_importing(monkeypatch):
    monkeypatch.setattr(sdk_executors.importlib.util, "find_spec", lambda _: None)
    assert sdk_executors.available("claude") is False


def test_fake_sdk_package_reports_available(monkeypatch):
    module = types.ModuleType("claude_agent_sdk")
    monkeypatch.setitem(sys.modules, "claude_agent_sdk", module)
    assert sdk_executors.available("claude") is True


# --- policy enforcement ---------------------------------------------------


def test_codex_continuation_is_refused_without_execution():
    result = run(handoff_continue("codex", "thr_123", "continue?"))
    assert result["refused"] is True
    assert "fresh-only" in result["reason"]


def test_continuation_requires_an_exact_session_id():
    result = run(handoff_continue("claude", "", "continue?"))
    assert result["refused"] is True


@pytest.mark.parametrize("session_id", ["latest", "continue", "--model", "../another", "bad id"])
def test_continuation_rejects_selectors_and_option_like_ids(session_id):
    result = run(handoff_continue("claude", session_id, "continue?"))
    assert result["refused"] is True


def test_unverified_cli_continuation_shapes_are_refused():
    for name in ("cline", "amp", "copilot"):
        result = _cli_continue(_entry(name), name, "id-1", "hi", None)
        assert result.get("refused") is True, name


def test_history_without_sdk_path_returns_guidance_not_an_error():
    result = run(session_history("grok", "ses-1"))
    assert result["route"] == "cli"
    assert "contract_docs" in result


def test_history_requires_an_exact_session_id():
    result = run(session_history("claude", ""))
    assert result["refused"] is True


def test_unknown_route_value_is_refused():
    from mcp_bridge.server import _choose_route

    with pytest.raises(RuntimeError, match="unknown route"):
        _choose_route(_entry("claude"), "sometimes")


def test_openhands_headless_requires_explicit_unattended_approval(monkeypatch):
    from mcp_bridge import server

    monkeypatch.setattr(server.sdk_executors, "available", lambda _: False)
    monkeypatch.setattr(server.cli_executor, "run_cli", lambda *a, **k: pytest.fail("CLI launched without authorization"))
    result = run(handoff_fresh("openhands", "task", use="cli"))
    assert result["refused"] is True
    assert "always approves" in result["reason"]
    assert run(handoff_continue("openhands", "ses-1", "task"))["refused"] is True


def test_openhands_explicit_unattended_approval_reaches_cli(monkeypatch):
    from mcp_bridge import server

    called = {}
    monkeypatch.setenv(server.UNATTENDED_ALLOWLIST_ENV, "openhands")

    def fake_run(entry, **kwargs):
        called["harness"] = entry.harness + "-harness-handoff"
        return {"route": "cli", "exit_code": 0}

    monkeypatch.setattr(server.cli_executor, "run_cli", fake_run)
    result = run(handoff_fresh("openhands", "task", approval="unattended", use="cli"))
    assert result["exit_code"] == 0
    assert called["harness"] == "openhands-harness-handoff"


def test_copilot_default_uses_cli_even_when_sdk_is_available(monkeypatch):
    from mcp_bridge import server

    monkeypatch.setattr(server.sdk_executors, "available", lambda _: True)
    monkeypatch.setattr(server.cli_executor, "run_cli", lambda *a, **k: {"route": "cli", "exit_code": 0})
    assert run(handoff_fresh("copilot", "task"))["route"] == "cli"
    refused = run(handoff_fresh("copilot", "task", use="sdk"))
    assert refused["refused"] is True


def test_copilot_sdk_requires_explicit_unattended_approval():
    with pytest.raises(RuntimeError, match="explicit unattended"):
        run(sdk_executors.copilot_fresh("task", None, None, "default"))
    with pytest.raises(RuntimeError, match="explicit unattended"):
        run(sdk_executors.copilot_resume("ses-1", "task", None))
    assert run(handoff_continue("copilot", "ses-1", "task"))["refused"] is True


def test_copilot_explicit_unattended_reaches_sdk_with_that_choice(monkeypatch):
    from mcp_bridge import server

    seen = []
    monkeypatch.setenv(server.UNATTENDED_ALLOWLIST_ENV, "copilot")

    async def fake_fresh(prompt, workspace, model, approval):
        seen.append(("fresh", approval))
        return {"route": "sdk", "session_id": "ses-1"}

    async def fake_resume(session_id, prompt, workspace, approval):
        seen.append(("resume", approval))
        return {"route": "sdk", "session_id": session_id}

    monkeypatch.setattr(server.sdk_executors, "available", lambda _: True)
    monkeypatch.setitem(server.sdk_executors.EXECUTORS, "copilot", {"fresh": fake_fresh, "resume": fake_resume, "history": None})
    assert run(handoff_fresh("copilot", "task", model="selected-model", approval="unattended"))["route"] == "sdk"
    assert run(handoff_continue("copilot", "ses-1", "task", approval="unattended"))["route"] == "sdk"
    assert seen == [("fresh", "unattended"), ("resume", "unattended")]


def test_sdk_receipt_redacts_known_credential_patterns():
    receipt = sdk_executors._receipt("demo", "ses-1", "result sk-SECRETSECRETSECRET")
    assert "sk-SECRETSECRETSECRET" not in receipt["output"]


def test_codex_approval_modes_are_explicit(monkeypatch):
    from mcp_bridge import server

    seen = {}
    monkeypatch.setenv(server.UNATTENDED_ALLOWLIST_ENV, "codex")

    def fake_run(entry, **kwargs):
        seen["argv"] = list(entry.argv)
        return {"route": "cli", "exit_code": 0}

    monkeypatch.setattr(server.cli_executor, "run_cli", fake_run)
    run(handoff_fresh("codex", "task", workspace=str(Path.cwd()), approval="restricted", use="cli"))
    assert seen["argv"][1:5] == ["--sandbox", "read-only", "-c", 'approval_policy="on-request"']
    run(handoff_fresh("codex", "task", workspace=str(Path.cwd()), use="cli"))
    assert seen["argv"][1] == "--dangerously-bypass-approvals-and-sandbox"
    run(handoff_fresh("codex", "task", workspace=str(Path.cwd()), approval="unattended", use="cli"))
    assert seen["argv"][1] == "--dangerously-bypass-approvals-and-sandbox"


def test_codex_selected_model_reaches_cli(monkeypatch):
    from mcp_bridge import server

    seen = {}
    monkeypatch.setattr(server.cli_executor, "run_cli", lambda plan, **kwargs: seen.update(argv=list(plan.argv)) or {"route": "cli"})
    run(handoff_fresh("codex", "task", workspace=str(Path.cwd()), model="selected-model", use="cli"))
    assert seen["argv"][seen["argv"].index("--model") + 1] == "selected-model"


def test_unbindable_workspace_or_model_is_refused(monkeypatch):
    from mcp_bridge import server

    monkeypatch.setenv(server.UNATTENDED_ALLOWLIST_ENV, "copilot")
    monkeypatch.setattr(server.sdk_executors, "available", lambda _: True)
    monkeypatch.setattr(server.cli_executor, "run_cli", lambda *a, **k: pytest.fail("CLI launched"))
    assert run(handoff_fresh("antigravity", "task", workspace="/w", use="sdk"))["refused"] is True
    assert run(handoff_fresh("copilot", "task", workspace="/w", model="m", approval="unattended", use="sdk"))["refused"] is True
    assert run(handoff_fresh("claude", "task", model="m", use="sdk"))["refused"] is True
    assert run(handoff_fresh("openhands", "task", use="sdk"))["refused"] is True
    assert run(handoff_continue("cursor", "ses-1", "task", workspace="/w"))["refused"] is True
    assert run(session_history("cursor", "ses-1", workspace="/w"))["refused"] is True


def test_other_unattended_routes_need_server_allowlist(monkeypatch):
    from mcp_bridge import server

    monkeypatch.delenv(server.UNATTENDED_ALLOWLIST_ENV, raising=False)
    monkeypatch.setattr(server.cli_executor, "run_cli", lambda *a, **k: pytest.fail("CLI launched"))
    result = run(handoff_fresh("openhands", "task", approval="unattended", use="cli"))
    assert result["refused"] is True
    assert server.UNATTENDED_ALLOWLIST_ENV in result["reason"]
    continued = run(handoff_continue("openhands", "ses-1", "task", approval="unattended"))
    assert continued["refused"] is True


def test_codex_dispatch_does_not_depend_on_unattended_allowlist(monkeypatch):
    from mcp_bridge import server

    monkeypatch.delenv(server.UNATTENDED_ALLOWLIST_ENV, raising=False)
    monkeypatch.setattr(server.cli_executor, "run_cli", lambda plan, **kwargs: {"route": "cli", "argv": list(plan.argv)})
    result = run(handoff_fresh("codex", "task", workspace=str(Path.cwd()), use="cli"))
    assert result["argv"][1] == "--dangerously-bypass-approvals-and-sandbox"


def test_unknown_approval_is_refused_before_launch(monkeypatch):
    from mcp_bridge import server

    monkeypatch.setattr(server.cli_executor, "run_cli", lambda *a, **k: pytest.fail("CLI launched"))
    result = run(handoff_fresh("codex", "task", approval="anything", use="cli"))
    assert result["refused"] is True


def test_opencode_continuation_stages_a_prompt_file(monkeypatch):
    from mcp_bridge import server

    monkeypatch.setattr(server.shutil, "which", lambda _: "/bin/opencode")
    seen = {}

    def fake_run(argv, **kwargs):
        seen["argv"] = argv
        file_flag = argv[argv.index("--file") + 1]
        seen["file_text"] = Path(file_flag).read_text(encoding="utf-8")
        return _Completed(stdout='{"id": "ses-9"}')

    monkeypatch.setattr(server.subprocess, "run", fake_run)
    result = server._cli_continue(_entry("opencode"), "opencode", "ses-9", "do the thing", None)
    assert seen["file_text"] == "do the thing"
    assert result["session_id"] == "ses-9"
    assert not Path(seen["argv"][seen["argv"].index("--file") + 1]).exists()


def test_cursor_sdk_route_requires_an_explicit_model():
    with pytest.raises(RuntimeError, match="explicit model"):
        run(sdk_executors.cursor_fresh("hi", None, None, "default"))
