"""MCP server: harness SDK bridge.

Run with: python3 mcp_bridge/server.py   (stdio transport)

Tools are thin, policy-enforcing wrappers around the v2 contract:
- route selection (SDK preferred where authorized and importable, else CLI);
- forbidden-route refusal (Codex continuation, newest-as-exact everywhere);
- exact session IDs only, never latest/continue inference;
- prompt delivery follows each contract; some CLIs expose prompt text in argv.
  Receipts apply best-effort credential pattern redaction.

Each call performs at most one harness execution and returns its receipt.
This server never fans out lanes, shares sessions across harnesses, or
substitutes another product when the selected one is unavailable.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from mcp_bridge import cli_executor, contracts, sdk_executors, control, launch_plan

mcp = FastMCP("harness-sdk-bridge")

CODEX_RESTRICTED_ARGV = ["--sandbox", "read-only", "-c", 'approval_policy="on-request"']
CODEX_AUTONOMOUS_ARGV = ["--dangerously-bypass-approvals-and-sandbox"]
EXACT_SESSION_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,255}\Z")
SESSION_SELECTORS = {"latest", "last", "newest", "continue"}
UNATTENDED_ALLOWLIST_ENV = "HARNESS_HANDOFF_UNATTENDED_HARNESSES"


def _refuse(message: str) -> dict:
    return {"refused": True, "reason": message}


def _is_exact_session_id(value: str) -> bool:
    return isinstance(value, str) and bool(EXACT_SESSION_ID.fullmatch(value)) and value.lower() not in SESSION_SELECTORS


def _unattended_allowed(harness: str) -> bool:
    allowed = {item.strip() for item in os.environ.get(UNATTENDED_ALLOWLIST_ENV, "").split(",")}
    return harness in allowed


def _stage_prompt(prompt: str) -> Path:
    directory = Path(tempfile.mkdtemp(prefix="harness-lane-"))
    path = directory / "prompt.txt"
    try:
        path.write_text(prompt, encoding="utf-8")
    except OSError:
        shutil.rmtree(directory)
        raise
    return path


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
def list_harnesses(workspace: str | None = None) -> list[dict] | dict:
    """List all fourteen harnesses with their SDK status and authorized routes."""
    rows = contracts.list_harnesses()
    if control.CONFIG_ENV not in os.environ:
        return rows
    try:
        return [row for row in rows if control.project(row["harness"], workspace)["verdict"]["effect"] == "allow"]
    except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        return _refuse(cli_executor.redact(str(exc)))


@mcp.tool()
def get_contract(harness: str, workspace: str | None = None) -> dict:
    """Return the full v2 execution contract for one harness."""
    if control.CONFIG_ENV in os.environ:
        try:
            if control.project(harness, workspace)["verdict"]["effect"] != "allow":
                return _refuse("not available in this session")
        except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError) as exc:
            return _refuse(cli_executor.redact(str(exc)))
    return contracts.get_harness(harness)


@mcp.tool()
def settings_describe(workspace: str | None = None) -> dict:
    """Describe settings; a configured host filters by ABAC projection."""
    result = control.describe()
    if control.CONFIG_ENV in os.environ:
        try:
            result["harnesses"] = {name: row for name, row in result["harnesses"].items()
                if control.project(name, workspace)["verdict"]["effect"] == "allow"}
        except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError) as exc:
            return _refuse(cli_executor.redact(str(exc)))
    return result


@mcp.tool()
async def settings_profiles(harness: str, repo: str) -> dict:
    """List ABAC-readable profiles for one product adapter and repository."""
    try:
        return await asyncio.to_thread(control.profiles, harness, repo)
    except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        return _refuse(cli_executor.redact(str(exc)))


@mcp.tool()
async def control_recover(request: dict) -> dict:
    """Catch-all recovery for unclear/unsupported requests within a selected target.

    Optional Jev chooses a useful next step; deterministic fallback works offline.
    Returns a bounded task to the current harness, never bypasses access control.
    """
    from mcp_bridge.ambiguity import recover
    try:
        return await asyncio.to_thread(recover, request)
    except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        return _refuse(cli_executor.redact(str(exc)))


@mcp.tool()
async def settings_resolve(request: dict) -> dict:
    """Resolve bounded settings interpretations; optional Jev, final ABAC gate.

    Returns a plan or focused question, never executes or changes permissions.
    Runs off the event loop so unrelated authorized work remains responsive.
    """
    from mcp_bridge.ambiguity import resolve
    try:
        return await asyncio.to_thread(resolve, request)
    except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        return _refuse(cli_executor.redact(str(exc)))


@mcp.tool()
def settings_get(harness: str, profile: str, repo: str) -> dict:
    """Read one ABAC-authorized saved launch profile, not live session state."""
    try:
        return control.get(harness, profile, repo)
    except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        return _refuse(cli_executor.redact(str(exc)))


@mcp.tool()
def settings_plan(changes: list[dict]) -> dict:
    """Preview a batch of saved launch setting changes and all ABAC decisions."""
    try:
        return control.plan(changes)
    except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        return _refuse(cli_executor.redact(str(exc)))


@mcp.tool()
def settings_apply(changes: list[dict], expected_digest: str) -> dict:
    """Apply exactly the reviewed plan to saved launch profiles in one write.

    Rechecks ABAC. Changes neither global native settings nor running sessions.
    """
    try:
        return control.apply(changes, expected_digest)
    except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        return _refuse(cli_executor.redact(str(exc)))


@mcp.tool()
async def handoff_fresh(
    harness: str,
    prompt: str,
    workspace: str | None = None,
    model: str | None = None,
    approval: str = "default",
    use: str = "auto",
    settings_profile: str | None = None,
    reasoning_effort: str | None = None,
    model_capabilities: str | None = None,
) -> dict:
    """Start one fresh execution in the selected harness and return its receipt.

    approval is "default", "restricted", or "unattended". An explicitly
    dispatched Codex handoff runs autonomously with full access by default;
    restricted selects a read-only sandbox with on-request approval.
    OpenHands headless CLI requires "unattended" explicitly.
    Copilot SDK approval bypass requires "unattended"; ordinary Copilot calls
    use the CLI route. Other routes accept only "default" because this bridge
    does not implement their approval controls. use is "auto", "sdk", or "cli".
    Codex CLI reasoning_effort requires an exact model and fresh capability
    metadata. model_capabilities points to native-shape JSON instead of the
    default local cache, and can also be supplied with a saved profile.
    A selected HARNESS_CONTROL_CONFIG engages ABAC projection and launch gates
    using the host-bound product access context, independently of settings_profile.
    """
    entry = contracts.get_harness(harness)
    short = _short_name(entry)
    requested = {"model": model, "reasoning_effort": reasoning_effort, "approval": approval, "use": use}
    access_receipt = None
    if control.CONFIG_ENV in os.environ:
        try:
            access_receipt = await asyncio.to_thread(control.access_gate, short, workspace or "", action="project",
                profile=settings_profile, controls=requested)
        except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError) as exc:
            return _refuse(cli_executor.redact(str(exc)))
    if (reasoning_effort is not None or model_capabilities is not None) and short != "codex":
        return _refuse("model capability preflight and reasoning override are implemented only for Codex")
    if reasoning_effort is not None and model is None:
        return _refuse("explicit reasoning effort requires an explicit model")
    profile_argv, profile_receipt = [], None
    if settings_profile is not None:
        if use not in {"auto", "cli"} or approval != "default" or model is not None or reasoning_effort is not None:
            return _refuse("saved settings use the CLI route and cannot be combined with model/approval overrides")
        try:
            profile_argv, profile_receipt = await asyncio.to_thread(control.launch_settings, short, settings_profile, workspace or "")
        except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError) as exc:
            return _refuse(cli_executor.redact(str(exc)))
        use = "cli"
    try:
        route = _choose_route(entry, use)
    except RuntimeError as exc:
        return _refuse(str(exc))
    if approval not in {"default", "restricted", "unattended"}:
        return _refuse("approval must be 'default', 'restricted', or 'unattended'")
    if approval == "unattended" and short != "codex" and not _unattended_allowed(short):
        return _refuse(f"{short}: unattended execution is disabled by {UNATTENDED_ALLOWLIST_ENV}")
    if short == "antigravity" and workspace and route == "sdk":
        if use == "sdk":
            return _refuse("antigravity SDK adapter cannot bind the selected workspace")
        route = "cli"
    if short == "copilot":
        if approval == "restricted":
            return _refuse("copilot: restricted approval control is not implemented by this bridge")
        if approval == "unattended" and route != "sdk":
            return _refuse("copilot: unattended approval is implemented only for the SDK route")
        if approval == "unattended" and not model:
            return _refuse("copilot SDK adapter requires an explicit model")
        if approval == "unattended" and workspace:
            return _refuse("copilot SDK adapter cannot bind the selected workspace")
        if approval == "default" and route == "sdk":
            if use == "sdk":
                return _refuse("copilot SDK route requires approval='unattended' because it uses approve_all")
            route = "cli"
    if short == "openhands" and route == "sdk" and not model:
        if use == "sdk":
            return _refuse("openhands SDK adapter requires an explicit model")
        route = "cli"
    if short == "openhands" and route == "cli" and approval != "unattended":
        return _refuse("openhands headless CLI always approves tools; use approval='unattended' only when authorized")
    if short not in {"codex", "openhands", "copilot"} and approval != "default":
        return _refuse(f"{short}: this bridge does not implement {approval!r} approval controls")
    if short == "openhands" and route == "sdk" and approval != "default":
        return _refuse("openhands SDK route does not implement an approval override")
    if model and route == "sdk" and short not in {"cursor", "copilot", "openhands"}:
        return _refuse(f"{short} SDK adapter cannot bind the selected model")
    if model and route == "cli" and short not in {"codex", "cursor", "opencode"}:
        return _refuse(f"{short} CLI contract cannot bind the selected model")
    if route == "sdk":
        if reasoning_effort is not None or model_capabilities is not None:
            return _refuse("model capability preflight requires the Codex CLI route")
    extra, extra_at = ([], 0)
    if profile_receipt is not None:
        # Preserve contract-owned prompt/workspace argv. Never append a second
        # approval override or the default full-access Codex recipe here.
        extra, extra_at = profile_argv, (1 if short in {"codex", "muse"} else 0)
    elif short == "codex":
        controls = CODEX_RESTRICTED_ARGV if approval == "restricted" else CODEX_AUTONOMOUS_ARGV
        extra, extra_at = (list(controls), 1)
        if model:
            extra.extend(["--model", model])
        if reasoning_effort is not None:
            extra.extend(["-c", "model_reasoning_effort=" + json.dumps(reasoning_effort)])
    native = dict(profile_receipt["requested_settings"] if profile_receipt else {
        "model": model, "reasoning_effort": reasoning_effort,
        "approval": None, "sandbox": None,
    })
    if not profile_receipt and short == "codex":
        native.update(approval="on-request" if approval == "restricted" else "never",
                      sandbox="read-only" if approval == "restricted" else "danger-full-access")
    elif not profile_receipt and short == "cursor" and route == "cli":
        native["sandbox"] = "enabled"
    elif not profile_receipt and (short == "openhands" and route == "cli" or short == "copilot" and route == "sdk"):
        native["approval"] = "always-approve"
    resolved = None
    cli_owns_staging = False
    try:
        resolved = await asyncio.to_thread(launch_plan.resolve, entry, route=route,
            prompt=prompt, workspace=workspace, requested=requested, native_settings=native,
            extra_argv=extra, extra_at=extra_at, profile=profile_receipt, context=access_receipt,
            model_capabilities=model_capabilities)
        authorization = await asyncio.to_thread(control.authorize_launch_plan, resolved)
        if route == "cli":
            # The execution thread retains its staging until it finishes, even
            # when its caller is cancelled. Process cancellation is separate.
            cli_owns_staging = True
            return await asyncio.to_thread(cli_executor.run_cli, resolved, authorization=authorization)
        return await sdk_executors.run_plan(resolved, authorization=authorization)
    except (ValueError, OSError, KeyError, TypeError, cli_executor.ExecutionError, subprocess.SubprocessError) as exc:
        return _refuse(cli_executor.redact(str(exc)))
    except Exception as exc:  # SDK-specific errors are receipts, never retries.
        return {"harness": short, "route": route, "error": cli_executor.redact(str(exc))}
    finally:
        if resolved is not None and not cli_owns_staging:
            resolved.cleanup()


@mcp.tool()
async def handoff_continue(
    harness: str,
    session_id: str,
    prompt: str,
    workspace: str | None = None,
    save_dir: str | None = None,
    approval: str = "default",
) -> dict:
    """Continue an explicitly selected session by exact ID. Never infers latest.

    Codex continuation is refused (fresh-only skill). Antigravity SDK restore
    needs save_dir pointing at the SDK-owned session store; otherwise the CLI
    continues the exact native conversation.
    """
    entry = contracts.get_harness(harness)
    short = _short_name(entry)
    access_receipt = None
    sdk = entry["sdk"]
    if approval not in {"default", "unattended"}:
        return _refuse("continuation approval must be 'default' or 'unattended'")
    if approval == "unattended" and not _unattended_allowed(short):
        return _refuse(f"{short}: unattended execution is disabled by {UNATTENDED_ALLOWLIST_ENV}")
    if approval == "unattended" and short not in {"openhands", "copilot"}:
        return _refuse(f"{short}: unattended continuation control is not implemented by this bridge")
    if short == "copilot" and approval != "unattended":
        return _refuse("copilot SDK continuation requires approval='unattended' because it uses approve_all")
    if not _is_exact_session_id(session_id):
        return _refuse("an exact session ID is required; selectors and option-like values are forbidden")
    if sdk["continuation"] == "forbidden":
        return _refuse(f"{short}: continuation is policy-forbidden for this fresh-only handoff")
    if control.CONFIG_ENV in os.environ:
        try:
            access_receipt = await asyncio.to_thread(control.access_gate, short, workspace or "",
                action="continue", session_id=session_id, controls={"approval": approval})
        except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError) as exc:
            return _refuse(cli_executor.redact(str(exc)))
    if short == "antigravity" and save_dir:
        if workspace:
            return _refuse("antigravity SDK restore cannot bind or verify the selected workspace")
        try:
            if access_receipt is not None:
                access_receipt = await asyncio.to_thread(control.recheck_access, access_receipt,
                    harness=short, workspace=workspace or "", action="continue", session_id=session_id,
                    controls=access_receipt["requested_controls"])
            receipt = await sdk_executors.antigravity_resume(session_id, prompt, workspace, save_dir=save_dir)
            if access_receipt is not None:
                receipt["access_control"] = access_receipt
            return receipt
        except Exception as exc:  # noqa: BLE001
            return {"harness": short, "route": "sdk", "error": cli_executor.redact(str(exc))}
    executor = sdk_executors.EXECUTORS.get(short, {}).get("resume")
    if sdk["continuation"].startswith("sdk") and executor is not None and sdk_executors.available(short):
        if workspace and short in {"cursor", "muse", "copilot"}:
            return _refuse(f"{short} SDK resume cannot bind or verify the selected workspace")
        try:
            if access_receipt is not None:
                access_receipt = await asyncio.to_thread(control.recheck_access, access_receipt,
                    harness=short, workspace=workspace or "", action="continue", session_id=session_id,
                    controls=access_receipt["requested_controls"])
            if short == "copilot":
                receipt = await executor(session_id, prompt, workspace, approval=approval)
            else:
                receipt = await executor(session_id, prompt, workspace)
            if access_receipt is not None:
                receipt["access_control"] = access_receipt
            return receipt
        except Exception as exc:  # noqa: BLE001
            return {"harness": short, "route": "sdk", "error": cli_executor.redact(str(exc))}
    # CLI exact-ID continuation: render the skill's resume shape per harness.
    try:
        return _cli_continue(entry, short, session_id, prompt, workspace, approval,
            **({"access_control": access_receipt} if access_receipt is not None else {}))
    except OSError as exc:
        return {"harness": short, "route": "cli", "error": cli_executor.redact(str(exc))}


def _cli_continue(entry: dict, short: str, session_id: str, prompt: str,
                  workspace: str | None, approval: str = "default", access_control: dict | None = None) -> dict:
    binary = entry["binary"]
    prompt_file: Path | None = None
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
        prompt_file = _stage_prompt(prompt)
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
            prompt_file = _stage_prompt(prompt)
        argv = ["run", "--session", session_id, "--format", "json", "--file", str(prompt_file), prompt]
    elif short == "droid":
        argv = ["exec", "-s", session_id, prompt]
    elif short == "openhands":
        if approval != "unattended":
            return _refuse("openhands headless continuation always approves tools; use approval='unattended' only when authorized")
        prompt_file = _stage_prompt(prompt)
        argv = ["--resume", session_id, "--headless", "--json", "--file", str(prompt_file)]
    elif short == "junie":
        argv = ["--project", workspace or ".", "--resume", "--session-id", session_id, prompt]
    else:
        # cline, amp, copilot: no verified exact-ID CLI continuation shape.
        # Their SDK resume paths are authorized; the CLI stays fresh-only here.
        return _refuse(
            f"{short}: no verified exact-ID CLI continuation; install the authorized SDK and retry"
        )
    try:
        if shutil.which(binary) is None:
            return {"harness": short, "route": "cli", "error": f"{binary} is not installed or not on PATH"}
        try:
            if access_control is not None:
                access_control = control.recheck_access(access_control, harness=short, workspace=workspace or "",
                    action="continue", session_id=session_id, controls=access_control["requested_controls"])
            completed = subprocess.run(
                [binary, *argv], input=stdin_text, capture_output=True,
                text=True, timeout=900, cwd=workspace or None,
            )
        except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError) as exc:
            return {"harness": short, "route": "cli", "error": cli_executor.redact(str(exc))}
        receipt = {
            "harness": short,
            "route": "cli",
            "exit_code": completed.returncode,
            "session_id": cli_executor.extract_session_id(completed.stdout or "") or session_id,
            "output": cli_executor.redact((completed.stdout or "")[-8000:]),
            "stderr": cli_executor.redact((completed.stderr or "")[-2000:]),
        }
        if access_control is not None:
            receipt["access_control"] = access_control
        return receipt
    finally:
        if prompt_file is not None:
            shutil.rmtree(prompt_file.parent)


@mcp.tool()
async def session_history(harness: str, session_id: str, workspace: str | None = None, limit: int = 20) -> dict:
    """Passively retrieve history for an exact session ID. Sends no prompt."""
    entry = contracts.get_harness(harness)
    short = _short_name(entry)
    if not _is_exact_session_id(session_id):
        return _refuse("an exact session ID is required for history lookup")
    if not 1 <= limit <= 500:
        return _refuse("history limit must be between 1 and 500")
    access_receipt = None
    if control.CONFIG_ENV in os.environ:
        try:
            access_receipt = await asyncio.to_thread(control.access_gate, short, workspace or "",
                action="review", session_id=session_id)
        except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError) as exc:
            return _refuse(cli_executor.redact(str(exc)))
    executor = sdk_executors.EXECUTORS.get(short, {}).get("history")
    if executor is not None and sdk_executors.available(short):
        if workspace and short == "cursor":
            return _refuse("cursor SDK history cannot verify the selected workspace")
        try:
            if access_receipt is not None:
                access_receipt = await asyncio.to_thread(control.recheck_access, access_receipt,
                    harness=short, workspace=workspace or "", action="review", session_id=session_id)
            receipt = await executor(session_id, workspace, limit)
            if access_receipt is not None:
                receipt["access_control"] = access_receipt
            return receipt
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
