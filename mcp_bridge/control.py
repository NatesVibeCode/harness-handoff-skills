"""ABAC-gated saved launch settings, using the handoff contracts.

No native global configuration or running session is mutated. The host owns
the context configuration; an ordinary agent must not be able to rewrite it
if this module is to form an enforcement boundary.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile

from mcp_bridge import contracts

CONFIG_ENV = "HARNESS_CONTROL_CONFIG"
CATALOG = contracts.REPO_ROOT / "skills-src" / "settings.json"
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}\Z")
IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_./:@-]{0,159}\Z")
LIMIT = 1 << 20


class ControlError(ValueError):
    pass


def _bytes(path: Path, *, missing: bool = False) -> bytes:
    if path.is_symlink():
        raise ControlError("control files must not be symlinks")
    try:
        with path.open("rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise ControlError("control file must be regular")
            raw = stream.read(LIMIT + 1)
    except FileNotFoundError:
        if missing:
            return b""
        raise
    if len(raw) > LIMIT:
        raise ControlError("control document exceeds one MiB")
    return raw


def _object(raw: bytes) -> dict:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ControlError("duplicate JSON member")
            result[key] = value
        return result
    value = json.loads(raw, object_pairs_hook=unique)
    if not isinstance(value, dict):
        raise ControlError("expected a JSON object")
    return value


def _closed(value: dict, required: set, optional: set = frozenset()) -> None:
    if not isinstance(value, dict) or not required <= value.keys() or value.keys() - required - optional:
        raise ControlError("document has missing or unsupported fields")


def _digest(value) -> str:
    raw = value if isinstance(value, bytes) else json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(raw).hexdigest()


def _absolute(value: str) -> Path:
    if not isinstance(value, str) or not Path(value).is_absolute():
        raise ControlError("host configuration paths must be absolute")
    return Path(value)


def describe() -> dict:
    catalog = _object(_bytes(CATALOG))
    known = contracts.load_contracts()["harnesses"]
    return {"schema": catalog["schema"], "scope": catalog["scope"],
            "native_global_settings": "unsupported", "running_session_settings": "unsupported",
            "harnesses": {name: catalog["harnesses"].get(name, {"status": "unsupported"}) for name in known}}


def _settings(harness: str, values: dict) -> dict:
    contracts.get_harness(harness)
    definitions = _object(_bytes(CATALOG))["harnesses"].get(harness)
    if definitions is None or not isinstance(values, dict) or not values or len(values) > 16:
        raise ControlError("settings unavailable or empty for this harness")
    for name, value in values.items():
        definition = definitions.get(name)
        if not isinstance(definition, dict):
            raise ControlError(f"unsupported setting {harness}.{name}")
        kind = definition["type"]
        valid = (kind == "bool" and type(value) is bool or
                 kind == "identifier" and isinstance(value, str) and IDENTIFIER.fullmatch(value) or
                 kind == "enum" and isinstance(value, str) and value in definition["values"])
        if not valid:
            raise ControlError(f"invalid value for {harness}.{name}")
    return definitions


class Host:
    def __init__(self):
        selected = os.environ.get(CONFIG_ENV)
        if not selected:
            raise ControlError(f"host must configure {CONFIG_ENV}; no implicit authority")
        self.path = _absolute(selected)
        raw = _bytes(self.path)
        self.config = _object(raw)
        _closed(self.config, {"schema", "abac_binary", "policy_files", "subject", "repositories", "state_file"}, {"jev_review"})
        if self.config["schema"] != "harness.control_host.v1":
            raise ControlError("unsupported host schema")
        _closed(self.config["subject"], {"principal_ref", "altitude"}, {"roles"})
        self.binary = _absolute(self.config["abac_binary"])
        self.state_path = _absolute(self.config["state_file"])
        policies = self.config["policy_files"]
        if not isinstance(policies, list) or not policies or len(policies) > 32:
            raise ControlError("host requires bounded explicit policy files")
        self.policies = [_absolute(path) for path in policies]
        protected = {path.resolve() for path in [self.path, self.binary, *self.policies, CATALOG]}
        if self.state_path.resolve() in protected:
            raise ControlError("settings state cannot replace a control or policy file")
        repos = self.config["repositories"]
        if not isinstance(repos, dict) or not repos:
            raise ControlError("host requires explicit repository identities")
        for name, record in repos.items():
            if not NAME.fullmatch(name):
                raise ControlError("invalid repository identity")
            _closed(record, {"path", "status"})
            _absolute(record["path"])
            if record["status"] not in {"active", "frozen", "superseded", "experimental"}:
                raise ControlError("invalid repository record")
        self.binding = {"host": _digest(raw), "catalog": _digest(_bytes(CATALOG)),
                        "contracts": _digest(_bytes(contracts.CONTRACT_PATH)),
                        "repository_paths": {name: str(Path(record["path"]).resolve()) for name, record in repos.items()},
                        "policies": {str(path): _digest(_bytes(path)) for path in self.policies}}
        hasher = hashlib.sha256()
        with self.binary.open("rb") as stream:
            for chunk in iter(lambda: stream.read(65536), b""):
                hasher.update(chunk)
        self.binding["evaluator"] = hasher.hexdigest()

    def state(self) -> tuple[dict, str]:
        raw = _bytes(self.state_path, missing=True)
        state = _object(raw) if raw else {"schema": "harness.launch_profiles.v1", "revision": 0, "profiles": {}}
        _closed(state, {"schema", "revision", "profiles"})
        if state["schema"] != "harness.launch_profiles.v1" or type(state["revision"]) is not int or not isinstance(state["profiles"], dict):
            raise ControlError("invalid settings state")
        return state, _digest(raw)

    def authorize(self, operation: str, harness: str, profile: str, repo: str,
                  setting: str = "", value=None) -> dict:
        record = self.config["repositories"].get(repo)
        if record is None:
            raise ControlError("repository is not in the host-owned identity map")
        if not Path(record["path"]).is_dir():
            raise ControlError("selected repository is unavailable")
        labels = {"harness": harness, "repo_id": repo,
                  "repo_path": str(Path(record["path"]).resolve()), "repo_status": record["status"]}
        if setting:
            labels.update(setting=setting, value=json.dumps(value, sort_keys=True, separators=(",", ":")))
        verbs = {"settings.get": "read", "settings.apply": "write", "handoff.launch_settings": "spawn", "ambiguity.review": "call"}
        if operation not in verbs:
            raise ControlError("unsupported authorization operation")
        request = {"subject": self.config["subject"],
                   "resource": {"kind": "data", "ref": f"harness-settings/{harness}/{profile}", "owner": "app",
                                "labels": labels},
                   "action": {"verb": verbs[operation], "operation": operation},
                   "environment": {"altitude": "app", "purpose": "harness-control"}}
        argv = [str(self.binary), "evaluate", "-request", "-"]
        for path in self.policies:
            argv.extend(["-policy", str(path)])
        result = subprocess.run(argv, input=json.dumps(request), text=True, capture_output=True,
                                timeout=15, env={"PATH": os.defpath})
        if result.returncode != 0 or len(result.stdout.encode()) > 65536:
            raise ControlError("ABAC evaluator refused or failed; no operation performed")
        verdict = _object(result.stdout.encode())
        if verdict.get("effect") not in {"allow", "deny"}:
            raise ControlError("invalid ABAC verdict")
        return {"request_digest": _digest(request), "operation": operation,
                "setting": setting or None, "verdict": verdict}

    def unchanged(self):
        if Host().binding != self.binding:
            raise ControlError("host configuration, evaluator, catalog or policies changed; replan")


def _target(change: dict):
    _closed(change, {"harness", "profile", "repo", "settings"})
    if not all(isinstance(change[key], str) and NAME.fullmatch(change[key]) for key in ("harness", "profile", "repo")):
        raise ControlError("exact harness/profile/repo names are required")
    _settings(change["harness"], change["settings"])
    return change["harness"] + "/" + change["profile"]


def plan(changes: list[dict], host: Host | None = None) -> dict:
    host = host or Host()
    if not isinstance(changes, list) or not changes or len(changes) > 64:
        raise ControlError("plan requires between one and 64 explicit changes")
    state, before = host.state()
    results, seen = [], set()
    for change in changes:
        key = _target(change)
        if key in seen:
            raise ControlError("duplicate target in batch")
        seen.add(key)
        prior = state["profiles"].get(key)
        if prior is not None and prior["repo"] != change["repo"]:
            raise ControlError("profile belongs to another repo; select a new profile")
        read = host.authorize("settings.get", change["harness"], change["profile"], change["repo"])
        if read["verdict"]["effect"] != "allow":
            raise ControlError("ABAC denies reading this profile: " + json.dumps(read["verdict"]))
        merged = dict(prior["settings"] if prior else {})
        merged.update(change["settings"])
        _settings(change["harness"], merged)
        decisions = [host.authorize("settings.apply", change["harness"], change["profile"], change["repo"], key, value)
                     for key, value in sorted(change["settings"].items())]
        results.append({"harness": change["harness"], "profile": change["profile"], "repo": change["repo"],
                        "before": prior["settings"] if prior else {}, "after": merged, "decisions": decisions})
    host.unchanged()
    result = {"schema": "harness.settings_plan.v1", "scope": "handoff_launch_profile", "binding": host.binding,
              "state_digest": before, "changes": changes, "targets": results,
              "allowed": all(d["verdict"]["effect"] == "allow" for row in results for d in row["decisions"])}
    result["digest"] = _digest(result)
    return result


@contextlib.contextmanager
def _lock(path: Path):
    if os.name != "posix":
        raise ControlError("settings publication requires the POSIX locking adapter")
    import fcntl
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(str(path) + ".lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ControlError("settings publication is busy; no wait or ownership claim; continue independent work and replan later") from exc
        yield
    finally:
        os.close(fd)


def apply(changes: list[dict], expected_digest: str) -> dict:
    host = Host()
    # Policy subprocesses run before the short, nonblocking publication gate.
    proposal = plan(changes, host)
    if proposal["digest"] != expected_digest:
        raise ControlError("stale or mismatched plan; inspect a fresh plan")
    if not proposal["allowed"]:
        return {"applied": False, "plan": proposal}
    with _lock(host.state_path):
        state, current = host.state()
        if current != proposal["state_digest"]:
            raise ControlError("settings changed while authorizing")
        for row in proposal["targets"]:
            state["profiles"][row["harness"] + "/" + row["profile"]] = {
                "repo": row["repo"], "settings": row["after"]}
        state["revision"] += 1
        raw = json.dumps(state, indent=2, allow_nan=False).encode() + b"\n"
        if len(raw) > LIMIT:
            raise ControlError("settings state exceeds its bound")
        fd, staged = tempfile.mkstemp(prefix=".settings-", dir=host.state_path.parent)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            host.unchanged()
            if host.state()[1] != current:
                raise ControlError("settings changed before publication")
            os.replace(staged, host.state_path)
        finally:
            if os.path.exists(staged):
                os.unlink(staged)
    return {"applied": True, "scope": "handoff_launch_profile", "plan_digest": expected_digest,
            "state_digest": _digest(raw), "revision": state["revision"],
            "targets": proposal["targets"], "native_global_settings_changed": False, "running_sessions_changed": False}


def get(harness: str, profile: str, repo: str) -> dict:
    contracts.get_harness(harness)
    if not NAME.fullmatch(profile):
        raise ControlError("invalid profile")
    host = Host()
    decision = host.authorize("settings.get", harness, profile, repo)
    if decision["verdict"]["effect"] != "allow":
        return {"allowed": False, "decision": decision}
    state, identity = host.state()
    row = state["profiles"].get(harness + "/" + profile)
    if row is not None and row["repo"] != repo:
        raise ControlError("profile belongs to another repo")
    host.unchanged()
    return {"allowed": True, "scope": "handoff_launch_profile", "profile": row,
            "state_digest": identity, "decision": decision, "effective_runtime_state": "not_observed"}


def launch_settings(harness: str, profile: str, workspace: str) -> tuple[list[str], dict]:
    if not isinstance(profile, str) or not NAME.fullmatch(profile):
        raise ControlError("invalid profile")
    host = Host()
    state, identity = host.state()
    row = state["profiles"].get(harness + "/" + profile)
    if row is None:
        raise ControlError("unknown saved launch profile")
    repo = row["repo"]
    root = Path(host.config["repositories"][repo]["path"]).resolve()
    if not workspace or not Path(workspace).resolve().is_relative_to(root):
        raise ControlError("selected workspace is outside the profile's repository")
    read = host.authorize("settings.get", harness, profile, repo)
    if read["verdict"]["effect"] != "allow":
        raise ControlError("ABAC denies reading the launch profile: " + json.dumps(read["verdict"]))
    definitions = _settings(harness, row["settings"])
    decisions = [host.authorize("handoff.launch_settings", harness, profile, repo, key, value)
                 for key, value in sorted(row["settings"].items())]
    denied = [d for d in decisions if d["verdict"]["effect"] != "allow"]
    if denied:
        raise ControlError("ABAC denies using these launch settings: " + json.dumps(denied))
    if harness == "codex" and not {"sandbox", "approval"} <= row["settings"].keys():
        raise ControlError("Codex profiles must explicitly select sandbox and approval")
    argv = []
    for key, value in sorted(row["settings"].items()):
        definition = definitions[key]
        if definition["type"] == "bool" and not value:
            continue
        argv.extend(part.replace("{value}", str(value)).replace("{json}", json.dumps(value)) for part in definition["argv"])
    host.unchanged()
    if host.state()[1] != identity:
        raise ControlError("launch profile changed while authorizing")
    return argv, {"profile": profile, "repo": repo, "state_digest": identity,
                  "binding": host.binding, "decisions": decisions,
                  "enforcement_scope": "selected launch settings; child tool calls require native enforcement"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("describe")
    review = sub.add_parser("resolve")
    review.add_argument("--request", required=True, help="bounded settings ambiguity JSON file")
    recovery = sub.add_parser("recover")
    recovery.add_argument("--request", required=True, help="selected target, intent and arbitrary bounded failure context")
    read = sub.add_parser("get")
    for key in ("harness", "profile", "repo"):
        read.add_argument("--" + key, required=True)
    for name in ("plan", "apply"):
        command = sub.add_parser(name)
        command.add_argument("--changes", required=True, help="JSON array file")
        if name == "apply":
            command.add_argument("--expected-digest", required=True)
    args = parser.parse_args()
    try:
        if args.command == "describe":
            result = describe()
        elif args.command == "resolve":
            from mcp_bridge.ambiguity import resolve
            result = resolve(_object(_bytes(Path(args.request))))
        elif args.command == "recover":
            from mcp_bridge.ambiguity import recover
            result = recover(_object(_bytes(Path(args.request))))
        elif args.command == "get":
            result = get(args.harness, args.profile, args.repo)
        else:
            changes = json.loads(_bytes(Path(args.changes)))
            result = plan(changes) if args.command == "plan" else apply(changes, args.expected_digest)
        print(json.dumps(result, indent=2))
        if args.command in {"resolve", "recover"}:
            # A recovery task, denial or needs-input receipt is a valid answer,
            # not a process failure that should trigger orchestration retries.
            return 0
        return 0 if result.get("allowed", result.get("applied", True)) else 2
    except (ControlError, OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        print(json.dumps({"refused": True, "reason": str(exc)}))
        return 2


if __name__ == "__main__":
    sys.exit(main())
