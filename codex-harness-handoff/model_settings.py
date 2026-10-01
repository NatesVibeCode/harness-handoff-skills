"""Portable, read-only Codex model preflight. No provider calls or launches."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone, timedelta
import hashlib
import json
import os
from pathlib import Path
import re

IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}\Z")
EFFORTS = {"none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra"}


def preflight(model=None, effort=None, capabilities_path=None, *, now=None):
    """Check exact requests against fresh native metadata or an explicit copy.

    Unknown metadata never substitutes a model or guesses a default. A model
    alone can be passed through with an unknown capability result; an explicit
    effort requires an exact model and current model-specific support evidence.
    """
    if model is not None and (not isinstance(model, str) or not IDENTIFIER.fullmatch(model)):
        raise ValueError("invalid model identifier")
    if effort is not None and (not isinstance(effort, str) or effort not in EFFORTS):
        raise ValueError("invalid reasoning effort")
    if effort is not None and model is None:
        raise ValueError("explicit reasoning effort requires an explicit model")
    result = {"schema": "harness.model_preflight.v1", "requested": {
        "model": model, "reasoning_effort": effort}, "status": "inherited" if model is None else "unknown",
        "source": None, "effective_runtime_state": "not_observed"}
    if model is None:
        return result
    path = Path(capabilities_path) if capabilities_path else Path(
        os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))) / "models_cache.json"
    try:
        raw = path.read_bytes()
        data = json.loads(raw)
        fetched = datetime.fromisoformat(data["fetched_at"].replace("Z", "+00:00"))
        current = now or datetime.now(timezone.utc)
        if fetched.tzinfo is None or not timedelta(0) <= current - fetched <= timedelta(hours=24):
            raise ValueError("model capability evidence is stale or future-dated")
        models = data["models"]
        if not isinstance(models, list):
            raise ValueError("model capability models must be a list")
        matches = [row for row in models if isinstance(row, dict) and row.get("slug") == model]
        if len(matches) != 1:
            raise ValueError("exact model absent or duplicated in capability evidence")
        levels = matches[0]["supported_reasoning_levels"]
        if not isinstance(levels, list) or any(not isinstance(row, dict) or row.get("effort") not in EFFORTS for row in levels):
            raise ValueError("invalid model-specific reasoning levels")
        if effort is not None and effort not in {row["effort"] for row in levels}:
            raise ValueError("selected model does not support the requested reasoning effort")
        result.update(status="validated", source={"kind": "supplied_file" if capabilities_path else "native_cache",
            "sha256": hashlib.sha256(raw).hexdigest(), "fetched_at": data["fetched_at"],
            "client_version": data.get("client_version")})
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        if effort is not None or capabilities_path is not None:
            raise ValueError(f"model preflight failed: {exc}") from exc
        result["reason"] = "fresh exact model capability evidence unavailable; native CLI must resolve the model"
    return result


def owned_context(session_id):
    """Read only the fresh thread's native journal, matched by its returned ID."""
    if not isinstance(session_id, str) or not re.fullmatch(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", session_id):
        return ""
    root = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))) / "sessions"
    try:
        paths = list(root.glob(f"**/*-{session_id}.jsonl"))
        if len(paths) != 1 or not paths[0].resolve().is_relative_to(root.resolve()):
            return ""
        with paths[0].open(encoding="utf-8") as stream:
            first = json.loads(next(stream))
            if first.get("type") != "session_meta" or first.get("payload", {}).get("id") != session_id:
                return ""
            latest = ""
            for line in stream:
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(event, dict) and event.get("type") == "turn_context":
                    latest = line
            return latest
    except (OSError, ValueError, TypeError, AttributeError, StopIteration):
        return ""


def launch_receipt(argv, stdout):
    """Record explicit CLI requests and only native metadata actually emitted."""
    requested = {"model": None, "reasoning_effort": None}
    for index, token in enumerate(argv[:-1]):
        if token in {"--model", "-m"}:
            requested["model"] = argv[index + 1]
        if token in {"-c", "--config"} and argv[index + 1].startswith("model_reasoning_effort="):
            value = argv[index + 1].split("=", 1)[1]
            try:
                requested["reasoning_effort"] = json.loads(value)
            except json.JSONDecodeError:
                requested["reasoning_effort"] = value
    observed = {}
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict) or event.get("type") != "turn_context":
            continue
        payload = event.get("payload", {})
        if not isinstance(payload, dict):
            continue
        for source, target in (("model", "model"), ("effort", "reasoning_effort")):
            if isinstance(payload.get(source), str):
                observed[target] = payload[source]
    comparisons = [observed[key] == value for key, value in requested.items()
                   if value is not None and key in observed]
    return {"requested": requested, "observed": observed,
        "verification_scope": "model_and_reasoning_effort",
        "effective_settings_verified": all(key in observed for key in requested) and all(comparisons),
        "matches_request": all(comparisons) if comparisons else None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model")
    parser.add_argument("--reasoning-effort")
    parser.add_argument("--capabilities", help="point to a Codex-native model metadata JSON file")
    args = parser.parse_args()
    try:
        result = preflight(args.model, args.reasoning_effort, args.capabilities)
    except ValueError as exc:
        print(json.dumps({"status": "refused", "reason": str(exc)}))
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
