"""Printed-process runner for one pinned harness-handoff Python SDK operation.

The Forge worker sends a single JSON request over stdin. This module verifies
the interpreter, installed distribution, import module, entrypoint, and shipped
adapter bytes before it calls exactly one SDK executor. It never installs a
package and never falls back to a CLI.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import importlib
import importlib.metadata
import json
import re
import sys
from pathlib import Path


MIN_PYTHON = {
    "claude": (3, 10),
    "cursor": (3, 10),
    "copilot": (3, 11),
    "muse": (3, 10),
    "antigravity": (3, 10),
    "openhands": (3, 12),
}
MODULES = {
    "claude": ("claude-agent-sdk", "claude_agent_sdk", "query"),
    "cursor": ("cursor-sdk", "cursor_sdk", "Agent"),
    "copilot": ("github-copilot-sdk", "copilot", "CopilotClient"),
    "muse": ("muse-code-sdk", "muse_code", "MuseClient"),
    "antigravity": ("google-antigravity", "google.antigravity", "Agent"),
    "openhands": ("openhands-sdk", "openhands.sdk", "Conversation"),
}
OPERATIONS = {
    ("claude", "fresh"): "claude_fresh",
    ("claude", "resume"): "claude_resume",
    ("claude", "history"): "claude_history",
    ("cursor", "fresh"): "cursor_fresh",
    ("cursor", "resume"): "cursor_resume",
    ("cursor", "history"): "cursor_history",
    ("copilot", "fresh"): "copilot_fresh",
    ("copilot", "resume"): "copilot_resume",
    ("muse", "fresh"): "muse_fresh",
    ("muse", "resume"): "muse_resume",
    ("antigravity", "fresh"): "antigravity_fresh",
    ("antigravity", "resume"): "antigravity_resume",
    ("openhands", "fresh"): "openhands_fresh",
}
SECRET_PATTERN = re.compile(
    r"(sk-[A-Za-z0-9-_]{8,}|xai-[A-Za-z0-9-_]{8,}|sgamp_[A-Za-z0-9-_]{8,}|crsr_[A-Za-z0-9-_]{8,}|perm-[A-Za-z0-9-_]{8,})"
)


def _string(request: dict, key: str) -> str:
    value = request.get(key, "")
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    return value


async def _invoke(request: dict, adapter_module):
    harness = _string(request, "harness")
    operation = _string(request, "operation")
    function_name = OPERATIONS.get((harness, operation))
    if not function_name or _string(request, "adapter") != function_name:
        raise ValueError("SDK operation is not in the pinned adapter table")
    function = getattr(adapter_module, function_name, None)
    if not callable(function):
        raise ValueError("pinned SDK adapter is absent")

    prompt = _string(request, "prompt")
    session_id = _string(request, "session_id")
    workspace = _string(request, "workspace") or None
    model = _string(request, "model") or None
    approval = _string(request, "approval") or "default"
    save_dir = _string(request, "save_dir")
    app_data_dir = _string(request, "app_data_dir") or None
    if operation == "fresh":
        result = await function(prompt, workspace, model, approval)
    elif operation == "resume":
        if harness == "antigravity":
            result = await function(session_id, prompt, workspace, save_dir=save_dir, app_data_dir=app_data_dir)
        elif harness == "copilot":
            result = await function(session_id, prompt, workspace, approval=approval)
        else:
            result = await function(session_id, prompt, workspace)
    else:
        limit = request.get("limit")
        if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
            raise ValueError("history limit must be a caller-supplied positive integer")
        result = await function(session_id, workspace, limit)
    if not isinstance(result, dict) or result.get("harness") != harness or result.get("route") != "sdk":
        raise ValueError("SDK adapter returned an invalid receipt")
    output = result.get("output", "")
    if not isinstance(output, str):
        output = json.dumps(output, ensure_ascii=False, separators=(",", ":"))
    raw_session_id = result.get("session_id")
    session_id = str(raw_session_id) if raw_session_id is not None else ""
    if operation == "fresh" and not session_id:
        raise ValueError("SDK adapter completed without a session id")
    return {
        "schema": "praxis.harness_sdk_receipt.v1",
        "status": "succeeded",
        "harness": harness,
        "sdk_operation": operation,
        "distribution": _string(request, "distribution"),
        "distribution_version": _string(request, "version"),
        "module": _string(request, "module"),
        "entrypoint": _string(request, "entrypoint"),
        "adapter": function_name,
        "adapter_digest": _string(request, "adapter_digest"),
        "runner_digest": _string(request, "runner_digest"),
        "session_id": session_id,
        "output": SECRET_PATTERN.sub("[redacted-credential]", output),
    }


def run(request: dict) -> dict:
    if not isinstance(request, dict):
        raise ValueError("request must be an object")
    harness = _string(request, "harness")
    expected = MODULES.get(harness)
    if expected is None:
        raise ValueError("unsupported Python SDK binding")
    distribution, module_name, entrypoint = expected
    if (
        _string(request, "distribution") != distribution
        or _string(request, "module") != module_name
        or _string(request, "entrypoint") != entrypoint
    ):
        raise ValueError("SDK package binding differs from the generated contract")
    if sys.version_info[:2] < MIN_PYTHON[harness]:
        raise RuntimeError("Python runtime is below the SDK contract minimum")
    version_pin = _string(request, "version")
    installed = importlib.metadata.version(distribution)
    if installed != version_pin:
        raise RuntimeError("installed Python SDK version differs from the Node pin")

    sdk_module = importlib.import_module(module_name)
    if not hasattr(sdk_module, entrypoint):
        raise RuntimeError("SDK entrypoint is absent from the installed package")

    base = Path(__file__).resolve().parent
    adapter_path = base / "mcp_bridge" / "sdk_executors.py"
    expected_digest = _string(request, "adapter_digest")
    actual_digest = "sha256:" + hashlib.sha256(adapter_path.read_bytes()).hexdigest()
    if actual_digest != expected_digest:
        raise RuntimeError("shipped SDK adapter source differs from the Node pin")
    runner_digest = "sha256:" + hashlib.sha256(Path(__file__).resolve().read_bytes()).hexdigest()
    if runner_digest != _string(request, "runner_digest"):
        raise RuntimeError("SDK runner source differs from the Node pin")

    sys.path.insert(0, str(base))
    from mcp_bridge import sdk_executors

    with contextlib.redirect_stdout(sys.stderr):
        return asyncio.run(_invoke(request, sdk_executors))


def main() -> int:
    try:
        request = json.load(sys.stdin)
        receipt = run(request)
        sys.stdout.write(json.dumps(receipt, ensure_ascii=False, separators=(",", ":")) + "\n")
        return 0
    except Exception as exc:
        message = re.sub(r"(?:sk-|xai-|sgamp_|crsr_|perm-)[A-Za-z0-9_-]{8,}", "[redacted-credential]", str(exc))
        sys.stderr.write(f"SDK invocation refused: {message}\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
