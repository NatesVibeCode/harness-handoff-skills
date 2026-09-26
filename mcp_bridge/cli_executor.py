"""CLI fallback executor: run every harness through its pinned contract argv.

This is the universal route — all fourteen harnesses declare a `binary` and an
`oneshot_argv` template — used whenever the official SDK is unavailable, the
caller language has no authorized binding, or the operator explicitly requests
the CLI. Some pinned CLI contracts put the task prompt in argv; never include
credential values in a handoff prompt for those routes.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

SESSION_ID_KEYS = ("session_id", "sessionId", "conversation_id", "conversationId", "thread_id", "id")
SECRET_PATTERN = re.compile(
    r"(sk-[A-Za-z0-9-_]{8,}|xai-[A-Za-z0-9-_]{8,}|sgamp_[A-Za-z0-9-_]{8,}|crsr_[A-Za-z0-9-_]{8,}|perm-[A-Za-z0-9-_]{8,})"
)


class ExecutionError(RuntimeError):
    """The harness process could not be launched or failed."""


def redact(text: str) -> str:
    """Redact likely secret tokens from logs, errors, and receipts."""
    return SECRET_PATTERN.sub("[redacted-credential]", text)


def build_argv(entry: dict, *, prompt: str, workspace: str | None, model: str | None) -> tuple[list[str], str | None, Path | None]:
    """Render `oneshot_argv`, returning (argv, stdin_text, temp_dir_to_clean).

    Placeholders: <prompt>, <model>, <workspace>, <prompt-file>, <workdir>.
    """
    delivery = entry["prompt_delivery"]
    argv: list[str] = []
    stdin_text: str | None = None
    temp_dir: Path | None = None
    prompt_file: Path | None = None

    if "<model>" in entry["oneshot_argv"] and not model:
        raise ExecutionError(f"{entry['skill']}: route requires an explicit model")
    if "<workspace>" in entry["oneshot_argv"] and not workspace:
        raise ExecutionError(f"{entry['skill']}: route requires an explicit workspace")
    if any("<workdir>" in token for token in entry["oneshot_argv"]) and not entry.get("call_workdir"):
        raise ExecutionError("contract uses <workdir> without call_workdir")

    if entry.get("call_workdir"):
        temp_dir = Path(tempfile.mkdtemp(prefix="harness-lane-"))
    if delivery == "file_flag":
        prompt_file = (temp_dir or Path(tempfile.mkdtemp(prefix="harness-lane-"))) / "prompt.txt"
        if temp_dir is None:
            temp_dir = prompt_file.parent
        try:
            prompt_file.write_text(prompt, encoding="utf-8")
        except OSError as exc:
            shutil.rmtree(temp_dir)
            raise ExecutionError(f"prompt file could not be staged: {redact(str(exc))}") from exc

    for token in entry["oneshot_argv"]:
        if token == "<prompt>":
            if delivery == "stdin":
                stdin_text = prompt
                continue
            argv.append(prompt)
        elif token == "<prompt-file>":
            if prompt_file is None:
                raise ExecutionError("contract uses <prompt-file> without file_flag delivery")
            argv.append(str(prompt_file))
        elif token == "<model>":
            if not model:
                raise ExecutionError(f"{entry['skill']}: route requires an explicit model")
            argv.append(model)
        elif token == "<workspace>":
            if not workspace:
                raise ExecutionError(f"{entry['skill']}: route requires an explicit workspace")
            argv.append(workspace)
        elif token == "<workdir>":
            if temp_dir is None:
                raise ExecutionError("contract uses <workdir> without call_workdir")
            argv.append(str(temp_dir))
        elif "<workdir>" in token:
            if temp_dir is None:
                raise ExecutionError("contract uses <workdir> without call_workdir")
            argv.append(token.replace("<workdir>", str(temp_dir)))
        else:
            argv.append(token)
    if delivery == "stdin" and stdin_text is None:
        stdin_text = prompt
    return argv, stdin_text, temp_dir


def extract_session_id(stdout: str) -> str | None:
    """Best-effort session/thread/conversation ID recovery from JSON output."""
    for match in re.finditer(r"\{[^{}]*\}", stdout):
        try:
            obj = json.loads(match.group(0))
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            for key in SESSION_ID_KEYS:
                value = obj.get(key)
                if isinstance(value, str) and value:
                    return value
    return None


def run_cli(entry: dict, *, prompt: str, workspace: str | None = None, model: str | None = None, timeout: int = 900, extra_argv: list[str] | None = None, extra_at: int = 0) -> dict:
    """Run the pinned CLI fallback and return a normalized receipt."""
    binary = entry["binary"]
    if shutil.which(binary) is None:
        raise ExecutionError(f"{binary} is not installed or not on PATH")
    argv, stdin_text, temp_dir = build_argv(entry, prompt=prompt, workspace=workspace, model=model)
    if extra_argv:
        argv = [*argv[:extra_at], *extra_argv, *argv[extra_at:]]
    try:
        try:
            completed = subprocess.run(
                [binary, *argv],
                input=stdin_text,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=workspace or None,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise ExecutionError(f"{binary} failed to launch: {redact(str(exc))}") from exc
        stdout = completed.stdout or ""
        final_message = None
        if temp_dir is not None:
            final_path = temp_dir / "final.md"
            try:
                with final_path.open("rb") as final_stream:
                    final_stream.seek(0, 2)
                    final_stream.seek(max(0, final_stream.tell() - 32768))
                    final_message = redact(final_stream.read().decode("utf-8", "replace")[-8000:])
            except FileNotFoundError:
                pass
        return {
            "harness": entry["skill"],
            "route": "cli",
            "binary": binary,
            "argv": [binary, *[("<prompt>" if a == prompt else a) for a in argv]],
            "exit_code": completed.returncode,
            "session_id": extract_session_id(stdout),
            "output": redact(stdout[-8000:]),
            "final_message": final_message,
            "stderr": redact((completed.stderr or "")[-2000:]),
            "approved": None,
        }
    finally:
        if temp_dir is not None:
            shutil.rmtree(temp_dir)
