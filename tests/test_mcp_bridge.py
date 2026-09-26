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

from mcp_bridge import cli_executor, contracts, sdk_executors
from mcp_bridge.server import _choose_route, _cli_continue, handoff_continue, session_history


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


# --- CLI execution (mocked) -----------------------------------------------


class _Completed:
    def __init__(self, stdout="", stderr="", returncode=0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


def test_missing_binary_is_a_clean_error(monkeypatch):
    monkeypatch.setattr(cli_executor.shutil, "which", lambda _: None)
    with pytest.raises(cli_executor.ExecutionError, match="not installed"):
        cli_executor.run_cli(_entry("amp"), prompt="hi")


def test_receipt_redacts_secrets_and_extracts_session_id(monkeypatch):
    monkeypatch.setattr(cli_executor.shutil, "which", lambda _: "/bin/amp")
    stdout = '{"session_id": "ses-123", "answer": "ok"} sk-SECRETSECRETSECRET'
    monkeypatch.setattr(
        cli_executor.subprocess, "run", lambda *a, **k: _Completed(stdout=stdout)
    )
    receipt = cli_executor.run_cli(_entry("amp"), prompt="hi")
    assert receipt["session_id"] == "ses-123"
    assert "sk-SECRETSECRETSECRET" not in receipt["output"]
    assert "[redacted-credential]" in receipt["output"]
    assert "super secret task wording" not in " ".join(receipt["argv"])


def test_prompt_text_is_not_echoed_into_the_logged_argv(monkeypatch):
    monkeypatch.setattr(cli_executor.shutil, "which", lambda _: "/bin/amp")
    monkeypatch.setattr(
        cli_executor.subprocess, "run", lambda *a, **k: _Completed(stdout="{}")
    )
    receipt = cli_executor.run_cli(_entry("amp"), prompt="super secret task wording")
    assert "super secret task wording" not in " ".join(receipt["argv"])


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


def test_cursor_sdk_route_requires_an_explicit_model():
    with pytest.raises(RuntimeError, match="explicit model"):
        run(sdk_executors.cursor_fresh("hi", None, None, "default"))
