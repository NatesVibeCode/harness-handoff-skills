"""Build typed action Blocks backed by the existing SDK Nodes.

Two shapes share this generator:

* the module harnesses, whose Node imports a pinned npm distribution through
  the shared runner/adapter pair copied from ``mcp_bridge/``;
* DeepSeek Harness, whose generated contract declares ``sdk.kind: "protocol"``.
  A protocol Node owns the wire protocol in its own pinned runner/adapter and
  has no vendor package to import, so its plan carries no package, module or
  entrypoint and Forge passes no distribution selection to the worker.

The protocol runner/adapter under ``assets/dsh/`` are Node-owned sources: they
started as byte-identical copies of ``mcp_bridge/sdk_ts_runner.mjs`` and
``mcp_bridge/sdk_ts_adapters.mjs`` and carry the DSH-only session ledger. They
are deliberately not copied back from ``mcp_bridge/`` on every run, because the
shared pair serves the five module harnesses whose pinned bytes must not drift.
"""

from __future__ import annotations

import hashlib
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SDK_ROOT = HERE.parent
REPO_ROOT = HERE.parents[3]
sys.path.insert(0, str(HERE))
import build_sdk_plans as common  # noqa: E402
import sdk_contracts  # noqa: E402

CONTRACTS = sdk_contracts.TYPESCRIPT
MODULES = {
    "amp": "@ampcode/sdk",
    "cline": "@cline/sdk",
    "codex": "@openai/codex-sdk",
    "droid": "@factory/droid-sdk/node",
    "opencode": "@opencode-ai/sdk",
}
PACKAGES = {
    "amp": "@ampcode/sdk",
    "cline": "@cline/sdk",
    "codex": "@openai/codex-sdk",
    "droid": "@factory/droid-sdk",
    "opencode": "@opencode-ai/sdk",
}
OPERATIONS = {
    "amp": ("fresh",),
    "cline": ("fresh",),
    "codex": ("fresh",),
    "droid": ("fresh",),
    "opencode": ("fresh",),
}

# DeepSeek Harness: protocol-kind. The generated contract is pinned by
# stores-dsh.json, its exact text ships inside the worker's contract envelope,
# and the Node runs dsh's own ACP stdio profile through the pinned runner.
PROTOCOL = {
    "harness": "dsh",
    "contract": REPO_ROOT / "dsh-harness-handoff/contract.json",
    "operation": "session_turn",
    "adapter": "dsh",
    "language": "typescript",
    "runner_file": "worker/sdk/typescript/run.mjs",
    "adapter_file": "worker/sdk/typescript/adapters.mjs",
    "contract_file": "worker/harness.json",
    "runner_source": HERE / "assets/dsh/sdk_ts_runner.mjs",
    "adapter_source": HERE / "assets/dsh/sdk_ts_adapters.mjs",
    "envelope": HERE / "assets/dsh/harness.json",
    "node_dir": "nodes/dsh-typescript-session",
    "plan": "plan-dsh-typescript-session.json",
    "stores": "stores-dsh.json",
    "runtime": "/opt/homebrew/bin/node",
    "binary": "/opt/homebrew/bin/dsh",
}
PROTOCOL_NODE_NAME = "harness.sdk.dsh.session"


def raw_sha256(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def executable_sha256(path: str) -> str:
    resolved = os.path.realpath(path)
    if not os.path.isfile(resolved) or not os.access(resolved, os.X_OK):
        raise SystemExit(f"{path} is not an executable runtime")
    return hashlib.sha256(Path(resolved).read_bytes()).hexdigest()


def installed_version(path: str) -> str:
    run = subprocess.run([path, "--version"], capture_output=True, text=True)
    version = run.stdout.strip()
    if run.returncode != 0 or not version:
        raise SystemExit(f"{path} --version failed: {run.stderr.strip()}")
    return version


def dsh_field(name: str, side: str, required: bool, intent: str, meaning: str) -> dict:
    field = {
        "side": side,
        "name": name,
        "type": {"type": "string"},
        "required": required,
        "bounds": [common.BOUND],
        "description": {
            "intent": intent,
            "tags": ["harness", "dsh", "acp", side],
            "meaning": meaning,
            "units": "typed value",
            "source": "caller" if side == "input" else "computed",
            "declared_by": "harness-handoff SDK authoring",
        },
    }
    if not required:
        field["default"] = ""
    return field


def protocol_fields() -> list[dict]:
    """The public DSH protocol shape, including its typed route overlay.

    There is deliberately no ownership flag. A caller can name a session; it
    cannot assert that the session may be continued. Route values and the
    overlay path/digest are ordinary runtime inputs, so callers can select a
    different pinned route without rebuilding this Process.
    """
    return [
        dsh_field(
            "prompt", "input", True,
            "One prompt submitted once to the selected DSH ACP session",
            "The single user turn delivered over ACP to the pinned DSH stdio process",
        ),
        dsh_field(
            "workspace", "input", True,
            "Existing absolute workspace selected by the calling Process",
            "The ACP session working directory DSH operates in; DSH file access stays inside this selected workspace, and its durable session ledger is written under this workspace",
        ),
        dsh_field(
            "session_id", "input", False,
            "Exact DSH session identity to continue; empty opens one new session",
            "A non-empty session_id asks to continue that exact session. The pinned runner authorizes continuation only from the durable ledger it wrote inside this workspace after an earlier fresh turn; no input can assert ownership, and an unrecorded or cross-workspace identity is refused before dispatch.",
        ),
        dsh_field(
            "route_provider", "input", True,
            "Provider id requested for this DSH ACP session",
            "The provider id the caller intends the ACP profile's `acp` model route to use; the pinned overlay and returned ACP session configuration must agree with it.",
        ),
        dsh_field(
            "route_model", "input", True,
            "Model id requested for this DSH ACP session",
            "The exact model id the caller intends the ACP profile's `acp` model route to use; the pinned overlay and returned ACP session configuration must agree with it.",
        ),
        dsh_field(
            "route_overlay_path", "input", True,
            "Absolute path to the caller's DSH ACP route overlay",
            "A UTF-8 JSON/YAML patch list containing exactly one `id: acp` row with `config.provider` and `config.model`; the runner checks its exact bytes and route, then snapshots those bytes before DSH starts.",
        ),
        dsh_field(
            "route_overlay_digest", "input", True,
            "Expected sha256 digest of the exact route overlay bytes",
            "The caller-supplied `sha256:<64 lowercase hex>` identity of route_overlay_path; the runner refuses missing, changed, or mismatched bytes before importing the adapter or starting DSH.",
        ),
        dsh_field(
            "session_id", "output", True,
            "Exact DSH session identity this call ran under",
            "The ACP session identity returned by session/new or restored by session/resume, and recorded in the workspace ledger on a fresh turn",
        ),
        dsh_field(
            "output", "output", True,
            "The single assistant output returned by the DSH ACP session",
            "The task text DSH delivered for the submitted prompt; partial or multi-part deliveries are not concatenated into a fabricated single value",
        ),
        dsh_field(
            "stop_reason", "output", True,
            "The stop reason DSH reported for the completed ACP turn",
            "The stop reason carried by the ACP turn result, reported verbatim; this Node completes only on end_turn",
        ),
        dsh_field("route_requested_provider", "output", True, "Provider requested by the Process caller", "The route_provider input value, labeled as requested rather than observed"),
        dsh_field("route_requested_model", "output", True, "Model requested by the Process caller", "The route_model input value, labeled as requested rather than observed"),
        dsh_field("route_configured_provider", "output", True, "Provider serialized into the validated ACP overlay", "The provider value parsed from the exact, digest-verified `id: acp` overlay row"),
        dsh_field("route_configured_model", "output", True, "Model serialized into the validated ACP overlay", "The model value parsed from the exact, digest-verified `id: acp` overlay row"),
        dsh_field("route_observed_provider", "output", True, "Provider reported by the created or resumed ACP session", "The provider decoded from the DSH `model` config option returned by `session/new` or `session/resume`"),
        dsh_field("route_observed_model", "output", True, "Model reported by the created or resumed ACP session", "The model decoded from the DSH `model` config option returned by `session/new` or `session/resume`"),
        dsh_field("route_overlay_sha256", "output", True, "sha256 identity of the exact overlay bytes passed to DSH", "The computed `sha256:<64 lowercase hex>` digest of the validated overlay snapshot used for this session"),
        dsh_field("route_observation_source", "output", True, "ACP response field used as actual route evidence", "Either `session/new.configOptions[model].currentValue` or `session/resume.configOptions[model].currentValue`"),
        dsh_field("route_observed_value", "output", True, "Exact ACP model-option currentValue used as route evidence", "The raw JSON string returned by DSH for the model option, retained alongside the parsed provider and model"),
    ]


def protocol_node_spec(
    contract: dict,
    contract_digest: str,
    version: str,
    digests: dict[str, str],
    dispatch_source_digest: str,
) -> dict:
    fields = protocol_fields()
    input_names = [field["name"] for field in fields if field["side"] == "input"]
    output_names = [field["name"] for field in fields if field["side"] == "output"]
    material = {
        PROTOCOL["contract_file"]: digests[PROTOCOL["contract_file"]],
        PROTOCOL["runner_file"]: digests[PROTOCOL["runner_file"]],
        PROTOCOL["adapter_file"]: digests[PROTOCOL["adapter_file"]],
    }
    handoff_sdk = {
        "contract_file": PROTOCOL["contract_file"],
        "working_directory_slot": "workspace",
        "language": PROTOCOL["language"],
        "version": version,
        "operation": PROTOCOL["operation"],
        "adapter": PROTOCOL["adapter"],
        "adapter_digest": digests[PROTOCOL["adapter_file"]],
        "runner_digest": digests[PROTOCOL["runner_file"]],
        "contract_digest": digests[PROTOCOL["contract_file"]],
        # The pinned runner reads no separate bindings document; its binding
        # table ships inside the runner bytes, so the envelope is the only
        # document this Node can name for that pin.
        "bindings_digest": digests[PROTOCOL["contract_file"]],
        "dispatch_source_digest": dispatch_source_digest,
        "dispatch_pointer": "sdkdispatch.Run",
        "runner_file": PROTOCOL["runner_file"],
        "files": material,
        "runtime": {
            "binary": PROTOCOL["runtime"],
            "sha256": executable_sha256(PROTOCOL["runtime"]),
            "arguments": [],
            "timeout_ms": 0,
            "bundle_file": "",
            "bundle_digest": "",
            "target": "",
        },
        "environment": [],
    }
    return {
        "composition": {
            "schema": "praxis.capability_contract.v1",
            "inputs": {
                name: {"semantic": f"{PROTOCOL_NODE_NAME}.{name}{'.in' if name == 'session_id' else ''}.v1"}
                for name in input_names
            },
            "outputs": {
                name: {"semantic": f"{PROTOCOL_NODE_NAME}.{name}.out.v1"}
                for name in output_names
            },
            "outcomes": ["completed"],
            "effects": ["harness.invoke"],
            "failure": "error",
        },
        "schema": "aeltum.node_spec.v1",
        "identity": {"name": PROTOCOL_NODE_NAME, "kind": "harness"},
        "pattern": common.PATTERN,
        "fields": fields,
        "dimensions": [
            {
                "name": "surface",
                "contents": {
                    "entry": "invoke_pinned_typescript_protocol",
                    "inputs": [{"field": name, "target": f"slot:{name}"} for name in input_names],
                    "outputs": [{"field": name, "target": f"result:{name}"} for name in output_names],
                },
            },
            {
                "name": "access",
                "contents": {
                    "share": {
                        "identity": "operator-sdk-account:dsh",
                        "digests": [contract_digest.removeprefix("sha256:")],
                    }
                },
            },
            {
                "name": "handoff",
                "contents": {
                    "harness": PROTOCOL["harness"],
                    "executor": "sdk",
                    "contract": {"digest": contract_digest},
                    "ownership": "customer",
                    "sdk": handoff_sdk,
                },
            },
            {"name": "fields", "contents": None},
            {"name": "field_types", "contents": None},
        ],
        "proof_spec": {
            "behavior": [],
            "test": {"pointer": "", "digest": ""},
            "target": "sdk-runtime",
            "mode": "real_service",
        },
        "usage": {
            "purpose": "Dispatch exactly one prompt to DeepSeek Harness over one ACP stdio session and return its session identity, output, stop reason and requested/configured/observed route evidence, continuing only when this workspace's durable ledger records the same session, workspace and route overlay.",
            "use_when": [
                "one caller-bounded prompt must be delegated to DeepSeek Harness over ACP using an exact typed provider/model route and content-pinned overlay",
                "an earlier DSH session identity that this workspace's ledger recorded must be continued under the exact workspace, provider, model and overlay identity",
            ],
            "avoid_when": [
                "the pinned DSH ACP protocol, runner bytes or actual session route cannot be observed",
                "a session identity not recorded for this workspace and route, a caller-asserted ownership flag, silent route fallback or an alternate surface is requested",
            ],
        },
    }


def protocol_plan(input_names: list[str], output_names: list[str]) -> dict:
    block_inputs = [{"name": name, "to": {"node": "invoke", "port": name}} for name in input_names]
    outputs = [{"name": name, "from": {"node": "invoke", "port": name}} for name in output_names]
    return {
        "schema": "forge.author_plan.v1",
        "module": "github.com/natesvibecode/harness-handoff/praxis/handoff/sdk",
        "library": True,
        "nodes": [
            {
                "key": "invoke",
                "spec_file": f"{PROTOCOL['node_dir']}/spec.json",
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
                "name": "harness.sdk.dsh.session_turn",
                "nodes": [{"key": "invoke", "node": "invoke"}],
                "inputs": block_inputs,
                "outputs": outputs,
            }
        ],
        "assets": [
            {"rel_path": PROTOCOL["contract_file"], "file": str(PROTOCOL["envelope"].relative_to(HERE))},
            {"rel_path": PROTOCOL["runner_file"], "file": str(PROTOCOL["runner_source"].relative_to(HERE))},
            {"rel_path": PROTOCOL["adapter_file"], "file": str(PROTOCOL["adapter_source"].relative_to(HERE))},
        ],
    }


def protocol_stores(contract_digest: str) -> dict:
    return {
        "schema": "atlas.forge_stores.v1",
        "patterns": [
            {
                "record": {"kind": "node", "key": "node.v1", "schema_urn": "aeltum.node_spec.v1"},
                "digest": common.PATTERN["digest"],
            }
        ],
        "bounds": [
            {
                "entry": {
                    "key": common.BOUND["key"],
                    "kind": "count",
                    "subject": "length(*)",
                    "params": {"min": 0.0},
                },
                "digest": common.BOUND["digest"],
            }
        ],
        "nodes": [],
        "demands": [],
        "capabilities": [],
        "pointers": [],
        "routes": [],
        "prompts": [],
        "interpreters": [],
        "contracts": [
            {
                "name": PROTOCOL["harness"],
                "path": os.path.relpath(PROTOCOL["contract"], HERE),
                "digest": contract_digest,
            }
        ],
    }


def build_protocol(pins: dict[str, str], dispatch_source_digest: str) -> None:
    contract_raw = PROTOCOL["contract"].read_bytes()
    contract = json.loads(contract_raw)
    sdk = contract.get("sdk", {})
    if sdk.get("kind") != "protocol":
        raise SystemExit("dsh contract is not protocol-kind")
    if sdk.get("packages") or sdk.get("entrypoints"):
        raise SystemExit("dsh protocol contract declares SDK module selections")
    contract_digest = sdk_contracts.contract_digest(contract_raw)

    envelope = {"contracts": {PROTOCOL["harness"]: contract_raw.decode("utf-8")}}
    common.write_json(PROTOCOL["envelope"], envelope)
    reread = json.loads(PROTOCOL["envelope"].read_bytes())
    if sdk_contracts.contract_digest(reread["contracts"][PROTOCOL["harness"]].encode("utf-8")) != contract_digest:
        raise SystemExit("dsh contract envelope changed the pinned contract text")

    digests = {
        PROTOCOL["contract_file"]: raw_sha256(PROTOCOL["envelope"].read_bytes()),
        PROTOCOL["runner_file"]: raw_sha256(PROTOCOL["runner_source"].read_bytes()),
        PROTOCOL["adapter_file"]: raw_sha256(PROTOCOL["adapter_source"].read_bytes()),
    }
    version = pins[PROTOCOL["harness"]]
    observed = installed_version(PROTOCOL["binary"])
    if observed != version:
        raise SystemExit(
            f"dsh pin {version} differs from the installed {PROTOCOL['binary']} {observed}"
        )

    spec = protocol_node_spec(contract, contract_digest, version, digests, dispatch_source_digest)
    common.write_json(HERE / PROTOCOL["node_dir"] / "spec.json", spec)
    input_names = [field["name"] for field in spec["fields"] if field["side"] == "input"]
    output_names = [field["name"] for field in spec["fields"] if field["side"] == "output"]
    common.write_json(HERE / PROTOCOL["plan"], protocol_plan(input_names, output_names))
    common.write_json(HERE / PROTOCOL["stores"], protocol_stores(contract_digest))


def main() -> None:
    parser = argparse.ArgumentParser(description="Build TypeScript SDK plans; --dsh-only updates only the DSH protocol authoring inputs")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dsh-only", action="store_true", help="generate the DSH protocol Node, plan, envelope and stores without rewriting module harness assets/plans")
    mode.add_argument("--modules-only", action="store_true", help="generate only the five TypeScript module SDK plans and their private contract envelope")
    parser.add_argument("--typescript-runtime", help="exact absolute Node executable to pin; defaults to the installed node on PATH")
    parser.add_argument("--environment", action="append", default=[], metavar="HARNESS=NAME", help="explicit environment variable name available to one selected harness; repeat as needed")
    args = parser.parse_args()
    pins_doc = json.loads((HERE / "typescript-sdk-pins.json").read_text(encoding="utf-8"))
    pins = pins_doc["pins"]
    dispatch_raw = (HERE / "assets/sdk_dispatch.go").read_bytes()
    dispatch_digest = common.source_digest(dispatch_raw)
    if args.dsh_only:
        if args.typescript_runtime or args.environment:
            parser.error("--dsh-only uses its pinned protocol runtime and does not accept module environment selections")
        build_protocol(pins, dispatch_digest)
        return
    runtime_binary = args.typescript_runtime or shutil.which("node")
    if not runtime_binary:
        parser.error("Node was not found on PATH; select it explicitly with --typescript-runtime")
    runtime = common.runtime_pin(runtime_binary)
    environment = common.parse_environment_overrides(args.environment, CONTRACTS)
    adapter_src = REPO_ROOT / "mcp_bridge/sdk_ts_adapters.mjs"
    runner_src = REPO_ROOT / "mcp_bridge/sdk_ts_runner.mjs"
    assets = HERE / "assets/worker/sdk/typescript"
    assets.mkdir(parents=True, exist_ok=True)
    adapter_asset = assets / "adapters.mjs"
    runner_asset = assets / "run.mjs"
    common.copy_if_changed(adapter_src, adapter_asset)
    common.copy_if_changed(runner_src, runner_asset)
    adapter_digest = raw_sha256(adapter_asset.read_bytes())
    runner_digest = raw_sha256(runner_asset.read_bytes())
    contract_texts = {}
    records = {}
    for harness, relative in CONTRACTS.items():
        path = REPO_ROOT / relative
        raw = path.read_bytes()
        contract = json.loads(raw)
        sdk = contract.get("sdk", {})
        if "typescript" not in sdk.get("packages", {}) or "typescript" not in sdk.get("entrypoints", {}):
            raise SystemExit(f"{harness} contract has no TypeScript SDK package and entrypoint")
        if sdk["packages"]["typescript"] != PACKAGES[harness]:
            raise SystemExit(f"{harness} TypeScript SDK package differs from the generated contract")
        digest = common.contract_digest(raw)
        records[harness] = (contract, digest)
        contract_texts[harness] = raw.decode("utf-8")

    contracts_asset = HERE / "assets/worker/typescript/harness.json"
    contracts_asset.parent.mkdir(parents=True, exist_ok=True)
    common.write_json(contracts_asset, {"contracts": contract_texts})
    contract_file_digest = common.raw_sha256(contracts_asset.read_bytes())
    # The shared store is the union of both generators' declared contracts, so
    # whichever generator runs last leaves the same file and neither carries a
    # name it does not declare.
    stores = common.read_json(HERE / "stores.json")
    stores["contracts"] = sdk_contracts.all_pins()
    common.write_json(HERE / "stores.json", stores)

    for harness, operations in OPERATIONS.items():
        contract, digest = records[harness]
        entrypoint = contract["sdk"]["entrypoints"]["typescript"]
        module = MODULES[harness]
        for operation in operations:
            adapter = f"{harness}_ts_{operation}"
            common.make_plan(
                harness,
                operation,
                contract,
                pins[harness],
                adapter_digest,
                runner_digest,
                dispatch_digest,
                digest,
                contract_file_digest,
                runtime,
                environment[harness],
                language="typescript",
                module=module,
                entrypoint=entrypoint,
                adapter=adapter,
            )

    if not args.modules_only:
        build_protocol(pins, dispatch_digest)


if __name__ == "__main__":
    main()
