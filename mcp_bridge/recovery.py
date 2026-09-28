"""Finite recovery issuance, not a task/section ownership or coordination board.

One private journal per host state store. Transactions never wait for another
writer; no transaction survives a provider call or client tool execution.
"""
from __future__ import annotations

import os
from pathlib import Path
import sqlite3
import time

from mcp_bridge import control

MAX_STEPS = 3
WINDOW_SECONDS = 300


def issue(host, request):
    target = {key: request[key] for key in ("harness", "profile", "repo")}
    root = str(Path(host.config["repositories"][target["repo"]]["path"]).resolve())
    # Same host-attested principal + original target/intent stays one episode,
    # even if a model edits its failure explanation or adds noisy metadata.
    episode_id = control._digest({"subject": host.config["subject"], "target": target,
                                 "root": root, "intent": request["intent"].strip()})
    path = host.state_path.with_name(host.state_path.name + ".recovery.sqlite3")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    os.close(fd)
    connection = sqlite3.connect(path, timeout=0, isolation_level=None)
    try:
        connection.execute("PRAGMA busy_timeout=0")
        connection.execute("CREATE TABLE IF NOT EXISTS episodes (id TEXT PRIMARY KEY, deadline REAL NOT NULL, issued INTEGER NOT NULL)")
        connection.execute("BEGIN IMMEDIATE")
        now = time.time()
        row = connection.execute("SELECT deadline, issued FROM episodes WHERE id=?", (episode_id,)).fetchone()
        deadline, issued = row if row else (now + WINDOW_SECONDS, 0)
        if issued >= MAX_STEPS or now >= deadline:
            connection.rollback()
            return {"id": episode_id, "status": "exhausted", "issued": issued,
                    "remaining": 0, "deadline": deadline}
        issued += 1
        connection.execute("INSERT INTO episodes VALUES (?, ?, ?) ON CONFLICT(id) DO UPDATE SET issued=excluded.issued", (episode_id, deadline, issued))
        connection.commit()
        return {"id": episode_id, "status": "issued", "issued": issued,
                "remaining": MAX_STEPS - issued, "deadline": deadline}
    except sqlite3.OperationalError as exc:
        if connection.in_transaction:
            connection.rollback()
        if "locked" in str(exc).lower() or "busy" in str(exc).lower():
            return {"id": episode_id, "status": "busy", "reason": "continue independent work; do not wait on another agent"}
        raise control.ControlError("recovery journal unavailable; ask for the unresolved fact without automatic retry") from exc
    except sqlite3.DatabaseError as exc:
        raise control.ControlError("recovery journal invalid; no automatic recovery reset") from exc
    finally:
        connection.close()
