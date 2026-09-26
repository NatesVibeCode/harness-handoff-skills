#!/usr/bin/env python3
"""Read-only inventory, optional local text search, and health checks.

Inventory emits metadata only. Search emits text excerpts only when requested.
Neither command invokes a provider, resumes a session, or writes a review ledger.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


VERSION = 1
HARNESS_NAMES = ("codex", "muse", "opencode")
VERSION_TOKEN = re.compile(r"\b\d+\.\d+(?:\.\d+)?(?:[-+][A-Za-z0-9.]+)?\b")


def _utc_string(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _local_midnight(day: date, zone: ZoneInfo) -> datetime:
    local = datetime.combine(day, time.min).replace(tzinfo=zone)
    # Reject a skipped local date instead of silently applying ZoneInfo's
    # normalization to a different calendar boundary.
    if local.astimezone(timezone.utc).astimezone(zone).date() != day:
        raise ValueError(f"date {day.isoformat()} does not exist in timezone {zone.key}")
    return local


def make_window(from_value: str, through_value: str, timezone_name: str) -> dict[str, Any]:
    try:
        start_date = date.fromisoformat(from_value)
        through_date = date.fromisoformat(through_value)
    except ValueError as exc:
        raise ValueError("--from and --through must be calendar dates in YYYY-MM-DD form") from exc
    if start_date > through_date:
        raise ValueError("--from must be on or before --through")
    try:
        zone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"unknown IANA timezone: {timezone_name}") from exc
    start_local = _local_midnight(start_date, zone)
    try:
        end_local = _local_midnight(through_date + timedelta(days=1), zone)
    except OverflowError as exc:
        raise ValueError("--through is outside the supported calendar range") from exc
    return {
        "from_inclusive": start_date.isoformat(),
        "through_inclusive": through_date.isoformat(),
        "timezone": zone.key,
        "start_local": start_local.isoformat(),
        "end_exclusive_local": end_local.isoformat(),
        "start_utc": _utc_string(start_local),
        "end_exclusive_utc": _utc_string(end_local),
        "_start": start_local.astimezone(timezone.utc),
        "_end": end_local.astimezone(timezone.utc),
        "_zone": zone,
    }


def parse_timestamp(value: Any, zone: ZoneInfo) -> tuple[datetime | None, str | None]:
    """Parse ISO timestamps or Unix seconds/milliseconds without guessing silently."""
    if isinstance(value, bool) or value is None:
        return None, None
    try:
        if isinstance(value, (int, float)):
            stamp = float(value)
            if abs(stamp) > 100_000_000_000:
                stamp /= 1000
            return datetime.fromtimestamp(stamp, timezone.utc), "unix_epoch"
        if not isinstance(value, str) or not value.strip():
            return None, None
        raw = value.strip()
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        parsed = datetime.fromisoformat(raw)
        source = "iso8601"
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=zone)
            source = "iso8601_assumed_review_timezone"
        return parsed.astimezone(timezone.utc), source
    except (ValueError, OverflowError, OSError):
        return None, None


def in_window(value: datetime | None, window: dict[str, Any]) -> bool | None:
    if value is None:
        return None
    return window["_start"] <= value < window["_end"]


def workspace_identity(path_value: str | None) -> str | None:
    if not path_value:
        return None
    try:
        resolved = os.path.normcase(os.path.realpath(os.path.abspath(os.path.expanduser(path_value))))
    except (OSError, ValueError):
        resolved = os.path.normcase(os.path.abspath(path_value))
    digest = hashlib.sha256(resolved.encode("utf-8", "surrogateescape")).hexdigest()[:12]
    return f"workspace-{digest}"


def path_is_within_tree(candidate: str | None, tree_root: str | None) -> bool:
    if not tree_root:
        return True
    if not candidate:
        return False
    if not Path(candidate).is_absolute():
        return False
    try:
        candidate_path = os.path.normcase(os.path.realpath(os.path.abspath(os.path.expanduser(candidate))))
        root_path = os.path.normcase(os.path.realpath(os.path.abspath(os.path.expanduser(tree_root))))
        return candidate_path == root_path or candidate_path.startswith(root_path.rstrip(os.sep) + os.sep)
    except (OSError, ValueError):
        return os.path.normcase(candidate) == os.path.normcase(tree_root)


def _meta_from_codex_line(line: bytes) -> dict[str, Any] | None:
    try:
        event = json.loads(line)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError):
        return None
    if not isinstance(event, dict) or event.get("type") != "session_meta":
        return None
    payload = event.get("payload")
    if not isinstance(payload, dict):
        return None
    session_id = payload.get("session_id") or payload.get("id")
    if not isinstance(session_id, str) or not session_id:
        return None
    return {
        "session_id": session_id,
        "workspace": payload.get("cwd") if isinstance(payload.get("cwd"), str) else None,
        "parent": payload.get("parent_thread_id") or payload.get("parent_id"),
        "timestamp": event.get("timestamp") or payload.get("timestamp"),
    }


def parse_codex_file(path: Path, zone: ZoneInfo) -> tuple[dict[str, Any] | None, list[str]]:
    warnings: list[str] = []
    try:
        stat = path.stat()
        first_meta = None
        first_time = None
        last_time = None
        last_timestamp_source = None
        last_event_type = None
        event_count = 0
        with path.open("rb") as file:
            first = file.readline()
            first_meta = _meta_from_codex_line(first)
            if first_meta is None:
                return None, ["leading session metadata line missing or invalid"]
            if first_meta.get("timestamp") is not None:
                first_time, _ = parse_timestamp(first_meta["timestamp"], zone)
                last_time = first_time
                last_timestamp_source = "session_event_timestamp"
            for raw_line in file:
                event_count += 1
                try:
                    event = json.loads(raw_line)
                except (UnicodeDecodeError, json.JSONDecodeError, RecursionError):
                    warnings.append("one or more event lines were not valid JSON")
                    continue
                if not isinstance(event, dict):
                    continue
                last_event_type = event.get("type")
                payload = event.get("payload")
                if last_event_type == "event_msg" and isinstance(payload, dict) and isinstance(payload.get("type"), str):
                    last_event_type = payload["type"]
                stamp, source = parse_timestamp(event.get("timestamp"), zone)
                if stamp is None:
                    if isinstance(payload, dict):
                        stamp, source = parse_timestamp(payload.get("timestamp"), zone)
                if stamp is not None:
                    if first_time is None:
                        first_time = stamp
                    last_time = stamp
                    last_timestamp_source = source
                del event
        if last_time is None:
            last_time = datetime.fromtimestamp(stat.st_mtime, timezone.utc)
            last_timestamp_source = "filesystem_mtime"
            warnings.append("no event timestamp found; used filesystem modification time")
        return {
            **first_meta,
            "start": first_time,
            "updated": last_time,
            "timestamp_source": last_timestamp_source or "filesystem_mtime",
            "recorded_terminal_event": last_event_type if last_event_type in {"turn.completed", "turn.failed", "turn.interrupted"} else "unknown",
            "event_count": event_count + 1,
        }, warnings
    except OSError:
        return None, ["session file could not be read"]


def _session_record(harness: str, session_id: str, workspace: str | None,
                    start: datetime | None, updated: datetime | None,
                    timestamp_source: str | None, window: dict[str, Any],
                    **extra: Any) -> dict[str, Any]:
    group_key = workspace_identity(workspace)
    match = in_window(updated, window)
    return {
        "harness": harness,
        "session_ref": session_id,
        "workspace_group": group_key,
        "started_at_utc": _utc_string(start) if start else None,
        "updated_at_utc": _utc_string(updated) if updated else None,
        "timestamp_source": timestamp_source or "unknown",
        "window_match": "in_window" if match is True else "out_of_window" if match is False else "unknown",
        **extra,
    }


def _note_assumed_timezone(coverage: dict[str, Any], session: dict[str, Any]) -> None:
    if "assumed_review_timezone" not in str(session.get("timestamp_source", "")):
        return
    note = "one or more source timestamps had no timezone; the requested review timezone was assumed"
    if note not in coverage["errors"]:
        coverage["errors"].append(note)
    coverage["complete"] = False
    if coverage["status"] == "complete":
        coverage["status"] = "partial"


def scan_codex(window: dict[str, Any], workspace: str | None,
               codex_home: str | None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    home = Path(codex_home or os.environ.get("CODEX_HOME") or (Path.home() / ".codex"))
    roots = [home / "sessions", home / "archived_sessions"]
    coverage = {
        "status": "complete",
        "source": "CODEX_HOME/sessions and CODEX_HOME/archived_sessions (or ~/.codex equivalents)",
        "method": "read-only streaming scan of all local *.jsonl session records; metadata and event timestamps only; does not require the CLI",
        "filetree_filter_applied": bool(workspace),
        "files_seen": 0,
        "files_scanned": 0,
        "files_scanned_by_partition": {"active": 0, "archived": 0},
        "matched_in_window": 0,
        "unknown_time_included": 0,
        "complete": True,
        "errors": [],
        "limits": ["missing event timestamps use filesystem mtime; malformed or unreadable records are reported as partial"],
    }
    existing_roots = [root for root in roots if root.exists()]
    if not existing_roots:
        coverage.update(status="data_unavailable", complete=False, errors=["Codex local sessions directory not found"])
        return [], coverage
    walk_errors: list[str] = []
    sessions: list[dict[str, Any]] = []
    for root in existing_roots:
        partition = "archived" if root.name == "archived_sessions" else "active"
        try:
            for parent, dirs, files in os.walk(root, onerror=lambda _e: walk_errors.append("a sessions directory could not be listed")):
                dirs.sort()
                for name in sorted(files):
                    if not name.endswith(".jsonl"):
                        continue
                    path = Path(parent) / name
                    try:
                        path.stat()
                    except OSError:
                        walk_errors.append("a session file could not be stat-ed")
                        continue
                    coverage["files_seen"] += 1
                    coverage["files_scanned"] += 1
                    coverage["files_scanned_by_partition"][partition] += 1
                    parsed, warnings = parse_codex_file(path, window["_zone"])
                    if warnings:
                        coverage["errors"].extend(warnings)
                        coverage["complete"] = False
                        if coverage["status"] == "complete":
                            coverage["status"] = "partial"
                    if not parsed:
                        coverage["complete"] = False
                        if coverage["status"] == "complete":
                            coverage["status"] = "partial"
                        continue
                    if not path_is_within_tree(parsed.get("workspace"), workspace):
                        continue
                    match = in_window(parsed.get("updated"), window)
                    if match is False:
                        continue
                    record = _session_record(
                        "codex", parsed["session_id"], parsed.get("workspace"), parsed.get("start"),
                        parsed.get("updated"), parsed.get("timestamp_source"), window,
                        parent_session_ref=parsed.get("parent") if isinstance(parsed.get("parent"), str) else None,
                        recorded_terminal_event=parsed.get("recorded_terminal_event", "unknown"),
                        event_count=parsed.get("event_count"),
                    )
                    _note_assumed_timezone(coverage, record)
                    sessions.append(record)
                    if record["window_match"] == "in_window":
                        coverage["matched_in_window"] += 1
                    else:
                        coverage["unknown_time_included"] += 1
        except OSError:
            walk_errors.append("a Codex sessions directory could not be read")
    if walk_errors:
        coverage["complete"] = False
        if coverage["status"] == "complete":
            coverage["status"] = "partial"
        coverage["errors"].extend(walk_errors)
    coverage["errors"] = list(dict.fromkeys(coverage["errors"]))
    return sessions, coverage


def _resolve_opencode_database(binary: str, cwd: str) -> tuple[Path | None, str | None]:
    if not shutil.which(binary):
        return None, "opencode CLI not found on PATH"
    try:
        result = subprocess.run(
            [binary, "db", "path"], cwd=cwd, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None, "opencode db path could not be read"
    if result.returncode != 0:
        return None, "opencode db path failed; output suppressed"
    try:
        value = result.stdout.decode("utf-8").strip()
        path = Path(value).expanduser()
        if not value or "\n" in value or not path.is_file():
            return None, "opencode database path was not a local file"
        return path.resolve(), None
    except (UnicodeDecodeError, OSError):
        return None, "opencode database path was invalid"


def scan_opencode(window: dict[str, Any], workspace: str | None,
                   binary: str, database_path: str | None = None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    cwd = str(Path(workspace).expanduser().resolve()) if workspace else os.getcwd()
    coverage = {
        "status": "complete",
        "source": "opencode db path + read-only SQLite session metadata query",
        "method": "read-only local database snapshot; selects IDs, parent IDs, directories, and timestamps only",
        "filetree_filter_applied": bool(workspace),
        "path_scope": "selected filetree" if workspace else "all local filetrees",
        "files_seen": None,
        "matched_in_window": 0,
        "unknown_time_included": 0,
        "complete": True,
        "errors": [],
        "limits": ["only sessions present in the local OpenCode database are visible", "a live database may change while the read-only snapshot is collected"],
    }
    resolved = Path(database_path).expanduser().resolve() if database_path else None
    if resolved is None:
        resolved, error = _resolve_opencode_database(binary, cwd)
        if error:
            status = "cli_unavailable" if not shutil.which(binary) else "database_unavailable"
            coverage.update(status=status, complete=False, errors=[error])
            return [], coverage
    coverage["database_path_source"] = "explicit override" if database_path else "opencode db path"
    try:
        connection = sqlite3.connect(resolved.as_uri() + "?mode=ro", uri=True, timeout=5)
        connection.execute("PRAGMA query_only = ON")
        connection.execute("BEGIN")
        columns = {row[1] for row in connection.execute("PRAGMA table_info(session)")}
        required = {"id", "parent_id", "directory", "time_created", "time_updated"}
        if not required.issubset(columns):
            raise sqlite3.DatabaseError("session table is missing required metadata columns")
        start_ms = int(window["_start"].timestamp() * 1000)
        end_ms = int(window["_end"].timestamp() * 1000)
        rows = connection.execute(
            "SELECT id,parent_id,directory,time_created,time_updated FROM session "
            "WHERE (time_updated >= ? AND time_updated < ?) OR "
            "(time_updated IS NULL AND time_created >= ? AND time_created < ?) "
            "ORDER BY time_updated DESC",
            (start_ms, end_ms, start_ms, end_ms),
        ).fetchall()
        connection.rollback()
        connection.close()
    except (sqlite3.Error, OSError):
        coverage.update(status="database_unreadable", complete=False, errors=["OpenCode read-only session metadata query failed"])
        return [], coverage
    coverage["files_seen"] = len(rows)
    sessions: list[dict[str, Any]] = []
    for session_id, parent_id, row_workspace, created, updated in rows:
        if not isinstance(session_id, str) or not session_id:
            coverage["complete"] = False
            coverage["status"] = "partial"
            coverage["errors"].append("a local session row did not include a valid ID")
            continue
        if not path_is_within_tree(row_workspace if isinstance(row_workspace, str) else None, workspace):
            continue
        start, start_source = parse_timestamp(created, window["_zone"])
        modified, update_source = parse_timestamp(updated, window["_zone"])
        record = _session_record(
            "opencode", session_id, row_workspace if isinstance(row_workspace, str) else None,
            start, modified, update_source or start_source, window,
            parent_session_ref=parent_id if isinstance(parent_id, str) else None,
            recorded_terminal_event="not_available_from_session_metadata",
        )
        sessions.append(record)
        if record["window_match"] == "in_window":
            coverage["matched_in_window"] += 1
        else:
            coverage["unknown_time_included"] += 1
    if any(item["window_match"] == "unknown" for item in sessions):
        coverage["complete"] = False
        coverage["status"] = "partial" if coverage["status"] == "complete" else coverage["status"]
        coverage["errors"].append("some local session rows had no usable timestamp")
    return sessions, coverage


def scan_muse(window: dict[str, Any], workspace: str | None, session_ids: list[str],
              index_path: str | None = None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    path = Path(index_path or os.environ.get("MUSE_SESSION_INDEX") or
                (Path.home() / ".local" / "share" / "muse" / "session-index.db")).expanduser()
    coverage = {
        "status": "complete",
        "source": "local Muse session-index.db, opened read-only",
        "method": "indexed session IDs, workspaces, timestamps, index status, and terminal segment marker; no transcript export",
        "filetree_filter_applied": bool(workspace),
        "files_seen": 0,
        "matched_in_window": 0,
        "unknown_time_included": 0,
        "complete": True,
        "errors": [],
        "limits": ["the Muse session index is a discovery cache and can lag changes in retained session logs"],
    }
    if not path.is_file():
        coverage.update(status="data_unavailable", complete=False, errors=["Muse local session index not found; set MUSE_SESSION_INDEX or --muse-index"])
        return [], coverage
    wanted = set(session_ids)
    try:
        connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=5)
        connection.execute("PRAGMA query_only = ON")
        connection.execute("BEGIN")
        columns = {row[1] for row in connection.execute("PRAGMA table_info(sessions)")}
        required = {"session_id", "workspace_root", "created_at_us", "updated_at_us", "indexed_at_us", "status", "latest_segment_terminated"}
        if not required.issubset(columns):
            raise sqlite3.DatabaseError("Muse sessions table is missing required index columns")
        rows = connection.execute(
            "SELECT session_id,workspace_root,created_at_us,updated_at_us,indexed_at_us,status,latest_segment_terminated "
            "FROM sessions WHERE updated_at_us >= ? AND updated_at_us < ? ORDER BY updated_at_us DESC",
            (int(window["_start"].timestamp() * 1_000_000), int(window["_end"].timestamp() * 1_000_000)),
        ).fetchall()
        connection.rollback()
        connection.close()
    except (sqlite3.Error, OSError):
        coverage.update(status="data_unreadable", complete=False, errors=["Muse session index could not be queried read-only"])
        return [], coverage
    coverage["files_seen"] = len(rows)
    coverage["index_path_source"] = "explicit override" if index_path else "MUSE_SESSION_INDEX or ~/.local/share/muse/session-index.db"
    sessions: list[dict[str, Any]] = []
    status_counts: dict[str, int] = {}
    latest_indexed = None
    for session_id, row_workspace, created, updated, indexed_at, index_status, terminated in rows:
        if wanted and session_id not in wanted:
            continue
        status_counts[index_status] = status_counts.get(index_status, 0) + 1
        indexed_time = datetime.fromtimestamp(indexed_at / 1_000_000, timezone.utc) if indexed_at is not None else None
        if indexed_time and (latest_indexed is None or indexed_time > latest_indexed):
            latest_indexed = indexed_time
        if not path_is_within_tree(row_workspace if isinstance(row_workspace, str) else None, workspace):
            continue
        start = datetime.fromtimestamp(created / 1_000_000, timezone.utc) if created is not None else None
        modified = datetime.fromtimestamp(updated / 1_000_000, timezone.utc) if updated is not None else None
        start_source = update_source = "unix_epoch_microseconds" if (created is not None or updated is not None) else None
        record = _session_record(
            "muse", session_id, row_workspace if isinstance(row_workspace, str) else None,
            start, modified, update_source or start_source, window,
            recorded_terminal_event="not_inferred_from_index",
            index_status=index_status,
            latest_segment_terminated=bool(terminated),
        )
        sessions.append(record)
        if record["window_match"] == "in_window":
            coverage["matched_in_window"] += 1
        else:
            coverage["unknown_time_included"] += 1
    coverage["index_status_counts"] = status_counts
    coverage["latest_indexed_at_utc"] = _utc_string(latest_indexed) if latest_indexed else None
    if status_counts.get("corrupt", 0):
        coverage["status"] = "partial"
        coverage["complete"] = False
        coverage["errors"].append("the index marked one or more candidate sessions corrupt")
    return sessions, coverage


def candidate_groups(sessions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in sessions:
        key = item.get("workspace_group")
        if key:
            grouped.setdefault(key, []).append(item)
    return [
        {
            "candidate_group": key,
            "basis": "exact canonical workspace path",
            "workstream_is_judgment": True,
            "session_refs": [f"{entry['harness']}:{entry['session_ref']}" for entry in sorted(rows, key=lambda r: (r["harness"], r["session_ref"]))],
        }
        for key, rows in sorted(grouped.items())
    ]


def effective_tree(scope: str, requested_tree: str | None) -> tuple[str | None, str]:
    if scope not in {"current-filetree", "all"}:
        raise ValueError("scope must be current-filetree or all; check HARNESS_SESSION_REVIEW_SCOPE")
    if requested_tree:
        return str(Path(requested_tree).expanduser().resolve()), "explicit_filetree"
    if scope == "current-filetree":
        return os.getcwd(), "current_filetree"
    return None, "all_local_workspaces"


def deduplicate_sessions(sessions: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, int], list[str]]:
    """Collapse only exact harness/session identities and retain conflicts."""
    kept: dict[tuple[str, str], dict[str, Any]] = {}
    counts: dict[str, int] = {}
    conflicts: list[str] = []
    for incoming in sessions:
        key = (incoming["harness"], incoming["session_ref"])
        current = kept.get(key)
        if current is None:
            kept[key] = dict(incoming)
            continue
        harness = incoming["harness"]
        counts[harness] = counts.get(harness, 0) + 1
        current["duplicate_observations"] = current.get("duplicate_observations", 1) + 1
        workspace_groups = set(current.get("workspace_groups_observed", []))
        workspace_groups.update(value for value in (current.get("workspace_group"), incoming.get("workspace_group")) if value)
        if len(workspace_groups) > 1:
            current["workspace_group"] = None
            current["workspace_groups_observed"] = sorted(workspace_groups)
            conflicts.append(f"{harness}:{incoming['session_ref']} appeared under multiple workspaces")
        left_status = current.get("recorded_terminal_event")
        right_status = incoming.get("recorded_terminal_event")
        terminal_conflict = bool(
            left_status and right_status and left_status != right_status
            and "not_available" not in (left_status, right_status)
            and "unknown" not in (left_status, right_status)
        )
        left_time = current.get("updated_at_utc") or ""
        right_time = incoming.get("updated_at_utc") or ""
        if right_time > left_time:
            for field in ("updated_at_utc", "timestamp_source", "window_match"):
                current[field] = incoming.get(field)
            if incoming.get("recorded_terminal_event") not in (None, "unknown", "not_available_from_session_list"):
                current["recorded_terminal_event"] = incoming["recorded_terminal_event"]
        if terminal_conflict:
            current["recorded_terminal_event"] = "conflicting_observations"
            conflicts.append(f"{harness}:{incoming['session_ref']} had conflicting terminal-event observations")
        elif left_status in (None, "unknown", "not_available_from_session_list") and right_status not in (None, "unknown", "not_available_from_session_list"):
            current["recorded_terminal_event"] = right_status
    return list(kept.values()), counts, conflicts


def inventory(args: argparse.Namespace) -> dict[str, Any]:
    window = make_window(args.from_date, args.through_date, args.timezone)
    started_at = datetime.now(timezone.utc)
    public_window = {key: value for key, value in window.items() if not key.startswith("_")}
    workspace, scope_label = effective_tree(args.scope, args.tree or args.workspace)
    chosen = list(dict.fromkeys(args.harness or HARNESS_NAMES))
    sources: dict[str, Any] = {}
    sessions: list[dict[str, Any]] = []
    for harness in chosen:
        if harness == "codex":
            found, source = scan_codex(window, workspace, args.codex_home)
        elif harness == "opencode":
            found, source = scan_opencode(window, workspace, args.opencode_binary, args.opencode_db)
        else:
            found, source = scan_muse(window, workspace, args.muse_session, args.muse_index)
        sources[harness] = source
        sessions.extend(found)
    sessions, duplicate_counts, duplicate_conflicts = deduplicate_sessions(sessions)
    for harness, count in duplicate_counts.items():
        sources[harness]["duplicates_collapsed"] = count
    if duplicate_conflicts:
        for harness, source in sources.items():
            relevant = [item for item in duplicate_conflicts if item.startswith(f"{harness}:")]
            if not relevant:
                continue
            source["errors"].extend(relevant)
            source["complete"] = False
            if source["status"] == "complete":
                source["status"] = "partial"
    sessions.sort(key=lambda row: (row.get("updated_at_utc") or "", row["harness"], row["session_ref"]))
    return {
        "schema_version": VERSION,
        "mode": "inventory",
        "collection_started_at_utc": _utc_string(started_at),
        "generated_at_utc": _utc_string(datetime.now(timezone.utc)),
        "snapshot_consistency": "best_effort; active local session files may change during the scan",
        "persistent_write": False,
        "session_state_mutation": "none",
        "temporary_exports": "none; inventory queries local metadata stores read-only",
        "transcript_text_emitted": False,
        "provider_probe": "not_run; inventory invokes no inference API and creates no agent session",
        "scope": scope_label,
        "filetree_filter_applied": workspace is not None,
        "window": public_window,
        "coverage": sources,
        "sessions": sessions,
        "candidate_groups": candidate_groups(sessions),
        "deduplication": {
            "deterministic_key": "harness + exact session ID",
            "cross_harness_merge": "not performed",
            "judgment_required": "same workspace, similar time, topic, artifact, or commit are candidate signals only",
        },
    }


def _optional_window(args: argparse.Namespace) -> dict[str, Any] | None:
    if bool(args.from_date) != bool(args.through_date):
        raise ValueError("--from and --through must be supplied together")
    if not args.from_date:
        return None
    return make_window(args.from_date, args.through_date, args.timezone)


def _search_query(query: str, mode: str) -> str:
    if mode == "fts":
        if not query.strip():
            raise ValueError("FTS query cannot be empty")
        return query
    terms = re.findall(r"[\w]+", query, flags=re.UNICODE)
    if not terms:
        raise ValueError("query must contain at least one searchable word")
    quoted = [f'"{term.replace(chr(34), chr(34) * 2)}"' for term in terms]
    if mode == "phrase":
        phrase = " ".join(terms).replace('"', '""')
        return f'"{phrase}"'
    operator = " AND " if mode == "all" else " OR "
    return operator.join(quoted)


def _add_search_doc(db: sqlite3.Connection, harness: str, session_id: str,
                    workspace: str | None, updated: datetime | None, content: str) -> bool:
    if not isinstance(content, str) or not content.strip():
        return False
    db.execute(
        "INSERT INTO search_docs(harness,session_ref,workspace_group,updated_at_utc,content) VALUES(?,?,?,?,?)",
        (harness, session_id, workspace_identity(workspace), _utc_string(updated) if updated else "", content),
    )
    return True


def _codex_search_text(event: dict[str, Any]) -> str | None:
    if event.get("type") != "response_item":
        return None
    payload = event.get("payload")
    if not isinstance(payload, dict) or payload.get("type") != "message":
        return None
    if payload.get("role") not in {"user", "assistant"}:
        return None
    content = payload.get("content")
    if not isinstance(content, list):
        return None
    pieces = [
        item.get("text") for item in content
        if isinstance(item, dict) and item.get("type") in {"input_text", "output_text", "text"}
        and isinstance(item.get("text"), str)
    ]
    return "\n".join(pieces) if pieces else None


def _search_codex(db: sqlite3.Connection, window: dict[str, Any] | None,
                  workspace: str | None, codex_home: str | None) -> dict[str, Any]:
    home = Path(codex_home or os.environ.get("CODEX_HOME") or (Path.home() / ".codex"))
    roots = [home / "sessions", home / "archived_sessions"]
    coverage = {"status": "complete", "files_scanned": 0, "sessions_scanned": 0, "documents_indexed": 0, "errors": []}
    if not any(root.is_dir() for root in roots):
        coverage.update(status="data_unavailable", errors=["Codex local session roots not found"])
        return coverage
    seen_sessions: set[str] = set()
    for root in (item for item in roots if item.is_dir()):
        try:
            walk = os.walk(root, onerror=lambda _error: coverage["errors"].append("a Codex session directory could not be read"))
            for parent, dirs, names in walk:
                dirs.sort()
                for name in sorted(names):
                    if not name.endswith(".jsonl"):
                        continue
                    path = Path(parent) / name
                    coverage["files_scanned"] += 1
                    metadata, warnings = parse_codex_file(path, window["_zone"] if window else ZoneInfo("UTC"))
                    if warnings:
                        coverage["errors"].extend(warnings)
                    if not metadata:
                        if not warnings:
                            coverage["errors"].append("a Codex session record could not be read")
                        continue
                    session_id = metadata["session_id"]
                    if session_id in seen_sessions:
                        continue
                    if not path_is_within_tree(metadata.get("workspace"), workspace):
                        continue
                    updated = metadata.get("updated")
                    if window and updated is not None and in_window(updated, window) is False:
                        continue
                    seen_sessions.add(session_id)
                    coverage["sessions_scanned"] += 1
                    try:
                        with path.open("rb") as stream:
                            stream.readline()
                            for line in stream:
                                try:
                                    event = json.loads(line)
                                except (UnicodeDecodeError, json.JSONDecodeError, RecursionError):
                                    continue
                                if isinstance(event, dict):
                                    content = _codex_search_text(event)
                                    if content and _add_search_doc(db, "codex", session_id, metadata.get("workspace"), updated, content):
                                        coverage["documents_indexed"] += 1
                    except OSError:
                        coverage["errors"].append("a Codex session file could not be read for search")
        except OSError:
            coverage["errors"].append("a Codex session root could not be traversed")
    if coverage["errors"]:
        coverage["status"] = "partial"
    return coverage


def _muse_index_path(index_path: str | None) -> Path:
    return Path(index_path or os.environ.get("MUSE_SESSION_INDEX") or
                (Path.home() / ".local" / "share" / "muse" / "session-index.db")).expanduser()


def _search_muse(db: sqlite3.Connection, window: dict[str, Any] | None,
                 workspace: str | None, index_path: str | None) -> dict[str, Any]:
    path = _muse_index_path(index_path)
    coverage = {"status": "complete", "sessions_scanned": 0, "documents_indexed": 0, "errors": [], "source": "local Muse session index search_text"}
    if not path.is_file():
        return {**coverage, "status": "data_unavailable", "errors": ["Muse session index not found"]}
    connection = None
    try:
        connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=5)
        connection.execute("PRAGMA query_only = ON")
        connection.execute("BEGIN")
        columns = {row[1] for row in connection.execute("PRAGMA table_info(sessions)")}
        required = {"session_id", "workspace_root", "created_at_us", "updated_at_us", "search_text", "title"}
        if not required.issubset(columns):
            raise sqlite3.DatabaseError("Muse session index schema lacks searchable metadata")
        created_expr = "COALESCE(msp_created_at_us,created_at_us)" if "msp_created_at_us" in columns else "created_at_us"
        updated_expr = "COALESCE(msp_updated_at_us,updated_at_us)" if "msp_updated_at_us" in columns else "updated_at_us"
        where = []
        params: list[Any] = []
        if window:
            where.append(f"{updated_expr} >= ? AND {updated_expr} < ?")
            params.extend((int(window["_start"].timestamp() * 1_000_000), int(window["_end"].timestamp() * 1_000_000)))
        sql = f"SELECT session_id,workspace_root,{created_expr},{updated_expr},search_text,title FROM sessions"
        if where:
            sql += " WHERE " + " AND ".join(where)
        for session_id, row_workspace, created, updated, search_text, title in connection.execute(sql, params):
            if not path_is_within_tree(row_workspace if isinstance(row_workspace, str) else None, workspace):
                continue
            if window and updated is not None:
                stamp = datetime.fromtimestamp(updated / 1_000_000, timezone.utc)
                if in_window(stamp, window) is False:
                    continue
            start = datetime.fromtimestamp(created / 1_000_000, timezone.utc) if created is not None else None
            modified = datetime.fromtimestamp(updated / 1_000_000, timezone.utc) if updated is not None else None
            content = "\n".join(value for value in (title, search_text) if isinstance(value, str) and value)
            coverage["sessions_scanned"] += 1
            if _add_search_doc(db, "muse", session_id, row_workspace, modified or start, content):
                coverage["documents_indexed"] += 1
        connection.rollback()
    except (sqlite3.Error, OSError):
        coverage.update(status="data_unreadable", errors=["Muse local search index could not be queried read-only"])
    finally:
        if connection is not None:
            connection.close()
    return coverage


def _opencode_visible_text(raw: str) -> str | None:
    try:
        part = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError):
        return None
    if not isinstance(part, dict):
        return None
    kind = part.get("type")
    if kind == "text":
        return part.get("text") if isinstance(part.get("text"), str) else None
    if kind == "tool":
        state = part.get("state")
        if isinstance(state, dict):
            values = [state.get(key) for key in ("title", "output", "error")]
            return "\n".join(value for value in values if isinstance(value, str)) or None
    if kind == "patch":
        return json.dumps(part.get("files", []), ensure_ascii=False) if part.get("files") else None
    return None


def _search_opencode(db: sqlite3.Connection, window: dict[str, Any] | None,
                     workspace: str | None, binary: str, database_path: str | None) -> dict[str, Any]:
    cwd = str(Path(workspace).resolve()) if workspace else os.getcwd()
    path = Path(database_path).expanduser().resolve() if database_path else None
    if path is None:
        path, error = _resolve_opencode_database(binary, cwd)
        if error:
            status = "cli_unavailable" if not shutil.which(binary) else "database_unavailable"
            return {"status": status, "sessions_scanned": 0, "documents_indexed": 0, "errors": [error], "source": "local OpenCode database"}
    coverage = {"status": "complete", "sessions_scanned": 0, "documents_indexed": 0, "errors": [], "source": "local OpenCode user/assistant text and tool output"}
    connection = None
    try:
        connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=5)
        connection.execute("PRAGMA query_only = ON")
        connection.execute("BEGIN")
        columns = {row[1] for row in connection.execute("PRAGMA table_info(session)")}
        required = {"id", "parent_id", "directory", "time_created", "time_updated", "title"}
        if not required.issubset(columns):
            raise sqlite3.DatabaseError("OpenCode session table lacks searchable metadata")
        where = []
        params: list[Any] = []
        if window:
            start_ms = int(window["_start"].timestamp() * 1000)
            end_ms = int(window["_end"].timestamp() * 1000)
            where.append("((time_updated >= ? AND time_updated < ?) OR (time_updated IS NULL AND time_created >= ? AND time_created < ?))")
            params.extend((start_ms, end_ms, start_ms, end_ms))
        query = "SELECT id,directory,time_created,time_updated,title FROM session"
        if where:
            query += " WHERE " + " AND ".join(where)
        sessions = []
        for row in connection.execute(query, params):
            session_id, row_workspace, created, updated, title = row
            if not path_is_within_tree(row_workspace if isinstance(row_workspace, str) else None, workspace):
                continue
            start, _ = parse_timestamp(created, window["_zone"] if window else ZoneInfo("UTC"))
            modified, _ = parse_timestamp(updated, window["_zone"] if window else ZoneInfo("UTC"))
            sessions.append((session_id, row_workspace, start, modified, title))
        coverage["sessions_scanned"] = len(sessions)
        for session_id, row_workspace, start, modified, title in sessions:
            if isinstance(title, str) and _add_search_doc(db, "opencode", session_id, row_workspace, modified or start, title):
                coverage["documents_indexed"] += 1
            part_rows = connection.execute(
                "SELECT p.data,m.data FROM part p LEFT JOIN message m ON m.id=p.message_id "
                "WHERE p.session_id=? ORDER BY p.time_created,p.id", (session_id,),
            )
            for part_data, message_data in part_rows:
                try:
                    message = json.loads(message_data) if message_data else {}
                except (TypeError, json.JSONDecodeError, RecursionError):
                    message = {}
                if message.get("role") not in {"user", "assistant"}:
                    continue
                content = _opencode_visible_text(part_data)
                if content and _add_search_doc(db, "opencode", session_id, row_workspace, modified or start, content):
                    coverage["documents_indexed"] += 1
        connection.rollback()
    except (sqlite3.Error, OSError):
        coverage.update(status="database_unreadable", errors=["OpenCode local search database could not be queried read-only"])
    finally:
        if connection is not None:
            connection.close()
    return coverage


def _redact_excerpt(value: str) -> str:
    value = re.sub(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{12,}", "Bearer [redacted]", value)
    value = re.sub(r"(?i)\b(?:sk|rk|pk)-[A-Za-z0-9_-]{12,}", "[redacted-key]", value)
    value = re.sub(r"(?i)\b(api[_-]?key|access[_-]?token|password|secret)\s*[:=]\s*[^\s,;]+", r"\1=[redacted]", value)
    return value if len(value) <= 480 else value[:477] + "…"


def search(args: argparse.Namespace) -> dict[str, Any]:
    window = _optional_window(args)
    workspace, scope_label = effective_tree(args.scope, args.tree or args.workspace)
    match_query = _search_query(args.query, args.mode)
    try:
        fts = sqlite3.connect(":memory:")
        fts.execute("PRAGMA temp_store = MEMORY")
        fts.execute("CREATE VIRTUAL TABLE search_docs USING fts5(harness UNINDEXED,session_ref UNINDEXED,workspace_group UNINDEXED,updated_at_utc UNINDEXED,content,tokenize='unicode61 remove_diacritics 2')")
    except sqlite3.OperationalError:
        raise ValueError("this Python SQLite build does not include FTS5") from None
    chosen = list(dict.fromkeys(args.harness or HARNESS_NAMES))
    coverage: dict[str, Any] = {}
    for harness in chosen:
        if harness == "codex":
            coverage[harness] = _search_codex(fts, window, workspace, args.codex_home)
        elif harness == "muse":
            coverage[harness] = _search_muse(fts, window, workspace, args.muse_index)
        else:
            coverage[harness] = _search_opencode(fts, window, workspace, args.opencode_binary, args.opencode_db)
    try:
        excerpt_expr = "snippet(search_docs,4,'⟦','⟧',' … ',20)" if args.show_excerpts else "NULL"
        terms = re.findall(r"[\w]+", args.query, flags=re.UNICODE) if args.mode == "all" else []
        if len(terms) > 1:
            eligible_sql = " INTERSECT ".join(
                "SELECT harness,session_ref FROM search_docs WHERE content MATCH ?" for _ in terms
            )
            eligible_join = "JOIN eligible USING(harness,session_ref) "
            eligibility = f"eligible AS ({eligible_sql}), "
            match_query = _search_query(args.query, "any")
            parameters = [f'"{term}"' for term in terms] + [match_query, args.limit]
        else:
            eligible_join = ""
            eligibility = ""
            parameters = [match_query, args.limit]
        rows = fts.execute(
            f"WITH {eligibility}hits AS (SELECT harness,session_ref,workspace_group,updated_at_utc, "
            f"bm25(search_docs) AS score,{excerpt_expr} AS excerpt "
            f"FROM search_docs {eligible_join}WHERE content MATCH ?), ranked AS ("
            "SELECT *,row_number() OVER(PARTITION BY harness,session_ref ORDER BY score) AS hit_rank FROM hits) "
            "SELECT harness,session_ref,workspace_group,updated_at_utc,excerpt FROM ranked "
            "WHERE hit_rank=1 ORDER BY score LIMIT ?",
            parameters,
        ).fetchall()
    except sqlite3.OperationalError as exc:
        fts.close()
        raise ValueError(f"invalid FTS query: {exc}") from None
    results = []
    for h, ref, group, updated, excerpt in rows:
        item = {"harness": h, "session_ref": ref, "workspace_group": group or None,
                "updated_at_utc": updated or None}
        if args.show_excerpts:
            item["excerpt"] = _redact_excerpt(excerpt or "")
        results.append(item)
    report = {
        "schema_version": VERSION,
        "mode": "search",
        "generated_at_utc": _utc_string(datetime.now(timezone.utc)),
        "match_mode": args.mode,
        "scope": scope_label,
        "filetree_filter_applied": workspace is not None,
        "window": {key: value for key, value in window.items() if not key.startswith("_")} if window else None,
        "engine": "ephemeral SQLite FTS5; index is held in memory and discarded after this search",
        "persistent_write": False,
        "session_state_mutation": "none",
        "provider_calls": 0,
        "transcript_text_emitted": bool(results) and args.show_excerpts,
        "excerpt_policy": "omitted by default; --show-excerpts emits up to 480 characters per hit with best-effort pattern redaction",
        "coverage": coverage,
        "result_count": len(results),
        "limit": args.limit,
        "results": results,
    }
    fts.close()
    return report


def _run_suppressed(argv: list[str], timeout: int = 10) -> tuple[int | None, bytes, str | None]:
    try:
        result = subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, timeout=timeout, check=False)
        return result.returncode, result.stdout[:4096], None
    except subprocess.TimeoutExpired:
        return None, b"", "timed out"
    except OSError:
        return None, b"", "could not be started"


def _decode_version(raw: bytes) -> str | None:
    # Return only a version token. A surprising wrapper banner cannot leak a
    # user name, path, credential, or other arbitrary first-line content.
    match = VERSION_TOKEN.search(raw.decode("utf-8", "replace"))
    return match.group(0) if match else None


def diagnose(args: argparse.Namespace) -> dict[str, Any]:
    rows: dict[str, Any] = {}
    for harness, binary, extra_env in (
        ("codex", args.codex_binary, ("CODEX_API_KEY", "OPENAI_API_KEY")),
        ("muse", args.muse_binary, ("META_API_KEY",)),
        ("opencode", args.opencode_binary, ("OPENCODE_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY")),
    ):
        executable = shutil.which(binary)
        row: dict[str, Any] = {
            "cli": {"status": "available" if executable else "not_found", "binary_name": binary},
            "authentication": {"status": "not_checked", "credential_env_names_present": [name for name in extra_env if name in os.environ]},
            "provider_connectivity": "not_probed",
        }
        if executable:
            code, output, error = _run_suppressed([executable, "--version"])
            row["cli"].update(version=_decode_version(output), version_exit_code=code)
            if error:
                row["cli"]["version_error"] = error
            if harness == "codex":
                status, auth_output, auth_error = _run_suppressed([executable, "login", "status"])
                normalized = auth_output.decode("utf-8", "replace").lower()
                if status == 0 and "logged in" in normalized and "not logged in" not in normalized:
                    auth_state = "logged_in"
                elif status == 0 and "not logged in" in normalized:
                    auth_state = "not_logged_in"
                else:
                    auth_state = "unknown"
                row["authentication"] = {
                    "status": auth_state,
                    "surface": "codex login status",
                    "credential_env_names_present": [name for name in extra_env if name in os.environ],
                    "details_suppressed": True,
                }
                if auth_error:
                    row["authentication"]["error"] = auth_error
            elif harness == "opencode":
                status, _, auth_error = _run_suppressed([executable, "auth", "list"])
                row["authentication"] = {
                    "status": "auth_list_command_succeeded" if status == 0 else "unknown",
                    "surface": "opencode auth list",
                    "credential_env_names_present": [name for name in extra_env if name in os.environ],
                    "details_suppressed": True,
                    "configured_provider_state": "not_interpreted",
                }
                if auth_error:
                    row["authentication"]["error"] = auth_error
            else:
                config_status, _, config_error = _run_suppressed([executable, "config", "status"])
                row["authentication"] = {
                    "status": "credential_env_present" if "META_API_KEY" in row["authentication"]["credential_env_names_present"] else "unknown",
                    "surface": "META_API_KEY presence only; no credential file read",
                    "details_suppressed": True,
                }
                row["local_configuration"] = {
                    "status": "config_status_command_succeeded" if config_status == 0 else "unknown",
                    "surface": "muse config status",
                    "details_suppressed": True,
                }
                if config_error:
                    row["local_configuration"]["error"] = config_error
        else:
            row["authentication"]["status"] = "not_checked_cli_missing"
        rows[harness] = row
    return {
        "schema_version": VERSION,
        "mode": "doctor",
        "generated_at_utc": _utc_string(datetime.now(timezone.utc)),
        "persistent_write": False,
        "provider_probe": "not_run; no network calls, model turns, or token spend requested",
        "credentials": {
            "credential_files_read_directly_by_helper": False,
            "credential_values_emitted": False,
            "native_cli_auth_store_may_be_read_by_status_commands": True,
        },
        "harnesses": rows,
        "interpretation": "CLI/authentication visibility is local diagnostics, not proof that a provider request will succeed",
    }


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("--codex-binary", default="codex", help=argparse.SUPPRESS)
    root.add_argument("--muse-binary", default="muse", help=argparse.SUPPRESS)
    root.add_argument("--opencode-binary", default="opencode", help=argparse.SUPPRESS)
    subparsers = root.add_subparsers(dest="command", required=True)
    doctor = subparsers.add_parser("doctor", help="check CLI and safe local authentication signals")
    doctor.set_defaults(handler=diagnose)
    collect = subparsers.add_parser("inventory", help="list metadata-only session candidates for an inclusive date window")
    collect.add_argument("--from", dest="from_date", required=True, help="inclusive start date (YYYY-MM-DD)")
    collect.add_argument("--through", dest="through_date", required=True, help="inclusive end date (YYYY-MM-DD)")
    collect.add_argument("--timezone", default="UTC", help="IANA timezone for date boundaries (default: UTC)")
    collect.add_argument("--scope", choices=("current-filetree", "all"), default=os.environ.get("HARNESS_SESSION_REVIEW_SCOPE", "current-filetree"), help="search local sessions associated with this directory tree, or all local trees (default: current-filetree)")
    collect.add_argument("--tree", help="directory tree root; defaults to the current directory")
    collect.add_argument("--workspace", help=argparse.SUPPRESS)
    collect.add_argument("--harness", action="append", choices=HARNESS_NAMES, help="repeat to select harnesses; default: all")
    collect.add_argument("--muse-session", action="append", default=[], metavar="ID", help="limit Muse inventory to an exact session ID; may be repeated")
    collect.add_argument("--muse-index", help="override the local Muse session-index.db path")
    collect.add_argument("--codex-home", help="override CODEX_HOME without changing it")
    collect.add_argument("--opencode-db", help="override the local OpenCode database path")
    collect.set_defaults(handler=inventory)
    search_cmd = subparsers.add_parser("search", help="full-text search local session content; defaults to the current filetree")
    search_cmd.add_argument("query", help="search text or an FTS5 expression when --mode fts is selected")
    search_cmd.add_argument("--mode", choices=("all", "any", "phrase", "fts"), default="all", help="match all terms, any term, an exact phrase, or a raw FTS5 expression")
    search_cmd.add_argument("--scope", choices=("current-filetree", "all"), default=os.environ.get("HARNESS_SESSION_REVIEW_SCOPE", "current-filetree"), help="default: current-filetree")
    search_cmd.add_argument("--tree", help="directory tree root; defaults to the current directory")
    search_cmd.add_argument("--workspace", help=argparse.SUPPRESS)
    search_cmd.add_argument("--from", dest="from_date", help="optional inclusive start date (YYYY-MM-DD); supply with --through")
    search_cmd.add_argument("--through", dest="through_date", help="optional inclusive end date (YYYY-MM-DD); supply with --from")
    search_cmd.add_argument("--timezone", default="UTC", help="IANA timezone for date boundaries (default: UTC)")
    search_cmd.add_argument("--harness", action="append", choices=HARNESS_NAMES, help="repeat to select harnesses; default: all")
    search_cmd.add_argument("--limit", type=int, default=50, help="maximum unique session results (1-500)")
    search_cmd.add_argument("--show-excerpts", action="store_true", help="include short matching transcript excerpts in output; may contain sensitive text")
    search_cmd.add_argument("--codex-home", help="override CODEX_HOME without changing it")
    search_cmd.add_argument("--muse-index", help="override the local Muse session-index.db path")
    search_cmd.add_argument("--opencode-db", help="override the local OpenCode database path")
    search_cmd.set_defaults(handler=search)
    return root


def main(argv: list[str] | None = None) -> int:
    arg_parser = parser()
    args = arg_parser.parse_args(argv)
    if getattr(args, "workspace", None) and getattr(args, "tree", None):
        arg_parser.error("use only one of --tree or --workspace")
    tree = getattr(args, "tree", None) or getattr(args, "workspace", None)
    if tree and not Path(tree).expanduser().is_dir():
        arg_parser.error("--tree must be an existing local directory")
    if getattr(args, "limit", 1) < 1 or getattr(args, "limit", 1) > 500:
        arg_parser.error("--limit must be between 1 and 500")
    try:
        result = args.handler(args)
    except ValueError as exc:
        arg_parser.error(str(exc))
    json.dump(result, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
