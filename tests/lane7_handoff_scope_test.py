"""Lane 7: muse CLI continuation is refused (no documented headless
resume-with-prompt), and the codex skill prose matches its fresh-only
contract."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from mcp_bridge import contracts, sdk_executors
from mcp_bridge.server import _cli_continue, handoff_continue

ROOT = Path(__file__).resolve().parent.parent


def run(coro):
    return asyncio.run(coro)


def test_lane7_muse_cli_continue_is_refused_without_execution(monkeypatch):
    from mcp_bridge import server

    def fail_run(*args, **kwargs):
        raise AssertionError(f"refused continuation executed: {args!r}")

    monkeypatch.setattr(server.subprocess, "run", fail_run)
    result = _cli_continue(contracts.get_harness("muse"), "muse", "sess-1", "hi", None)
    assert result.get("refused") is True
    assert "muse resume" in result["reason"]


def test_lane7_muse_continue_without_sdk_is_refused(monkeypatch):
    monkeypatch.setattr(sdk_executors.importlib.util, "find_spec", lambda _: None)
    result = run(handoff_continue("muse", "sess-1", "continue?"))
    assert result.get("refused") is True


def test_lane7_codex_prose_matches_fresh_only_contract():
    contract = json.loads((ROOT / "codex-harness-handoff" / "contract.json").read_text())
    assert contract["sdk"]["continuation"] == "forbidden"
    assert "resume" in contract["sdk"]["forbidden_operations"]
    assert "fork" in contract["sdk"]["forbidden_operations"]
    prose = (ROOT / "codex-harness-handoff" / "SKILL.md").read_text()
    assert "codex exec resume" in prose and "forbidden" in prose
    programmatic = prose.split("## Programmatic execution", 1)[1]
    programmatic = programmatic.split("## ", 1)[0]
    assert "use only its Start" in programmatic
    assert "continuation is forbidden here" in programmatic


def test_lane7_muse_prose_no_longer_advertises_resume():
    prose = (ROOT / "muse-harness-handoff" / "SKILL.md").read_text()
    programmatic = prose.split("## Programmatic execution", 1)[1]
    programmatic = programmatic.split("## ", 1)[0]
    assert "Resume is unsupported" in programmatic
    assert "does not resume history" in programmatic
