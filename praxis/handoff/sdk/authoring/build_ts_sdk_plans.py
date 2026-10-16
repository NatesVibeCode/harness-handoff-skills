"""Build exact, single-operation TypeScript SDK plans for Forge."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SDK_ROOT = HERE.parent
REPO_ROOT = HERE.parents[3]
sys.path.insert(0, str(HERE))
import build_sdk_plans as common  # noqa: E402

CONTRACTS = {
    name: f"{name}-harness-handoff/contract.json"
    for name, binding in common.BINDINGS.items() if binding["language"] == "typescript"
}
MODULES = {name: common.BINDINGS[name]["module"] for name in CONTRACTS}
PACKAGES = {name: common.BINDINGS[name]["distribution"] for name in CONTRACTS}
OPERATIONS = {name: tuple(common.BINDINGS[name]["operations"]) for name in CONTRACTS}


def raw_sha256(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def main() -> None:
    pins = {name: binding["version"] for name, binding in common.BINDINGS.items() if binding["language"] == "typescript"}
    common.write_json(HERE / "typescript-sdk-pins.json", {"schema": "praxis.harness_sdk_pins.v1", "pins": pins})
    adapter_src = REPO_ROOT / "mcp_bridge/sdk_ts_adapters.mjs"
    runner_src = REPO_ROOT / "mcp_bridge/sdk_ts_runner.mjs"
    assets = HERE / "assets/worker/sdk/typescript"
    assets.mkdir(parents=True, exist_ok=True)
    adapter_asset = assets / "adapters.mjs"
    runner_asset = assets / "run.mjs"
    shutil.copyfile(adapter_src, adapter_asset)
    shutil.copyfile(runner_src, runner_asset)
    adapter_digest = raw_sha256(adapter_asset.read_bytes())
    runner_digest = raw_sha256(runner_asset.read_bytes())
    dispatch_raw = (HERE / "assets/sdk_dispatch.go").read_bytes()
    dispatch_digest = common.source_digest(dispatch_raw)

    pins_for_atlas = []
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
        pins_for_atlas.append({"name": harness, "path": os.path.relpath(path, HERE), "digest": digest})

    stores_path = HERE / "stores.json"
    stores = common.read_json(stores_path)
    prior = {item["name"]: item for item in stores.get("contracts", [])}
    prior.update({item["name"]: item for item in pins_for_atlas})
    stores["contracts"] = [prior[name] for name in sorted(prior)]
    common.write_json(stores_path, stores)

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
                language="typescript",
                module=module,
                entrypoint=entrypoint,
                adapter=adapter,
            )


if __name__ == "__main__":
    main()
