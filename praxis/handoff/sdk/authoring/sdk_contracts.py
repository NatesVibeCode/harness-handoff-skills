"""The one declaration of the harness contracts the shared SDK store pins.

`stores.json` beside this file is consumed by every generated SDK plan's
`forge-author plan -check`. Forge resolves a contract by harness name plus
pinned digest, and Atlas refuses a manifest that declares one name twice, so
that store may pin each harness exactly once, from the contract bytes this
checkout generates. The declaration below is the whole input: the store is a
pure function of it and never of the copy already on disk, so a name added to
the file by hand cannot survive a regeneration.

A harness whose generated contract is not module-kind is not pinned here: the
generated store backs the SDK module plans, and Forge refuses a protocol
adapter that declares an SDK package, module or entrypoint. `dsh` is that case.
Its `dsh-harness-handoff/contract.json` declares `sdk.kind: "protocol"`, so
`build_ts_sdk_plans.py` generates its Node, plan and `stores-dsh.json` from
that contract directly: the protocol Node pins the contract's purpose digest,
its own runner/adapter bytes and a `worker/harness.json` envelope holding the
exact contract text, and it selects no vendor package at all.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[3]

# The SDK plan generators own these trees, one contract per harness.
PYTHON = {
    "antigravity": "antigravity-harness-handoff/contract.json",
    "claude": "claude-harness-handoff/contract.json",
    "copilot": "copilot-harness-handoff/contract.json",
    "cursor": "cursor-harness-handoff/contract.json",
    "muse": "muse-harness-handoff/contract.json",
    "openhands": "openhands-harness-handoff/contract.json",
}
TYPESCRIPT = {
    "amp": "amp-harness-handoff/contract.json",
    "cline": "cline-harness-handoff/contract.json",
    "codex": "codex-harness-handoff/contract.json",
    "droid": "droid-harness-handoff/contract.json",
    "opencode": "opencode-harness-handoff/contract.json",
}


def contract_digest(raw: bytes) -> str:
    """Return the digest Forge computes over a generated contract's exact bytes."""
    return "sha256:" + hashlib.sha256(b"praxis.harness_contract.v1\x00" + raw).hexdigest()


def all_pins() -> list[dict[str, str]]:
    """Return every pin the shared store declares, sorted by harness name.

    Refuses a second declaration of one name: Atlas rejects such a manifest, and
    a harness whose contract is pinned by both SDK languages is an authoring
    mistake, not a language choice.
    """
    pins: dict[str, dict[str, str]] = {}
    for language, contracts in (("Python", PYTHON), ("TypeScript", TYPESCRIPT)):
        for harness, relative in contracts.items():
            if harness in pins:
                raise SystemExit(
                    f"{harness} is declared by both the Python and TypeScript SDK contracts"
                )
            path = REPO_ROOT / relative
            pins[harness] = {
                "name": harness,
                "path": os.path.relpath(path, HERE),
                "digest": contract_digest(path.read_bytes()),
            }
    return [pins[name] for name in sorted(pins)]
