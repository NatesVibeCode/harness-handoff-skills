"""Contract loader for the harness SDK bridge.

Reads the single source of truth (skills-src/contracts.json) and exposes
per-harness execution contracts to the MCP tools. This module performs no
execution, launches no processes, and touches no credentials.
"""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = REPO_ROOT / "skills-src" / "contracts.json"


class ContractError(ValueError):
    """The contract file is unusable or the harness is unknown."""


def load_contracts(path: Path = CONTRACT_PATH) -> dict:
    """Load and minimally validate the contract document."""
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(f"cannot read contract file {path}: {exc}") from exc
    if document.get("version") != 2:
        raise ContractError(f"{path}: unsupported contract version {document.get('version')!r}")
    harnesses = document.get("harnesses")
    if not isinstance(harnesses, dict) or not harnesses:
        raise ContractError(f"{path}: 'harnesses' must be a non-empty object")
    return document


def get_harness(name: str, document: dict | None = None) -> dict:
    """Return the contract entry for one harness, or raise ContractError."""
    document = document if document is not None else load_contracts()
    try:
        return document["harnesses"][name]
    except KeyError:
        known = ", ".join(sorted(document["harnesses"]))
        raise ContractError(f"unknown harness {name!r}; known harnesses: {known}") from None


def list_harnesses(document: dict | None = None) -> list[dict]:
    """Return a summary row per harness for tool discovery."""
    document = document if document is not None else load_contracts()
    rows = []
    for name, entry in sorted(document["harnesses"].items()):
        sdk = entry["sdk"]
        rows.append(
            {
                "harness": name,
                "title": entry["title"],
                "binary": entry["binary"],
                "sdk_kind": sdk["kind"],
                "sdk_status": sdk["status"],
                "sdk_languages": sdk["languages"],
                "fresh": sdk["fresh"],
                "continuation": sdk["continuation"],
                "history": sdk["history"],
            }
        )
    return rows
