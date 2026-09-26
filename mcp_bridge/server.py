"""MCP server: harness SDK bridge.

Run with: python3 mcp_bridge/server.py   (stdio transport)

Tools are thin, policy-enforcing wrappers around the v2 contract:
- route selection (SDK preferred where authorized and importable, else CLI);
- forbidden-route refusal (Codex continuation, newest-as-exact everywhere);
- exact session IDs only, never latest/continue inference;
- no credential values in argv, secrets redacted from receipts.

Each call performs at most one harness execution and returns its receipt.
This server never fans out lanes, shares sessions across harnesses, or
substitutes another product when the selected one is unavailable.
"""

from __future__ import annotations

import asyncio
import shutil
import subprocess
import tempfile
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from mcp_bridge import cli_executor, contracts, sdk_executors

mcp = FastMCP("harness-sdk-bridge")

# Codex fresh lanes run unattended by skill policy unless restricted.
CODEX_UNATTENDED_argv = ["--dangerously-bypass-approvals-and-sandbox"]


def _refuse(message: str) -> dict:
    return {"refused": True, "reason": message}


def _choose_route(entry: dict, use: str) -> str:
    sdk = entry["sdk"]
    harness = _short_name(entry)
    if use == "cli":
        return "cli"
    if use == "sdk":
        if sdk["kind"] != "library" or not sdk_executors.available(harness):
            raise RuntimeError(
                f"{harness}: authorized SDK is not importable here; retry with use='cli'"
            )
        return "sdk"
    # use == "auto"; anything else is rejected so typos never silently route.
    if use != "auto":
        raise RuntimeError(f"unknown route {use!r}; use 'auto', 'sdk', or 'cli'")
    fresh = sdk["fresh"]
    if fresh.startswith("sdk") and sdk_executors.available(harness):
        return "sdk"
    return "cli"


def _short_name(entry: dict) -> str:
    return entry["skill"].removesuffix("-harness-handoff")


@mcp.tool()
def list_harnesses() -> list[dict]:
    """List all fourteen harnesses with their SDK status and authorized routes."""
    return contracts.list_harnesses()


@mcp.tool()
def get_contract(harness: str) -> dict:
    """Return the full v2 execution contract for one harness."""
    return contracts.get_harness(harness)


@mcp.tool()
async def handoff_fresh(
    harness: str,
    prompt: str,
    workspace: str | None = None,
    model: str | None = None,
    approval: str = "default",
    use: str = "auto",
) -> dict:
    """Start one fresh execution in the selected harness and return its receipt.

    approval is "default" (harness defaults) or "restricted" (no bypasses).
    For Codex, anything but "restricted" applies the skill's unattended
    bypass flag. use is "auto", "sdk", or "cli".
    """
    entry = contracts.get_harness(harness)
    short = _short_name(entry)
    try:
        route = _choose_route(entry, use)
    except RuntimeError as exc:
        return _refuse(str(exc))
    if route == "sdk":
        fn = sdk_executors.EXECUTORS[short]["fresh"]
        try:
            return await fn(prompt, workspace, model, approval)
        except Exception as exc:  # noqa: BLE001 — receipt, not traceback
            return {"harness": short, "route": "sdk", "error": cli_executor.redact(str(exc))}
    extra, extra_at = ([], 0)
    if short == "codex" and approval != "restricted":
        extra, extra_at = (CODEX_UNATTENDED_argv, 1)
    try:
        receipt = await asyncio.to_thread(
            cli_executor.run_cli, entry, prompt=prompt, workspace=workspace,
            model=model, extra_argv=extra, extra_at=extra_at,
        )
    except cli_executor.ExecutionError as exc:
        return {"harness": short, "route": "cli", "error": cli_executor.redact(str(exc))}
    if short == "openhands":
        receipt["warning"] = "headless mode always runs always-approve; use only with explicit unattended authorization"
    return receipt


@mcp.tool()
async def handoff_continue(
    harness: str,
    session_id: str,
    prompt: str,
    workspace: str | None = None,
    save_dir: str | None = None,
) -> dict:
    """Continue an explicitly selected session by exact ID. Never infers latest.

    Codex continuation is refused (fresh-only skill). Antigravity SDK restore
    needs save_dir pointing at the SDK-owned session store; otherwise the CLI
    continues the exact native conversation.
    """
    entry = contracts.get_harness(harness)
    short = _short_name(entry)
    sdk = entry["sdk"]
    if not session_id:
        return _refuse("an exact session ID is required; latest/continue inference is forbidden")
    if sdk["continuation"] == "forbidden":
        return _refuse(f"{short}: continuation is policy-forbidden for this fresh-only handoff")
    if short == "antigravity" and save_dir:
        try:
            return await sdk_executors.antigravity_resume(session_id, prompt, workspace, save_dir=save_dir)
        except Exception as exc:  # noqa: BLE001
            return {"harness": short, "route": "sdk", "error": cli_executor.redact(str(exc))}
    executor = sdk_executors.EXECUTORS.get(short, {}).get("resume")
    if sdk["continuation"].startswith("sdk") and executor is not None and sdk_executors.available(short):
        try:
            return await executor(session_id, prompt, workspace)
        except Exception as exc:  # noqa: BLE001
            return {"harness": short, "route": "sdk", "error": cli_executor.redact(str(exc))}
    # CLI exact-ID continuation: render the skill's resume shape per harness.
    return _cli_continue(entry, short, session_id, prompt, workspace)


def _cli_continue(entry: dict, short: str, session_id: str, prompt: str, workspace: str | None) -> dict:
    binary = entry["binary"]
    prompt_file: Path | None = None
    if entry["prompt_delivery"] == "file_flag":
        prompt_file = Path(tempfile.mkdtemp(prefix="harness-lane-")) / "prompt.txt"
        prompt_file.write_text(prompt, encoding="utf-8")
    argv: list[str] | None = None
    stdin_text: str | None = None
    if short == "antigravity":
        argv = ["--conversation", session_id, "--output-format", "json", "--print", prompt]
    elif short == "claude":
        argv = ["--resume", session_id, "-p", "--output-format", "json"]
        stdin_text = prompt
    elif short == "cursor":
        argv = ["--workspace", workspace or ".", "--resume", session_id, "--print", "--output-format", "json", prompt]
    elif short == "grok":
        argv = ["--cwd", workspace or ".", "--resume", session_id, "--prompt-file", str(prompt_file), "--output-format", "json"]
    elif short == "gemini":
        argv = ["--resume", session_id, "-p", prompt]
    elif short == "muse":
        # No verified headless CLI resume-with-prompt: exec --session-id
        # only selects an identity for a new run and does not resume
        # history, while `muse resume` is interactive-only. The authorized
        # SDK resume path is attempted before this CLI fallback; when it is
        # unavailable, refuse rather than mislabel a new run.
        return _refuse(
            "muse: no verified headless CLI continuation; install the authorized SDK for resume "
            "or continue interactively with `muse resume`"
        )
    elif short == "opencode":
        if prompt_file is None:
            prompt_file = Path(tempfile.mkdtemp(prefix="harness-lane-")) / "prompt.txt"
            prompt_file.write_text(prompt, encoding="utf-8")
        argv = ["run", "--session", session_id, "--format", "json", "--file", str(prompt_file), prompt]
    elif short == "droid":
        argv = ["exec", "-s", session_id, prompt]
    elif short == "openhands":
        argv = ["--resume", session_id, "--headless", "--json", "--file", str(prompt_file)]
    elif short == "junie":
        argv = ["--project", workspace or ".", "--resume", "--session-id", session_id, prompt]
    else:
        # cline, amp, copilot: no verified exact-ID CLI continuation shape.
        # Their SDK resume paths are authorized; the CLI stays fresh-only here.
        return _refuse(
            f"{short}: no verified exact-ID CLI continuation; install the authorized SDK and retry"
        )
    if shutil.which(binary) is None:
        return {"harness": short, "route": "cli", "error": f"{binary} is not installed or not on PATH"}
    try:
        completed = subprocess.run(
            [binary, *argv], input=stdin_text, capture_output=True,
            text=True, timeout=900, cwd=workspace or None,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {"harness": short, "route": "cli", "error": cli_executor.redact(str(exc))}
    return {
        "harness": short,
        "route": "cli",
        "exit_code": completed.returncode,
        "session_id": cli_executor.extract_session_id(completed.stdout or "") or session_id,
        "output": cli_executor.redact((completed.stdout or "")[-8000:]),
        "stderr": cli_executor.redact((completed.stderr or "")[-2000:]),
    }


@mcp.tool()
async def session_history(harness: str, session_id: str, workspace: str | None = None, limit: int = 20) -> dict:
    """Passively retrieve history for an exact session ID. Sends no prompt."""
    entry = contracts.get_harness(harness)
    short = _short_name(entry)
    if not session_id:
        return _refuse("an exact session ID is required for history lookup")
    executor = sdk_executors.EXECUTORS.get(short, {}).get("history")
    if executor is not None and sdk_executors.available(short):
        try:
            return await executor(session_id, workspace, limit)
        except Exception as exc:  # noqa: BLE001
            return {"harness": short, "route": "sdk", "error": cli_executor.redact(str(exc))}
    return {
        "harness": short,
        "route": "cli",
        "note": "no authorized SDK history path here; use the skill's native list/export commands",
        "contract_docs": entry["sdk"]["docs"],
    }


if __name__ == "__main__":
    mcp.run()
