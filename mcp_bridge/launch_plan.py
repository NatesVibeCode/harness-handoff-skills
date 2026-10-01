"""Immutable fresh-launch inputs shared by authorization and native execution."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict, replace
import hashlib
import json
import marshal
import os
from pathlib import Path
import shutil
import stat
import sys


def encode(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value) -> str:
    return hashlib.sha256(encode(value).encode()).hexdigest()


@dataclass(frozen=True)
class FilePin:
    path: str
    sha256: str
    device: int
    inode: int

    @classmethod
    def read(cls, path):
        resolved = Path(path).resolve(strict=True)
        with resolved.open("rb") as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode):
                raise ValueError("launch input must be a regular file")
            hasher = hashlib.sha256()
            for chunk in iter(lambda: stream.read(65536), b""):
                hasher.update(chunk)
            after = os.fstat(stream.fileno())
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
                after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
            raise ValueError("launch input changed while resolving")
        return cls(str(resolved), hasher.hexdigest(), before.st_dev, before.st_ino)

    def verify(self):
        if self != self.read(self.path):
            raise ValueError("resolved launch input changed: " + self.path)


def callable_digest(fn):
    return hashlib.sha256(marshal.dumps(fn.__code__)).hexdigest()


@dataclass(frozen=True)
class LaunchPlan:
    harness: str
    adapter: str
    executable: FilePin
    workspace: str
    workspace_device: int
    workspace_inode: int
    prompt: str = field(repr=False)
    argv: tuple[str, ...] = field(default=(), repr=False)
    stdin_text: str | None = field(default=None, repr=False)
    temp_dir: str | None = None
    profile_argv: tuple[str, ...] = ()
    requested_json: str = "{}"
    native_json: str = "{}"
    context_json: str = "null"
    binding_json: str = "null"
    profile_json: str = "null"
    preflight_json: str = "null"
    input_files: tuple[FilePin, ...] = ()
    sdk_callable_digest: str | None = None
    sdk_workspace: str | None = None
    sdk_callable: object = field(default=None, repr=False, compare=False)
    capabilities_path: str | None = None
    resolved_digest: str = field(default="", repr=False)

    @property
    def route(self):
        return self.adapter.split(".", 1)[0]

    @property
    def governed(self):
        return self.binding_json != "null"

    @property
    def requested(self):
        return json.loads(self.requested_json)

    @property
    def native_settings(self):
        return json.loads(self.native_json)

    @property
    def settings_control(self):
        return json.loads(self.profile_json)

    @property
    def plan_digest(self):
        # Private argv/stdin/prompt are bound but never echoed in public receipts.
        payload = asdict(self)
        payload.pop("sdk_callable")
        payload.pop("resolved_digest")
        return digest(payload)

    def policy_labels(self):
        labels = {"launch_plan_digest": self.plan_digest, "execution_adapter": self.adapter,
                  "execution_route": self.route, "executable": self.executable.path,
                  "executable_digest": self.executable.sha256, "workspace": self.workspace,
                  "executable_kind": "native_cli" if self.route == "cli" else "python_runtime",
                  "native_settings": self.native_json}
        labels.update({"resolved_" + key: encode(value) for key, value in self.native_settings.items()})
        return labels

    def public(self):
        return {"schema": "harness.launch_plan.v1", "digest": self.plan_digest,
                "harness": self.harness, "adapter": self.adapter, "route": self.route,
                "executable": asdict(self.executable),
                "executable_kind": "native_cli" if self.route == "cli" else "python_runtime",
                "workspace": self.workspace, "workspace_identity": [self.workspace_device, self.workspace_inode],
                "native_settings": self.native_settings, "requested_controls": self.requested,
                "access_context": json.loads(self.context_json), "governed": self.governed,
                "settings_profile": (self.settings_control or {}).get("profile")}

    def verify(self):
        if self.resolved_digest != self.plan_digest:
            raise ValueError("launch plan changed after resolution")
        if self.adapter != f"{self.route}.{self.harness}.fresh":
            raise ValueError("launch adapter and harness do not match")
        info = Path(self.workspace).stat()
        if not stat.S_ISDIR(info.st_mode) or (info.st_dev, info.st_ino) != (self.workspace_device, self.workspace_inode):
            raise ValueError("resolved launch workspace changed")
        self.executable.verify()
        for pin in self.input_files:
            pin.verify()
        if self.route == "cli" and self.harness == "codex":
            from mcp_bridge import model_settings
            parsed = model_settings.launch_receipt(list(self.argv), "")["requested"]
            if any(parsed[key] != self.native_settings.get(key) for key in parsed):
                raise ValueError("native model/effort arguments differ from the resolved settings")
            if self.argv.count("-C") != 1 or self.argv[self.argv.index("-C") + 1] != self.workspace:
                raise ValueError("native workspace argument differs from the resolved workspace")
            sandbox = None
            approval = None
            native_profile = None
            index = 1
            if not self.argv or self.argv[0] != "exec":
                raise ValueError("unresolved native command")
            while index < len(self.argv):
                token = self.argv[index]
                if token in {"--json", "-"}:
                    index += 1
                    continue
                if token == "--dangerously-bypass-approvals-and-sandbox":
                    if sandbox is not None or approval is not None:
                        raise ValueError("ambiguous native approval posture")
                    sandbox, approval = "danger-full-access", "never"
                    index += 1
                    continue
                if token not in {"-C", "-o", "--model", "-m", "--sandbox", "--profile", "-c", "--config"} or index + 1 >= len(self.argv):
                    raise ValueError("unresolved native argument")
                value = self.argv[index + 1]
                if token == "--sandbox":
                    if sandbox is not None:
                        raise ValueError("ambiguous native sandbox")
                    sandbox = value
                elif token == "--profile":
                    native_profile = value
                elif token in {"-c", "--config"} and value.startswith("approval_policy="):
                    if approval is not None:
                        raise ValueError("ambiguous native approval")
                    approval = json.loads(value.split("=", 1)[1])
                elif token == "-o" and value != str(Path(self.temp_dir or "") / "final.md"):
                    raise ValueError("native output path differs from the resolved staging")
                index += 2
            if any(actual != self.native_settings.get(key) for key, actual in (
                    ("sandbox", sandbox), ("approval", approval), ("native_profile", native_profile))):
                raise ValueError("native approval/profile arguments differ from the resolved settings")
            for index, token in enumerate(self.argv[:-1]):
                if token in {"-c", "--config"}:
                    key = self.argv[index + 1].split("=", 1)[0]
                    if key not in {"approval_policy", "model_reasoning_effort"}:
                        raise ValueError("unresolved native configuration override")
        if self.capabilities_path is not None:
            from mcp_bridge import model_settings
            checked = model_settings.preflight(self.native_settings.get("model"),
                self.native_settings.get("reasoning_effort"), self.capabilities_path)
            if checked["source"]["sha256"] != json.loads(self.preflight_json)["source"]["sha256"]:
                raise ValueError("resolved model evidence changed")
        if self.route == "sdk":
            from mcp_bridge import sdk_executors
            fn = sdk_executors.EXECUTORS[self.harness]["fresh"]
            if fn is not self.sdk_callable or callable_digest(fn) != self.sdk_callable_digest:
                raise ValueError("resolved SDK adapter changed")

    def cleanup(self):
        if self.temp_dir is not None and Path(self.temp_dir).exists():
            shutil.rmtree(self.temp_dir)


def resolve(entry, *, route, prompt, workspace, requested, native_settings,
            extra_argv=(), extra_at=0, profile=None, context=None,
            model_capabilities=None):
    """Resolve once; no worker or model call is performed here."""
    from mcp_bridge import cli_executor, contracts, model_settings, sdk_executors, control
    if profile is not None and context is None:
        raise ValueError("saved launch settings require a bound governance context")
    harness = entry["skill"].removesuffix("-harness-handoff")
    canonical = str(Path(workspace or Path.cwd()).resolve(strict=True))
    directory = Path(canonical).stat()
    if not stat.S_ISDIR(directory.st_mode):
        raise ValueError("launch workspace must be a directory")
    temp_dir = None
    argv, stdin_text, preflight = [], None, None
    files = [FilePin.read(contracts.CONTRACT_PATH), FilePin.read(control.CATALOG)]
    sdk_hash, sdk_callable, capabilities_path = None, None, None
    sdk_workspace = canonical
    native_settings = dict(native_settings)
    native_settings.update(workspace=canonical, workspace_binding="canonical")
    if profile is not None:
        for key, value in list(native_settings.items()):
            if value is False and harness == "muse":
                # An omitted boolean flag inherits native configuration; it
                # does not resolve an effective false value.
                native_settings[key] = None
    try:
        if route == "cli":
            binary = shutil.which(entry["binary"])
            if binary is None:
                raise cli_executor.ExecutionError(f"{entry['binary']} is not installed or not on PATH")
            executable = FilePin.read(binary)
            if not os.access(executable.path, os.X_OK):
                raise ValueError("resolved executable is not executable")
            argv, stdin_text, temp_dir = cli_executor.build_argv(entry, prompt=prompt, workspace=canonical,
                                                               model=native_settings.get("model"))
            argv = [*argv[:extra_at], *extra_argv, *argv[extra_at:]]
            files.append(FilePin.read(cli_executor.__file__))
            if temp_dir is not None and (temp_dir / "prompt.txt").exists():
                files.append(FilePin.read(temp_dir / "prompt.txt"))
            if harness == "codex":
                parsed = model_settings.launch_receipt(argv, "")["requested"]
                if any(parsed[key] != native_settings.get(key) for key in parsed):
                    raise ValueError("native model/effort arguments differ from the resolved settings")
                preflight = model_settings.preflight(parsed["model"], parsed["reasoning_effort"], model_capabilities)
                if preflight["status"] == "validated":
                    cache = model_capabilities or str(Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))) / "models_cache.json")
                    pin = FilePin.read(cache)
                    if pin.sha256 != preflight["source"]["sha256"]:
                        raise ValueError("model capability evidence changed while resolving")
                    files.append(pin)
                    capabilities_path = pin.path
        elif route == "sdk":
            executable = FilePin.read(sys.executable)
            files.append(FilePin.read(sdk_executors.__file__))
            sdk_callable = sdk_executors.EXECUTORS[harness]["fresh"]
            sdk_hash = callable_digest(sdk_callable)
            if harness in {"copilot", "antigravity"}:
                # These adapters cannot attest a native workspace. They are
                # already refused when a caller selects one, including governance.
                sdk_workspace = None
                native_settings.update(workspace=None, workspace_binding="vendor_default_unverified")
                if context is not None:
                    raise ValueError("SDK adapter cannot bind a governed workspace")
        else:
            raise ValueError("unsupported resolved adapter")
        resolved = LaunchPlan(harness=harness, adapter=f"{route}.{harness}.fresh", executable=executable,
            workspace=canonical, workspace_device=directory.st_dev, workspace_inode=directory.st_ino,
            prompt=prompt, argv=tuple(argv), stdin_text=stdin_text,
            temp_dir=str(temp_dir) if temp_dir is not None else None, profile_argv=tuple(extra_argv) if profile else (),
            requested_json=encode(requested), native_json=encode(native_settings),
            context_json=encode((context or {}).get("access_context")), binding_json=encode((context or {}).get("binding")),
            profile_json=encode(profile), preflight_json=encode(preflight), input_files=tuple(files),
            sdk_callable_digest=sdk_hash, sdk_workspace=sdk_workspace, sdk_callable=sdk_callable,
            capabilities_path=capabilities_path)
        return replace(resolved, resolved_digest=resolved.plan_digest)
    except BaseException:
        if temp_dir is not None:
            shutil.rmtree(temp_dir)
        raise
