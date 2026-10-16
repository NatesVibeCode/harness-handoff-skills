"""Build explicit Forge plans for each supported Python SDK operation."""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
SDK_ROOT = HERE.parent
REPO_ROOT = HERE.parents[3]
sys.path.insert(0, str(REPO_ROOT))
from mcp_bridge.sdk_contract import BINDINGS_PATH, bindings
BINDINGS = bindings()
CONTRACTS = {
    name: f"{name}-harness-handoff/contract.json"
    for name, binding in BINDINGS.items() if binding["language"] == "python"
}
MODULES = {name: BINDINGS[name]["module"] for name in CONTRACTS}
OPERATIONS = {name: tuple(BINDINGS[name]["operations"]) for name in CONTRACTS}
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


def contract_digest(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(b"praxis.harness_contract.v1\x00" + raw).hexdigest()


def source_digest(raw: bytes) -> str:
    return hashlib.sha256(b"praxis.source.go.v1\x00" + raw).hexdigest()


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
        "contract_digest": {"type": "string", "enum": [raw_sha256((REPO_ROOT / ("mcp_bridge/sdk_contract.mjs" if language == "typescript" else "mcp_bridge/sdk_contract.py")).read_bytes())]},
        "bindings_digest": {"type": "string", "enum": [raw_sha256(BINDINGS_PATH.read_bytes())]},
        "settings_digest": {"type": "string"},
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
    if operation != "fresh":
        raise ValueError("Only fresh SDK operations are authored")
    binding = BINDINGS[harness]
    if binding["language"] != language:
        raise ValueError("SDK language differs from the declaration")
    settings = typed_field("settings", "input", True,
                           meaning="Typed SDK settings selected by the calling Process")
    settings["type"] = binding["settings"]
    receipt = typed_field("receipt", "output", True,
                          meaning="Completed SDK assistant output and exact session identity")
    receipt["type"] = {"type": "object"}
    return [typed_field("prompt", "input", True, meaning="One prompt submitted once to a fresh SDK session"),
            typed_field("workspace", "input", True, meaning="Existing absolute workspace selected by the calling Process"),
            settings, receipt]


def field_schema(field: dict, receipt: dict):
    if field["name"] == "receipt":
        field["type"] = receipt
    return field


def node_spec(harness: str, operation: str, contract: dict, package_version: str, adapter_digest: str, runner_digest: str, dispatch_source_digest: str, digest: str, *, language: str = "python", module: str | None = None, entrypoint: str | None = None, adapter: str | None = None):
    sdk = contract["sdk"]
    module = module or MODULES[harness]
    entrypoint = entrypoint or sdk["entrypoints"][language]
    adapter = adapter or f"{harness}_{operation}"
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
            "language": language,
            "package": sdk["packages"][language],
            "version": package_version,
            "module": module,
            "entrypoint": entrypoint,
            "operation": operation,
            "adapter": adapter,
            "adapter_digest": adapter_digest,
            "runner_digest": runner_digest,
            "contract_digest": raw_sha256((REPO_ROOT / ("mcp_bridge/sdk_contract.mjs" if language == "typescript" else "mcp_bridge/sdk_contract.py")).read_bytes()),
            "bindings_digest": raw_sha256(BINDINGS_PATH.read_bytes()),
            "dispatch_source_digest": dispatch_source_digest,
            "dispatch_pointer": "sdkdispatch.Run",
            "runner_file": "worker/sdk/typescript/run.mjs" if language == "typescript" else "worker/sdk/run.py",
            "working_directory_slot": "workspace",
            "files": {},
            "runtime": read_json(HERE / "runtime-pins.json")["runtimes"][language],
            "environment": BINDINGS[harness]["environment"],
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


def handoff_material(node):
    return next(d["contents"]["sdk"] for d in node["dimensions"] if d["name"] == "handoff")


def make_plan(harness: str, operation: str, contract: dict, package_version: str, adapter_digest: str, runner_digest: str, dispatch_source_digest: str, digest: str, *, language: str = "python", module: str | None = None, entrypoint: str | None = None, adapter: str | None = None):
    slug = f"{harness}-{operation}"
    node_fields = operation_fields(harness, operation, language)
    input_names = [field["name"] for field in node_fields if field["side"] == "input"]
    block_inputs = [{"name": name, "to": {"node": "invoke", "port": name}} for name in input_names]
    process_inputs = [{"name": name, "to": {"block": "operation", "port": name}} for name in input_names]
    plan = {
        "schema": "forge.author_plan.v1",
        "module": "github.com/natesvibecode/harness-handoff/praxis/handoff/sdk",
        "tool_name": f"harness_sdk_{language}_{harness}_{operation}",
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
        "process": {
            "name": f"harness.sdk.{harness}.{operation}",
            "policy": {
                "allowed_effects": ["harness.invoke"],
                "acceptance": {
                    "schema": "praxis.process_outcome_coverage.v1",
                    "required_outcomes": [
                        {
                            "id": "pinned_sdk_operation_returned",
                            "purpose": "The selected SDK adapter completed one operation and returned its exact package and source binding.",
                            "owner": {"block": "operation", "node": "invoke"},
                            "node_outcome": "completed",
                            "deliveries": [{"node_output": "receipt", "process_output": "receipt"}],
                        }
                    ],
                },
            },
            "blocks": [{"key": "operation", "block": "operation"}],
            "inputs": process_inputs,
            "outputs": [{"name": "receipt", "from": {"block": "operation", "port": "receipt"}}],
        },
        "assets": [
            {"rel_path": "worker/harness.json", "file": f"assets/worker/harness-{harness}.json"},
            {"rel_path": "worker/sdk/run.py", "file": os.path.relpath(REPO_ROOT / "mcp_bridge/sdk_runner.py", HERE)},
            {"rel_path": "worker/sdk/mcp_bridge/sdk_operations.py", "file": os.path.relpath(REPO_ROOT / "mcp_bridge/sdk_operations.py", HERE)},
            {"rel_path": "worker/sdk/mcp_bridge/sdk_contract.py", "file": os.path.relpath(REPO_ROOT / "mcp_bridge/sdk_contract.py", HERE)},
            {"rel_path": "worker/sdk/mcp_bridge/sdk_bindings.json", "file": os.path.relpath(BINDINGS_PATH, HERE)},
        ],
    }
    if language == "typescript":
        slug = f"{harness}-typescript-{operation}"
        plan["tool_name"] = f"harness_sdk_typescript_{harness}_{operation}"
        plan["nodes"][0]["spec_file"] = f"nodes/{slug}/spec.json"
        plan["blocks"][0]["name"] = f"harness.sdk.typescript.{harness}.{operation}"
        plan["process"]["name"] = f"harness.sdk.typescript.{harness}.{operation}"
        plan["assets"] = [
            {"rel_path": "worker/harness.json", "file": f"assets/worker/harness-{harness}.json"},
            {"rel_path": "worker/sdk/typescript/adapters.mjs", "file": "assets/worker/sdk/typescript/adapters.mjs"},
            {"rel_path": "worker/sdk/typescript/run.mjs", "file": "assets/worker/sdk/typescript/run.mjs"},
            {"rel_path": "worker/sdk/typescript/contract.mjs", "file": os.path.relpath(REPO_ROOT / "mcp_bridge/sdk_contract.mjs", HERE)},
            {"rel_path": "worker/sdk/typescript/sdk_bindings.json", "file": os.path.relpath(BINDINGS_PATH, HERE)},
        ]
    node = node_spec(harness, operation, contract, package_version, adapter_digest, runner_digest, dispatch_source_digest, digest, language=language, module=module, entrypoint=entrypoint, adapter=adapter)
    if language == "typescript":
        node["identity"]["name"] = f"harness.sdk.typescript.{harness}.{operation}"
    # Private material paths let different SDK Nodes and exact revisions coexist.
    material_id = hashlib.sha256(json.dumps(handoff_material(node), sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    private_dir = f"sdk/{harness}-{language}-{operation}/{material_id}"
    plan["nodes"][0]["dispatch"]["dir"] = private_dir
    sdk_root = f"nodes/{private_dir}/runtime"
    for asset in plan["assets"]:
        asset["rel_path"] = asset["rel_path"].replace("worker/harness.json", sdk_root + "/harness.json").replace("worker/sdk/", sdk_root + "/")
    handoff = next(d["contents"] for d in node["dimensions"] if d["name"] == "handoff")
    handoff["sdk"]["runner_file"] = f"{sdk_root}/typescript/run.mjs" if language == "typescript" else f"{sdk_root}/run.py"
    handoff["sdk"]["contract_file"] = f"{sdk_root}/harness.json"
    handoff["sdk"]["files"] = {a["rel_path"]: raw_sha256((HERE/a["file"]).read_bytes()) for a in plan["assets"] if not a["rel_path"].endswith("/harness.json")}
    contract_text = (REPO_ROOT / f"{harness}-harness-handoff/contract.json").read_text(encoding="utf-8")
    write_json(HERE / f"assets/worker/harness-{harness}.json", {"contracts": {harness: contract_text}})
    handoff["sdk"]["files"][handoff["sdk"]["contract_file"]] = raw_sha256((HERE/f"assets/worker/harness-{harness}.json").read_bytes())
    write_json(HERE / "nodes" / slug / "spec.json", node)
    write_json(HERE / f"plan-{slug}.json", plan)
    stores = read_json(HERE / "stores.json")
    stores["contracts"] = [item for item in stores["contracts"] if item["name"] == harness]
    write_json(HERE / f"stores-{slug}.json", stores)


def main() -> None:
    pins = {name: binding["version"] for name, binding in BINDINGS.items() if binding["language"] == "python"}
    write_json(HERE / "python-sdk-pins.json", {"schema": "harness.handoff.python_sdk_pins.v1", "pins": pins})
    adapter_raw = (REPO_ROOT / "mcp_bridge/sdk_operations.py").read_bytes()
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
    (HERE / "assets/sdk_dispatch.go").write_bytes(dispatch_raw)
    dispatch_source_digest = source_digest(dispatch_raw)
    contracts = {}
    pins_for_atlas = []
    for harness, relative in CONTRACTS.items():
        path = REPO_ROOT / relative
        raw = path.read_bytes()
        contract = json.loads(raw)
        if "python" not in contract.get("sdk", {}).get("packages", {}):
            raise SystemExit(f"{harness} contract has no Python SDK package")
        if "python" not in contract.get("sdk", {}).get("entrypoints", {}):
            raise SystemExit(f"{harness} contract has no Python SDK entrypoint")
        digest = contract_digest(raw)
        contracts[harness] = (contract, digest)
        pins_for_atlas.append(
            {"name": harness, "path": os.path.relpath(path, HERE), "digest": digest}
        )
    stores = read_json(SDK_ROOT.parent / "authoring/stores.json")
    stores["contracts"] = pins_for_atlas
    write_json(HERE / "stores.json", stores)

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
            )


if __name__ == "__main__":
    main()
