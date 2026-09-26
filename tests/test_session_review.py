from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "session_review.py"
sys.path.insert(0, str(REPO / "scripts"))
import session_review  # noqa: E402


def run_tool(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    if env:
        merged.update(env)
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args], cwd=REPO, env=merged,
        capture_output=True, text=True, check=False,
    )


def test_local_date_window_handles_dst_and_inclusive_dates():
    window = session_review.make_window("2026-03-08", "2026-03-08", "America/Los_Angeles")
    assert window["start_utc"] == "2026-03-08T08:00:00Z"
    assert window["end_exclusive_utc"] == "2026-03-09T07:00:00Z"


@pytest.mark.parametrize(
    ("from_value", "through_value", "zone"),
    [("2026-09-02", "2026-09-01", "UTC"), ("2026-09-01", "2026-09-02", "Not/A_Zone")],
)
def test_invalid_windows_fail_clearly(from_value, through_value, zone):
    with pytest.raises(ValueError):
        session_review.make_window(from_value, through_value, zone)


def test_codex_inventory_emits_metadata_not_session_text(tmp_path):
    codex_home = tmp_path / "codex-home"
    sessions = codex_home / "sessions" / "2026" / "09"
    sessions.mkdir(parents=True)
    workspace = tmp_path / "private-project-name"
    workspace.mkdir()
    path = sessions / "rollout-test-thread.jsonl"
    lines = [
        {"type": "session_meta", "payload": {"id": "thread-123", "session_id": "thread-123", "cwd": str(workspace)}},
        {"type": "event_msg", "timestamp": "2026-09-25T22:00:00-07:00", "message": "PRIVATE TRANSCRIPT"},
        {"type": "turn.completed", "timestamp": "2026-09-26T05:30:00Z", "secret": "sk-private-value"},
    ]
    path.write_text("".join(json.dumps(line) + "\n" for line in lines), encoding="utf-8")

    result = run_tool(
        "inventory", "--from", "2026-09-25", "--through", "2026-09-25",
        "--timezone", "America/Los_Angeles", "--harness", "codex",
        "--workspace", str(workspace), "--codex-home", str(codex_home),
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["window"]["end_exclusive_utc"] == "2026-09-26T07:00:00Z"
    assert len(report["sessions"]) == 1
    session = report["sessions"][0]
    assert session["session_ref"] == "thread-123"
    assert session["window_match"] == "in_window"
    assert session["recorded_terminal_event"] == "turn.completed"
    assert session["workspace_group"].startswith("workspace-")
    assert str(workspace) not in result.stdout
    assert "private-project-name" not in result.stdout
    assert "PRIVATE TRANSCRIPT" not in result.stdout
    assert "sk-private-value" not in result.stdout
    assert report["transcript_text_emitted"] is False
    assert report["persistent_write"] is False


def test_codex_timestamp_falls_back_to_file_mtime(tmp_path):
    root = tmp_path / "codex" / "sessions"
    root.mkdir(parents=True)
    path = root / "session.jsonl"
    path.write_text(json.dumps({"type": "session_meta", "payload": {"id": "mtime-id", "cwd": str(tmp_path)}}) + "\n", encoding="utf-8")
    stamp = datetime(2026, 9, 25, 12, tzinfo=timezone.utc).timestamp()
    os.utime(path, (stamp, stamp))
    window = session_review.make_window("2026-09-25", "2026-09-25", "UTC")
    sessions, coverage = session_review.scan_codex(window, None, str(tmp_path / "codex"))
    assert coverage["complete"] is False
    assert coverage["status"] == "partial"
    assert sessions[0]["timestamp_source"] == "filesystem_mtime"
    assert sessions[0]["window_match"] == "in_window"


def test_codex_missing_local_store_is_reported_without_needing_cli(tmp_path):
    window = session_review.make_window("2026-09-01", "2026-09-02", "UTC")
    sessions, coverage = session_review.scan_codex(window, None, str(tmp_path / "missing"))
    assert sessions == []
    assert coverage["status"] == "data_unavailable"
    assert coverage["complete"] is False


def test_codex_scans_all_files_in_active_and_archived_roots_without_a_session_cap(tmp_path):
    home = tmp_path / "codex"
    active = home / "sessions"
    archived = home / "archived_sessions"
    active.mkdir(parents=True)
    archived.mkdir(parents=True)
    stamp = "2026-09-25T12:00:00Z"
    for index in range(12):
        root = archived if index == 11 else active
        path = root / f"session-{index}.jsonl"
        path.write_text(
            json.dumps({"type": "session_meta", "payload": {"id": f"session-{index}", "timestamp": stamp}}) + "\n"
            + json.dumps({"type": "turn.completed", "timestamp": stamp}) + "\n",
            encoding="utf-8",
        )
    window = session_review.make_window("2026-09-25", "2026-09-25", "UTC")
    sessions, coverage = session_review.scan_codex(window, None, str(home))
    assert len(sessions) == 12
    assert coverage["files_scanned"] == 12
    assert coverage["files_scanned_by_partition"] == {"active": 11, "archived": 1}
    assert any(item["session_ref"] == "session-11" for item in sessions)


def test_exact_codex_session_duplicates_collapse_and_conflicts_remain_visible(tmp_path):
    root = tmp_path / "codex" / "sessions"
    root.mkdir(parents=True)
    for filename, event_type, stamp in (
        ("copy-one.jsonl", "turn.completed", "2026-09-25T10:00:00Z"),
        ("copy-two.jsonl", "turn.failed", "2026-09-25T11:00:00Z"),
    ):
        path = root / filename
        path.write_text(
            json.dumps({"type": "session_meta", "payload": {"id": "duplicate-id", "cwd": str(tmp_path)}}) + "\n"
            + json.dumps({"type": event_type, "timestamp": stamp}) + "\n",
            encoding="utf-8",
        )
    window = session_review.make_window("2026-09-25", "2026-09-25", "UTC")
    sessions, coverage = session_review.scan_codex(window, None, str(tmp_path / "codex"))
    deduplicated, counts, conflicts = session_review.deduplicate_sessions(sessions)
    assert len(deduplicated) == 1
    assert counts == {"codex": 1}
    assert deduplicated[0]["duplicate_observations"] == 2
    assert deduplicated[0]["recorded_terminal_event"] == "conflicting_observations"
    assert any("conflicting terminal-event" in item for item in conflicts)
    assert coverage["complete"] is True


def _make_opencode_db(path: Path, rows: list[tuple]):
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE session (id TEXT PRIMARY KEY, parent_id TEXT, directory TEXT, time_created INTEGER, time_updated INTEGER, title TEXT, cost REAL)")
        db.executemany("INSERT INTO session VALUES (?,?,?,?,?,?,?)", rows)


def test_opencode_inventory_reads_unbounded_local_db_metadata_without_output_cap(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    db_path = tmp_path / "opencode.db"
    created = int(datetime(2026, 9, 25, 10, tzinfo=timezone.utc).timestamp() * 1000)
    updated = int(datetime(2026, 9, 25, 12, tzinfo=timezone.utc).timestamp() * 1000)
    rows = [(f"ses-{i}", "ses-parent" if i == 0 else None, str(workspace), created, updated, "PRIVATE TITLE", 123.4) for i in range(1200)]
    _make_opencode_db(db_path, rows)
    result = run_tool(
        "inventory", "--from", "2026-09-20", "--through", "2026-09-25",
        "--timezone", "UTC", "--harness", "opencode", "--workspace", str(workspace), "--opencode-db", str(db_path),
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["coverage"]["opencode"]["status"] == "complete"
    assert len(report["sessions"]) == 1200
    assert report["sessions"][0]["session_ref"] == "ses-0"
    assert report["sessions"][0]["parent_session_ref"] == "ses-parent"
    assert report["sessions"][0]["window_match"] == "in_window"
    assert "PRIVATE TITLE" not in result.stdout
    assert "123.4" not in result.stdout


def test_opencode_database_path_is_resolved_through_native_cli(tmp_path):
    db_path = tmp_path / "opencode.db"
    created = int(datetime(2026, 9, 25, 10, tzinfo=timezone.utc).timestamp() * 1000)
    _make_opencode_db(db_path, [("ses-native", None, str(tmp_path), created, created, "private", 0)])
    cli = tmp_path / "opencode"
    cli.write_text(f"#!/bin/sh\n[ \"$1 $2\" = \"db path\" ] || exit 7\nprintf '%s\\n' '{db_path}'\n", encoding="utf-8")
    cli.chmod(0o700)
    window = session_review.make_window("2026-09-25", "2026-09-25", "UTC")
    sessions, coverage = session_review.scan_opencode(window, None, str(cli))
    assert sessions[0]["session_ref"] == "ses-native"
    assert coverage["database_path_source"] == "opencode db path"


def test_opencode_missing_cli_is_a_coverage_result(tmp_path):
    window = session_review.make_window("2026-09-01", "2026-09-02", "UTC")
    sessions, coverage = session_review.scan_opencode(window, None, str(tmp_path / "missing-opencode"))
    assert sessions == []
    assert coverage["status"] == "cli_unavailable"
    assert coverage["complete"] is False


def test_opencode_unknown_time_is_not_counted_as_in_window(tmp_path):
    db_path = tmp_path / "opencode.db"
    created = int(datetime(2026, 9, 1, 12, tzinfo=timezone.utc).timestamp() * 1000)
    _make_opencode_db(db_path, [("ses-unknown", None, str(tmp_path), created, None, "hidden", 0)])
    window = session_review.make_window("2026-09-01", "2026-09-02", "UTC")
    sessions, coverage = session_review.scan_opencode(window, None, "opencode", str(db_path))
    assert sessions[0]["window_match"] == "unknown"
    assert coverage["matched_in_window"] == 0
    assert coverage["unknown_time_included"] == 1
    assert coverage["complete"] is False


def _make_muse_index(path: Path, rows: list[tuple]):
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE sessions (session_id TEXT PRIMARY KEY, workspace_root TEXT, created_at_us INTEGER, updated_at_us INTEGER, indexed_at_us INTEGER, status TEXT, latest_segment_terminated INTEGER, search_text TEXT NOT NULL DEFAULT '', title TEXT NOT NULL DEFAULT '')")
        db.executemany("INSERT INTO sessions(session_id, workspace_root, created_at_us, updated_at_us, indexed_at_us, status, latest_segment_terminated) VALUES (?,?,?,?,?,?,?)", rows)


def test_muse_inventory_discovers_full_local_index_and_filters_ids(tmp_path):
    index = tmp_path / "session-index.db"
    workspace = tmp_path / "project"
    workspace.mkdir()
    created = int(datetime(2026, 9, 25, 10, tzinfo=timezone.utc).timestamp() * 1_000_000)
    updated = int(datetime(2026, 9, 25, 12, tzinfo=timezone.utc).timestamp() * 1_000_000)
    rows = [(f"muse-session-{i}", str(workspace), created, updated, updated, "valid", 1) for i in range(1100)]
    _make_muse_index(index, rows)
    window = session_review.make_window("2026-09-25", "2026-09-25", "UTC")
    sessions, coverage = session_review.scan_muse(window, str(workspace), [], str(index))
    assert len(sessions) == 1100
    assert coverage["status"] == "complete"
    assert coverage["matched_in_window"] == 1100
    assert sessions[0]["latest_segment_terminated"] is True
    filtered, filtered_coverage = session_review.scan_muse(window, None, ["muse-session-1099"], str(index))
    assert [item["session_ref"] for item in filtered] == ["muse-session-1099"]
    assert filtered_coverage["status"] == "complete"


def test_muse_missing_index_reports_discovery_error(tmp_path):
    window = session_review.make_window("2026-09-25", "2026-09-25", "UTC")
    sessions, coverage = session_review.scan_muse(window, None, [], str(tmp_path / "missing.db"))
    assert sessions == []
    assert coverage["status"] == "data_unavailable"
    assert coverage["complete"] is False


def test_nonexistent_workspace_is_a_usage_error(tmp_path):
    result = run_tool(
        "inventory", "--from", "2026-09-01", "--through", "2026-09-02",
        "--workspace", str(tmp_path / "missing"),
    )
    assert result.returncode == 2
    assert "existing local directory" in result.stderr


def test_muse_rejects_path_like_session_ids_without_running_cli():
    window = session_review.make_window("2026-09-25", "2026-09-25", "UTC")
    index = Path(__file__).parent / "missing-muse-index.db"
    sessions, coverage = session_review.scan_muse(window, None, ["../private/file"], str(index))
    assert sessions == []
    assert coverage["status"] == "data_unavailable"


def _write_codex_message(path: Path, session_id: str, directory: str, text: str):
    events = [
        {"type": "session_meta", "timestamp": "2026-09-25T10:00:00Z", "payload": {"id": session_id, "cwd": directory}},
        {"type": "response_item", "timestamp": "2026-09-25T10:01:00Z", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": text}]}},
        {"type": "turn.completed", "timestamp": "2026-09-25T10:02:00Z"},
    ]
    path.write_text("".join(json.dumps(event) + "\n" for event in events), encoding="utf-8")


def test_search_fts_phrase_and_current_filetree_default(tmp_path):
    codex_home = tmp_path / "codex"
    (codex_home / "sessions").mkdir(parents=True)
    outside = tmp_path / "outside-tree"
    outside.mkdir()
    _write_codex_message(codex_home / "sessions" / "inside.jsonl", "inside-123", str(REPO), "invoice workflow failure follow-up")
    _write_codex_message(codex_home / "sessions" / "outside.jsonl", "outside-456", str(outside), "invoice workflow failure follow-up")
    phrase = run_tool(
        "--codex-binary", "codex", "search", "invoice workflow", "--mode", "phrase",
        "--harness", "codex", "--codex-home", str(codex_home),
    )
    assert phrase.returncode == 0, phrase.stderr
    report = json.loads(phrase.stdout)
    assert report["scope"] == "current_filetree"
    assert "query" not in report
    assert report["filetree_filter_applied"] is True
    assert [row["session_ref"] for row in report["results"]] == ["inside-123"]
    assert "excerpt" not in report["results"][0]
    assert report["transcript_text_emitted"] is False
    assert report["engine"].startswith("ephemeral SQLite FTS5")
    assert report["persistent_write"] is False
    assert report["provider_calls"] == 0

    excerpted = run_tool(
        "search", "invoice workflow", "--mode", "phrase", "--show-excerpts",
        "--harness", "codex", "--codex-home", str(codex_home),
    )
    assert excerpted.returncode == 0, excerpted.stderr
    excerpt_report = json.loads(excerpted.stdout)
    assert "⟦invoice workflow⟧" in excerpt_report["results"][0]["excerpt"]
    assert excerpt_report["transcript_text_emitted"] is True

    any_word = run_tool(
        "search", "invoice missing", "--mode", "any", "--harness", "codex",
        "--codex-home", str(codex_home), "--scope", "all", "--limit", "10",
    )
    assert any_word.returncode == 0, any_word.stderr
    all_word = run_tool(
        "search", "invoice missing", "--mode", "all", "--harness", "codex",
        "--codex-home", str(codex_home), "--scope", "all", "--limit", "10",
    )
    assert all_word.returncode == 0, all_word.stderr
    assert len(json.loads(any_word.stdout)["results"]) == 2
    assert json.loads(all_word.stdout)["results"] == []


def test_search_muse_uses_local_indexed_search_text(tmp_path):
    index = tmp_path / "session-index.db"
    created = int(datetime(2026, 9, 25, 10, tzinfo=timezone.utc).timestamp() * 1_000_000)
    _make_muse_index(index, [("muse-search-1", str(REPO), created, created, created, "valid", 1)])
    with sqlite3.connect(index) as db:
        db.execute("UPDATE sessions SET search_text=? WHERE session_id=?", ("A distinctive payment reconciliation outcome.", "muse-search-1"))
    result = run_tool("search", "payment reconciliation", "--mode", "all", "--show-excerpts", "--harness", "muse", "--muse-index", str(index))
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert [row["session_ref"] for row in report["results"]] == ["muse-search-1"]
    assert "payment" in report["results"][0]["excerpt"]


def test_search_reports_missing_codex_store_as_coverage_gap(tmp_path):
    result = run_tool("search", "invoice", "--harness", "codex", "--codex-home", str(tmp_path / "missing"))
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["results"] == []
    assert report["coverage"]["codex"]["status"] == "data_unavailable"


def test_filetree_scope_rejects_relative_session_paths():
    assert session_review.path_is_within_tree(".", str(REPO)) is False
    assert session_review.path_is_within_tree(str(REPO), str(REPO)) is True


def test_invalid_scope_setting_cannot_widen_search(tmp_path):
    result = run_tool(
        "search", "invoice", "--harness", "codex", "--codex-home", str(tmp_path / "missing"),
        env={"HARNESS_SESSION_REVIEW_SCOPE": "everything"},
    )
    assert result.returncode != 0
    assert "scope must be current-filetree or all" in result.stderr


def test_all_terms_can_match_different_turns_of_one_session(tmp_path):
    codex_home = tmp_path / "codex"
    root = codex_home / "sessions"
    root.mkdir(parents=True)
    path = root / "split.jsonl"
    _write_codex_message(path, "split-terms", str(REPO), "invoice approved")
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({"type": "response_item", "timestamp": "2026-09-25T10:03:00Z", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "workflow complete"}]}}) + "\n")
    result = run_tool("search", "invoice workflow", "--mode", "all", "--harness", "codex", "--codex-home", str(codex_home))
    assert result.returncode == 0, result.stderr
    assert [row["session_ref"] for row in json.loads(result.stdout)["results"]] == ["split-terms"]


def test_search_opencode_indexes_visible_user_assistant_text_only(tmp_path):
    db_path = tmp_path / "opencode.db"
    _make_opencode_db(db_path, [("ses-search-1", None, str(REPO), 1790330400000, 1790330400000, "Private title", 0)])
    with sqlite3.connect(db_path) as db:
        db.execute("CREATE TABLE message(id TEXT PRIMARY KEY,session_id TEXT,role TEXT,data TEXT,time_created INTEGER)")
        db.execute("CREATE TABLE part(id TEXT PRIMARY KEY,session_id TEXT,message_id TEXT,data TEXT,time_created INTEGER)")
        db.execute("INSERT INTO message VALUES(?,?,?,?,?)", ("msg-1", "ses-search-1", "user", json.dumps({"role": "user"}), 1790330400000))
        db.execute("INSERT INTO message VALUES(?,?,?,?,?)", ("msg-2", "ses-search-1", "assistant", json.dumps({"role": "assistant"}), 1790330400000))
        db.execute("INSERT INTO message VALUES(?,?,?,?,?)", ("msg-3", "ses-search-1", "assistant", json.dumps({"role": "assistant"}), 1790330400000))
        db.execute("INSERT INTO part VALUES(?,?,?,?,?)", ("part-1", "ses-search-1", "msg-1", json.dumps({"type": "text", "text": "Unique customer invoice process"}), 1790330400000))
        db.execute("INSERT INTO part VALUES(?,?,?,?,?)", ("part-2", "ses-search-1", "msg-2", json.dumps({"type": "text", "text": "Verified invoice workflow"}), 1790330400000))
        db.execute("INSERT INTO part VALUES(?,?,?,?,?)", ("part-3", "ses-search-1", "msg-3", json.dumps({"type": "reasoning", "text": "SECRET REASONING TERM"}), 1790330400000))
    result = run_tool("search", "invoice workflow", "--mode", "all", "--harness", "opencode", "--opencode-db", str(db_path))
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert [row["session_ref"] for row in report["results"]] == ["ses-search-1"]
    assert "SECRET REASONING TERM" not in result.stdout


def test_diagnostics_use_only_safe_local_surfaces(monkeypatch):
    calls = []
    monkeypatch.setattr(session_review.shutil, "which", lambda binary: f"/fake/{binary}")

    def fake_run(argv, timeout=10):
        calls.append(argv)
        if argv[-1] == "--version":
            return 0, b"fake 1.0\n", None
        if argv[1:3] == ["login", "status"]:
            return 0, b"Logged in using hidden-account@example.test", None
        if argv[1:3] == ["auth", "list"]:
            return 0, b"SECRET_PROVIDER_DETAILS", None
        if argv[1:3] == ["config", "status"]:
            return 0, b"PRIVATE_CONFIG_DETAILS", None
        raise AssertionError(f"unexpected health command: {argv}")

    monkeypatch.setattr(session_review, "_run_suppressed", fake_run)
    args = type("Args", (), {"codex_binary": "codex", "muse_binary": "muse", "opencode_binary": "opencode"})()
    report = session_review.diagnose(args)
    rendered = json.dumps(report)
    assert report["harnesses"]["codex"]["authentication"]["status"] == "logged_in"
    assert report["harnesses"]["opencode"]["authentication"]["status"] == "auth_list_command_succeeded"
    assert report["provider_probe"].startswith("not_run")
    assert "hidden-account@example.test" not in rendered
    assert "SECRET_PROVIDER_DETAILS" not in rendered
    assert "PRIVATE_CONFIG_DETAILS" not in rendered
    assert all("exec" not in call for call in calls)


def test_report_schema_covers_required_review_sections():
    schema = json.loads((REPO / "skills-src" / "session-review-output.schema.json").read_text(encoding="utf-8"))
    required = set(schema["required"])
    assert {
        "window", "coverage", "workstreams", "accomplishments", "open_work",
        "evidence", "strengths", "weaknesses", "next_actions", "harness_health",
        "costs", "limitations", "operator_confirmed_closures",
    }.issubset(required)
    assert "explicitly_open" in schema["properties"]["open_work"]["items"]["properties"]["state"]["enum"]
    assert "unknown" in schema["properties"]["open_work"]["items"]["properties"]["state"]["enum"]
