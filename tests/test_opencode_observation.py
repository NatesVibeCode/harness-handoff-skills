"""Read-only OpenCode history association tests; no real session is queried."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import subprocess
from pathlib import Path

import pytest

from mcp_bridge import server


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _binding(workspace: Path) -> dict:
    index_path = workspace / "sections.json"
    record_path = workspace / "record.json"
    index_bytes = b'{"schemaVersion":1,"sections":[]}'
    record_bytes = b'{"task":"T1","title":"Review history safely"}'
    index_path.write_bytes(index_bytes)
    record_path.write_bytes(record_bytes)
    return {
        "contract": "mdview.handoff-binding",
        "schemaVersion": 1,
        "source": {
            "index": str(index_path.resolve()),
            "section": "execution-plan",
            "record": "record.json",
            "taskId": "T1",
            "taskSha256": _sha(record_bytes),
            "expectedReadSet": {
                "@index": _sha(index_bytes),
                "record.json": _sha(record_bytes),
            },
            "expectedEdition": None,
        },
        "scope": "selected source/task binding only",
    }


def _run(coro):
    return asyncio.run(coro)


def test_opencode_history_returns_one_exactly_bound_native_observation(tmp_path, monkeypatch):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    binding = _binding(workspace)
    session_id = "ses-exact-1"
    attempt_id = "attempt-7"
    native_payload = {
        "session": {"id": session_id, "directory": str(workspace)},
        "messages": [
            {"role": "user", "time": {"created": 1730000000000}, "parts": [{"type": "text", "text": "Inspect only."}]},
            {"role": "assistant", "time": {"created": 1730000001000}, "parts": [{"type": "text", "text": "History retained exactly."}]},
        ],
    }
    calls = []

    async def fake_history(harness, requested_session, workspace=None, limit=20):
        calls.append((harness, requested_session, workspace, limit))
        return {
            "harness": "opencode",
            "route": "cli",
            "session_id": requested_session,
            "native_payload": native_payload,
        }

    monkeypatch.setattr(server, "session_history", fake_history)
    result = _run(server.opencode_handoff_observation(
        session_id=session_id,
        workspace=str(workspace),
        handoff_binding=binding,
        attempt_id=attempt_id,
    ))

    assert calls == [("opencode", session_id, str(workspace), 20)]
    assert result == {
        "contract": "work-coordination.handoff-association",
        "schemaVersion": 1,
        "handoffBinding": binding,
        "destination": {
            "selection": "operator-explicit",
            "surface": "opencode",
            "sessionId": session_id,
        },
        "attempt": {"id": attempt_id},
        "observations": [{
            "id": result["observations"][0]["id"],
            "origin": {"surface": "opencode", "sessionId": session_id, "attemptId": attempt_id},
            "observedAt": result["observations"][0]["observedAt"],
            "nativeKind": "opencode.session_history",
            "nativeValue": native_payload,
        }],
    }
    assert re.fullmatch(r"opencode-history-[a-f0-9]{64}", result["observations"][0]["id"])
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z", result["observations"][0]["observedAt"])
    assert "status" not in result
    assert "completion" not in result
    assert result["observations"][0]["nativeValue"] == native_payload


def test_opencode_history_refuses_malformed_or_stale_binding_before_history_lookup(tmp_path, monkeypatch):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    binding = _binding(workspace)
    monkeypatch.setattr(server, "session_history", lambda *args, **kwargs: pytest.fail("history must not be queried"))

    malformed = {**binding, "unexpected": True}
    result = _run(server.opencode_handoff_observation("ses-exact-1", str(workspace), malformed, "attempt-7"))
    assert result["refused"] is True
    assert "fields are malformed" in result["reason"]

    (workspace / "record.json").write_text('{"task":"T1","title":"Changed after handoff"}', encoding="utf-8")
    result = _run(server.opencode_handoff_observation("ses-exact-1", str(workspace), binding, "attempt-7"))
    assert result["refused"] is True
    assert "stale" in result["reason"]


def test_opencode_history_requires_explicit_workspace_and_exact_session(tmp_path, monkeypatch):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    binding = _binding(workspace)
    monkeypatch.setattr(server, "session_history", lambda *args, **kwargs: pytest.fail("history must not be queried"))

    for session_id, selected_workspace in [("latest", str(workspace)), ("ses-exact-1", "")]:
        result = _run(server.opencode_handoff_observation(
            session_id=session_id,
            workspace=selected_workspace,
            handoff_binding=binding,
            attempt_id="attempt-7",
        ))
        assert result["refused"] is True


def test_unavailable_session_history_refuses_without_a_synthetic_association(tmp_path, monkeypatch):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    binding = _binding(workspace)

    async def unavailable(*args, **kwargs):
        return {"refused": True, "reason": "history unavailable"}

    monkeypatch.setattr(server, "session_history", unavailable)
    result = _run(server.opencode_handoff_observation("ses-exact-1", str(workspace), binding, "attempt-7"))
    assert result == {"refused": True, "reason": "OpenCode history is unavailable for the selected session"}


def test_session_history_uses_only_exact_sanitized_export_in_selected_workspace(tmp_path, monkeypatch):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    native_payload = {"session": {"id": "ses-exact-1"}, "messages": [{"time": 1730000000, "text": "fixture"}]}
    calls = []
    monkeypatch.setattr(server.shutil, "which", lambda binary: "/fixture/opencode" if binary == "opencode" else None)

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, 0, json.dumps(native_payload), "")

    monkeypatch.setattr(server.subprocess, "run", fake_run)
    result = _run(server.session_history("opencode", "ses-exact-1", workspace=str(workspace)))

    assert result["native_payload"] == native_payload
    assert calls == [(["/fixture/opencode", "export", "ses-exact-1", "--sanitize"], {
        "cwd": str(workspace.resolve()), "capture_output": True, "text": True,
    })]
