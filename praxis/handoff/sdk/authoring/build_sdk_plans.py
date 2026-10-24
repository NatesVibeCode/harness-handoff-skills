"""Build explicit Forge plans for each supported Python SDK operation."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sdk_contracts  # noqa: E402
from sdk_contracts import contract_digest  # noqa: E402

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[3]
CONTRACTS = sdk_contracts.PYTHON
MODULES = {
    "antigravity": "google.antigravity",
    "claude": "claude_agent_sdk",
    "copilot": "copilot",
    "cursor": "cursor_sdk",
    "muse": "muse_code",
    "openhands": "openhands.sdk",
}
OPERATIONS = {
    "antigravity": ("fresh",),
    "claude": ("fresh",),
    "copilot": ("fresh",),
    "cursor": ("fresh",),
    "muse": ("fresh",),
    "openhands": ("fresh",),
}
BOUND = {
    "key": "handoff.value.length.nonnegative",
    "digest": "11ee5a5237e83c31468ee3fc471982ea3e1c80b33ea2444d4429707d945d5196",
}
PATTERN = {
    "key": "node.v1",
    "digest": "144731dd834259d024c98b17ea7e62805ce5af074128133790a5dcdfafa0e24f",
}


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def raw_sha256(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def source_digest(raw: bytes) -> str:
    return hashlib.sha256(b"praxis.source.go.v1\x00" + raw).hexdigest()


def runtime_pin(binary: str) -> dict:
    """Bind the exact build-selected runtime without adding a timeout policy."""
    candidate = Path(binary).expanduser()
    if not candidate.is_absolute():
        raise SystemExit("SDK runtime must be selected by an absolute executable path")
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as error:
        raise SystemExit(f"SDK runtime is unavailable: {candidate}: {error}") from error
    if not resolved.is_file() or not os.access(resolved, os.X_OK):
        raise SystemExit(f"SDK runtime is not an executable file: {resolved}")
    digest = hashlib.sha256(resolved.read_bytes()).hexdigest()
    return {
        "binary": str(resolved),
        "sha256": digest,
        "arguments": [],
        "timeout_ms": 0,
        "bundle_file": "",
        "bundle_digest": "",
        "target": "",
    }


def parse_environment_overrides(values: list[str], harnesses) -> dict[str, list[str]]:
    """Parse explicit per-harness environment *names*, never credential values."""
    result = {name: [] for name in harnesses}
    reserved = {"PATH", "HOME", "TMPDIR", "PYTHONPATH", "PYTHONHOME", "NODE_OPTIONS", "NODE_PATH"}
    for raw in values:
        harness, separator, name = raw.partition("=")
        if not separator or harness not in result:
            raise SystemExit(f"--environment must name a selected harness as HARNESS=NAME: {raw!r}")
        if not re.fullmatch(r"[A-Z_][A-Z0-9_]*", name):
            raise SystemExit(f"--environment requires an uppercase variable name: {raw!r}")
        if name in reserved or name.startswith(("PRAXIS_SDK_", "LD_", "DYLD_")):
            raise SystemExit(f"--environment cannot select a reserved runtime variable: {name}")
        if name in result[harness]:
            raise SystemExit(f"duplicate --environment selection for {harness}: {name}")
        result[harness].append(name)
    return result


def copy_if_changed(source: Path, destination: Path) -> None:
    raw = source.read_bytes()
    if destination.is_file() and destination.read_bytes() == raw:
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(raw)


def typed_field(name: str, side: str, required: bool, *, enum=None, meaning: str = "Caller-supplied SDK operation value"):
    scalar = {"type": "string"}
    if enum is not None:
        scalar["enum"] = enum
    field = {
        "side": side,
        "name": name,
        "type": scalar,
        "required": required,
        "bounds": [BOUND],
        "description": {
            "intent": meaning,
            "tags": ["harness", "sdk", side],
            "meaning": meaning,
            "units": "typed value",
            "source": "caller" if side == "input" else "computed",
            "declared_by": "harness-handoff SDK authoring",
        },
    }
    if not required:
        field["default"] = ""
    return field


def receipt_schema(harness: str, operation: str, contract: dict, package_version: str, adapter: str, adapter_digest: str, runner_digest: str):
    return receipt_schema_for_language(
        harness, operation, contract, package_version, adapter, adapter_digest, runner_digest,
        language="python", module=MODULES[harness], entrypoint=contract["sdk"]["entrypoints"]["python"],
    )


def receipt_schema_for_language(harness: str, operation: str, contract: dict, package_version: str, adapter: str, adapter_digest: str, runner_digest: str, *, language: str, module: str, entrypoint: str):
    sdk = contract["sdk"]
    values = {
        "schema": {"type": "string", "enum": ["praxis.harness_sdk_receipt.v1"]},
        "status": {"type": "string", "enum": ["succeeded"]},
        "harness": {"type": "string", "enum": [harness]},
        "sdk_operation": {"type": "string", "enum": [operation]},
        "distribution": {"type": "string", "enum": [sdk["packages"][language]]},
        "distribution_version": {"type": "string", "enum": [package_version]},
        "module": {"type": "string", "enum": [module]},
        "entrypoint": {"type": "string", "enum": [entrypoint]},
        "adapter": {"type": "string", "enum": [adapter]},
        "adapter_digest": {"type": "string", "enum": [adapter_digest]},
        "runner_digest": {"type": "string", "enum": [runner_digest]},
        "session_id": {"type": "string"},
        "output": {"type": "string"},
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": values,
        "required": list(values),
    }


def operation_fields(harness: str, operation: str, language: str = "python"):
    fields = []
    if language == "typescript":
        if operation in ("fresh", "resume"):
            fields.append(typed_field("prompt", "input", True, meaning="One prompt submitted to the pinned TypeScript SDK operation"))
        if operation in ("resume", "history"):
            fields.append(typed_field("session_id", "input", True, meaning="Exact SDK-owned session identifier"))
        fields.append(typed_field("workspace", "input", True, meaning="Explicit local workspace used to resolve the pinned SDK package and operation"))
        if operation == "resume":
            fields.append(typed_field("session_owner", "input", True, enum=["operator_owned"], meaning="Caller assertion that this exact SDK session is operator-owned and authorized for continuation"))
        if operation in ("fresh", "resume") and harness == "amp":
            fields.append(typed_field("approval", "input", True, enum=["native"], meaning="Preserve Amp native permission settings without automatic approval"))
        elif operation in ("fresh", "resume") and harness in ("cline", "droid", "opencode"):
            fields.append(typed_field("approval", "input", True, enum=["deny_unapproved", "unattended"], meaning="Explicit approval boundary for SDK tools"))
        if harness == "cline" and operation in ("fresh", "resume"):
            fields.append(typed_field("provider_id", "input", True, enum=["anthropic", "openai", "google", "gemini", "openrouter", "groq", "mistral", "deepseek"], meaning="Explicit Cline provider identifier supported by the pinned local adapter"))
            fields.append(typed_field("model", "input", True, meaning="Explicit Cline provider model identifier"))
        elif harness in ("droid", "opencode") and operation in ("fresh", "resume"):
            fields.append(typed_field("model", "input", False, meaning="Optional exact provider/model override; empty preserves the selected SDK's native default"))
        fields.append(
            {
                "side": "output",
                "name": "receipt",
                "type": {"type": "object"},
                "required": True,
                "bounds": [BOUND],
                "description": {
                    "intent": "Pinned TypeScript SDK operation result and session identity",
                    "tags": ["harness", "sdk", "receipt"],
                    "meaning": "SDK result and exact execution binding",
                    "units": "typed object",
                    "source": "computed",
                    "declared_by": "harness-handoff SDK authoring",
                },
            }
        )
        return fields
    if operation in ("fresh", "resume"):
        fields.append(typed_field("prompt", "input", True, meaning="One prompt submitted to the pinned SDK operation"))
    if operation in ("resume", "history"):
        fields.append(typed_field("session_id", "input", True, meaning="Exact SDK-owned session identifier"))
    if operation == "fresh" and harness in ("claude", "cursor", "muse", "openhands"):
        fields.append(typed_field("workspace", "input", True, meaning="Explicit local workspace bound to the SDK call"))
    elif operation == "resume" and harness == "claude":
        fields.append(typed_field("workspace", "input", True, meaning="Workspace used to resolve the exact SDK session"))
    elif operation == "history" and harness == "claude":
        fields.append(typed_field("workspace", "input", True, meaning="Workspace used to resolve the exact SDK session"))
    if operation == "fresh" and harness in ("cursor", "copilot", "openhands"):
        fields.append(typed_field("model", "input", True, meaning="Explicit model identifier required by this SDK adapter"))
    if harness == "copilot" and operation in ("fresh", "resume"):
        fields.append(typed_field("approval", "input", True, enum=["unattended"], meaning="Explicit authorization for the adapter's approve_all permission handler"))
    if harness == "antigravity" and operation == "resume":
        fields.append(typed_field("save_dir", "input", True, meaning="Owning SDK save directory required for exact session restore"))
        fields.append(typed_field("app_data_dir", "input", False, meaning="SDK application data directory used by exact session restore"))
    if operation == "history":
        fields.append(typed_field("limit", "input", True, meaning="Positive decimal count requested from the history SDK operation; caller controls the requested count"))
    fields.append(
        {
            "side": "output",
            "name": "receipt",
            "type": {"type": "object"},
            "required": True,
            "bounds": [BOUND],
            "description": {
                "intent": "Pinned SDK operation result and session identity",
                "tags": ["harness", "sdk", "receipt"],
                "meaning": "SDK result and exact execution binding",
                "units": "typed object",
                "source": "computed",
                "declared_by": "harness-handoff SDK authoring",
            },
        }
    )
    return fields


def field_schema(field: dict, receipt: dict):
    if field["name"] == "receipt":
        field["type"] = receipt
    return field


def node_spec(harness: str, operation: str, contract: dict, package_version: str, adapter_digest: str, runner_digest: str, dispatch_source_digest: str, digest: str, contract_file_digest: str, runtime: dict, environment: list[str], *, language: str = "python", module: str | None = None, entrypoint: str | None = None, adapter: str | None = None):
    sdk = contract["sdk"]
    module = module or MODULES[harness]
    entrypoint = entrypoint or sdk["entrypoints"][language]
    adapter = adapter or f"{harness}_{operation}"
    if language == "typescript":
        runner_file = "worker/sdk/typescript/run.mjs"
        adapter_file = "worker/sdk/typescript/adapters.mjs"
    else:
        runner_file = "worker/sdk/run.py"
        adapter_file = "worker/sdk/mcp_bridge/sdk_executors.py"
    material = {
        "worker/harness.json": contract_file_digest,
        runner_file: runner_digest,
        adapter_file: adapter_digest,
    }
    fields = operation_fields(harness, operation, language)
    receipt = receipt_schema_for_language(harness, operation, contract, package_version, adapter, adapter_digest, runner_digest, language=language, module=module, entrypoint=entrypoint)
    fields = [field_schema(field, receipt) for field in fields]
    input_fields = [field["name"] for field in fields if field["side"] == "input"]
    composition_inputs = {
        name: {"semantic": f"harness.sdk.{harness}.{operation}.{name}.v1"}
        for name in input_fields
    }
    composition = {
        "schema": "praxis.capability_contract.v1",
        "inputs": composition_inputs,
        "outputs": {"receipt": {"semantic": f"harness.sdk.{harness}.{operation}.receipt.v1"}},
        "outcomes": ["completed"],
        "effects": ["harness.invoke"],
        "failure": "error",
    }
    target_inputs = [
        {"field": name, "target": f"slot:{name}"}
        for name in input_fields
    ]
    handoff = {
        "harness": harness,
        "executor": "sdk",
        "contract": {"digest": digest},
        "ownership": "customer",
        "interactivity": contract["interactivity"],
        "credential_channel": contract["credential_channel"],
        "credential_auth": contract["credential_auth"],
        "sdk": {
            "contract_file": "worker/harness.json",
            "working_directory_slot": "workspace" if "workspace" in input_fields else "",
            "language": language,
            "package": sdk["packages"][language],
            "version": package_version,
            "module": module,
            "entrypoint": entrypoint,
            "operation": operation,
            "adapter": adapter,
            "adapter_digest": adapter_digest,
            "runner_digest": runner_digest,
            "contract_digest": contract_file_digest,
            "bindings_digest": contract_file_digest,
            "dispatch_source_digest": dispatch_source_digest,
            "dispatch_pointer": "sdkdispatch.Run",
            "runner_file": runner_file,
            "files": material,
            "runtime": runtime,
            "environment": environment,
        },
    }
    return {
        "composition": composition,
        "schema": "aeltum.node_spec.v1",
        "identity": {"name": f"harness.sdk.{harness}.{operation}", "kind": "harness"},
        "pattern": PATTERN,
        "fields": fields,
        "dimensions": [
            {
                "name": "surface",
                "contents": {
                    "entry": "invoke_pinned_typescript_sdk" if language == "typescript" else "invoke_pinned_python_sdk",
                    "inputs": target_inputs,
                    "outputs": [{"field": "receipt", "target": "result:json"}],
                },
            },
            {
                "name": "access",
                "contents": {
                    "share": {
                        "identity": f"operator-sdk-account:{harness}",
                        "digests": [digest.removeprefix("sha256:")],
                    }
                },
            },
            {"name": "handoff", "contents": handoff},
            {"name": "fields", "contents": None},
            {"name": "field_types", "contents": None},
        ],
        "proof_spec": {"behavior": [], "test": {"pointer": "", "digest": ""}, "target": "sdk-runtime", "mode": "real_service"},
        "usage": {
            "purpose": f"Invoke exactly one {harness} {language.title()} SDK {operation} operation through its pinned adapter and return a bound receipt.",
            "use_when": [f"an explicit {harness} SDK {operation} operation is selected"],
            "avoid_when": ["the selected SDK package version or exact session identity is unknown"],
        },
    }


def make_plan(harness: str, operation: str, contract: dict, package_version: str, adapter_digest: str, runner_digest: str, dispatch_source_digest: str, digest: str, contract_file_digest: str, runtime: dict, environment: list[str], *, language: str = "python", module: str | None = None, entrypoint: str | None = None, adapter: str | None = None):
    slug = f"{harness}-{operation}"
    node_fields = operation_fields(harness, operation, language)
    input_names = [field["name"] for field in node_fields if field["side"] == "input"]
    block_inputs = [{"name": name, "to": {"node": "invoke", "port": name}} for name in input_names]
    plan = {
        "schema": "forge.author_plan.v1",
        "module": "github.com/natesvibecode/harness-handoff/praxis/handoff/sdk",
        "library": True,
        "nodes": [
            {
                "key": "invoke",
                "spec_file": f"nodes/{slug}/spec.json",
                "source_file": "assets/sdk_dispatch.go",
                "dispatch": {
                    "dir": "invoke",
                    "file": "spec.json",
                    "source_file": "sdk_dispatch.go",
                    "package": "sdkdispatch",
                    "symbol": "Run",
                },
            }
        ],
        "blocks": [
            {
                "key": "operation",
                "name": f"harness.sdk.{harness}.{operation}",
                "nodes": [{"key": "invoke", "node": "invoke"}],
                "inputs": block_inputs,
                "outputs": [{"name": "receipt", "from": {"node": "invoke", "port": "receipt"}}],
            }
        ],
        "assets": [
            {"rel_path": "worker/harness.json", "file": "assets/worker/python/harness.json"},
            {"rel_path": "worker/sdk/run.py", "file": os.path.relpath(REPO_ROOT / "mcp_bridge/sdk_runner.py", HERE)},
            {"rel_path": "worker/sdk/mcp_bridge/sdk_executors.py", "file": os.path.relpath(REPO_ROOT / "mcp_bridge/sdk_executors.py", HERE)},
        ],
    }
    if language == "typescript":
        slug = f"{harness}-typescript-{operation}"
        plan["nodes"][0]["spec_file"] = f"nodes/{slug}/spec.json"
        plan["blocks"][0]["name"] = f"harness.sdk.typescript.{harness}.{operation}"
        plan["assets"] = [
            {"rel_path": "worker/harness.json", "file": "assets/worker/typescript/harness.json"},
            {"rel_path": "worker/sdk/typescript/adapters.mjs", "file": "assets/worker/sdk/typescript/adapters.mjs"},
            {"rel_path": "worker/sdk/typescript/run.mjs", "file": "assets/worker/sdk/typescript/run.mjs"},
        ]
    node = node_spec(
        harness,
        operation,
        contract,
        package_version,
        adapter_digest,
        runner_digest,
        dispatch_source_digest,
        digest,
        contract_file_digest,
        runtime,
        environment,
        language=language,
        module=module,
        entrypoint=entrypoint,
        adapter=adapter,
    )
    if language == "typescript":
        node["identity"]["name"] = f"harness.sdk.typescript.{harness}.{operation}"
    write_json(HERE / "nodes" / slug / "spec.json", node)
    write_json(HERE / f"plan-{slug}.json", plan)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build typed Python SDK action Blocks")
    parser.add_argument("--python-runtime", help="exact absolute Python executable to pin; defaults to this generator's sys.executable")
    parser.add_argument("--environment", action="append", default=[], metavar="HARNESS=NAME", help="explicit environment variable name available to one selected harness; repeat as needed")
    args = parser.parse_args()

    pins_doc = read_json(HERE / "python-sdk-pins.json")
    pins = pins_doc["pins"]
    runtime = runtime_pin(args.python_runtime or sys.executable)
    environment = parse_environment_overrides(args.environment, CONTRACTS)
    adapter_raw = (REPO_ROOT / "mcp_bridge/sdk_executors.py").read_bytes()
    runner_raw = (REPO_ROOT / "mcp_bridge/sdk_runner.py").read_bytes()
    adapter_digest = raw_sha256(adapter_raw)
    runner_digest = raw_sha256(runner_raw)
    dispatch_source = (
        "package sdkdispatch\n\n"
        "import \"errors\"\n\n"
        "// Run exists only to satisfy Forge's sealed dispatch package. The printed\n"
        "// worker binds harness Nodes to its pinned SDK runtime before execution.\n"
        "func Run(map[string]any) (map[string]any, error) {\n"
        "\treturn nil, errors.New(\"harness SDK Node requires the printed SDK runtime\")\n"
        "}\n"
    )
    dispatch_raw = dispatch_source.encode("utf-8")
    dispatch_path = HERE / "assets/sdk_dispatch.go"
    if not dispatch_path.is_file() or dispatch_path.read_bytes() != dispatch_raw:
        dispatch_path.write_bytes(dispatch_raw)
    dispatch_source_digest = source_digest(dispatch_raw)
    contracts = {}
    contract_texts = {}
    for harness, relative in CONTRACTS.items():
        path = REPO_ROOT / relative
        raw = path.read_bytes()
        contract = json.loads(raw)
        if "python" not in contract.get("sdk", {}).get("packages", {}):
            raise SystemExit(f"{harness} contract has no Python SDK package")
        if "python" not in contract.get("sdk", {}).get("entrypoints", {}):
            raise SystemExit(f"{harness} contract has no Python SDK entrypoint")
        if not MODULES.get(harness) or not contract["sdk"]["packages"]["python"]:
            raise SystemExit(f"{harness} contract has no exact Python module binding")
        digest = contract_digest(raw)
        contracts[harness] = (contract, digest)
        contract_texts[harness] = raw.decode("utf-8")
    # The shared store is the union of both generators' declared contracts, so
    # whichever generator runs last leaves the same file and neither carries a
    # name it does not declare.
    stores = read_json(HERE / "stores.json")
    stores["contracts"] = sdk_contracts.all_pins()
    write_json(HERE / "stores.json", stores)
    envelope = HERE / "assets/worker/python/harness.json"
    write_json(envelope, {"contracts": contract_texts})
    contract_file_digest = raw_sha256(envelope.read_bytes())

    for harness, operations in OPERATIONS.items():
        contract, digest = contracts[harness]
        for operation in operations:
            make_plan(
                harness,
                operation,
                contract,
                pins[harness],
                adapter_digest,
                runner_digest,
                dispatch_source_digest,
                digest,
                contract_file_digest,
                runtime,
                environment[harness],
            )


if __name__ == "__main__":
    main()
