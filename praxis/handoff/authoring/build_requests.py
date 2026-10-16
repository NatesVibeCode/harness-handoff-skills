#!/usr/bin/env python3
"""Generate the closed Forge Runway requests and explicit authoring plan."""

from __future__ import annotations

import json
import hashlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUTHORING = ROOT / "authoring"
RUNWAY = AUTHORING / "runway"
MODULE_PATH = "github.com/natesvibecode/harness-handoff/praxis/handoff"
BOUND_ENTRY = {
    "key": "handoff.value.length.nonnegative",
    "kind": "count",
    "subject": "length(*)",
    "params": {"min": 0.0},
}


def bound_digest(entry):
    payload = json.dumps(
        {"purpose": "praxis.bound.v1", "value": entry},
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def field(name, side, semantic, kind, meaning):
    return {
        "name": name,
        "side": side,
        "semantic": semantic,
        "intent": meaning,
        "meaning": meaning,
        "tags": ["handoff", "typed"],
        "type": kind,
        "required": True,
        "bounds": [{"key": BOUND_ENTRY["key"], "digest": bound_digest(BOUND_ENTRY)}],
    }


def reuse_port(name, semantic, kind):
    return {"name": name, "type": kind, "semantic": semantic, "required": True}


def request(identity, destination, task):
    return {
        "schema": "harness.handoff_request.v1",
        "identity_context": identity,
        "destination": destination,
        "task": task,
    }


def main():
    request_schema = read_json(ROOT / "contracts" / "handoff-request.schema.json")
    packet_schema = read_json(ROOT / "contracts" / "handoff-packet.schema.json")
    request_type = {key: value for key, value in request_schema.items() if not key.startswith("$")}
    packet_type = {key: value for key, value in packet_schema.items() if not key.startswith("$")}
    write_json(AUTHORING / "stores.json", {
        "schema": "atlas.forge_stores.v1",
        "patterns": [{
            "record": {"kind": "node", "key": "node.v1", "schema_urn": "aeltum.node_spec.v1"},
            "digest": "144731dd834259d024c98b17ea7e62805ce5af074128133790a5dcdfafa0e24f",
        }],
        "bounds": [{"entry": BOUND_ENTRY, "digest": bound_digest(BOUND_ENTRY)}],
        "nodes": [],
        "demands": [],
        "capabilities": [],
        "pointers": [],
        "routes": [],
        "prompts": [],
        "interpreters": [],
    })

    identity = {
        "operator_identity": "",
        "current_product_interaction": "",
        "current_client_or_harness": "",
        "current_channel": "",
        "current_inference_mechanism": "",
        "current_execution_adapter": "",
    }
    task = {
        "direct_instruction": "Carry out the explicitly selected task.",
        "current_state": "Current state supplied by the operator.",
        "next_action": "Inspect the selected workspace and continue the task.",
        "constraints": ["Preserve the direct instruction and selected target."],
        "acceptance_criteria": ["Return the completed result and evidence."],
        "evidence_refs": [],
    }
    fresh = request(identity, {
        "product": "Codex",
        "harness": "codex",
        "client_or_harness": "Codex CLI",
        "channel": "CLI",
        "inference_mechanism": "harness.direct",
        "execution_adapter": "cli.codex.fresh",
        "operation": "fresh",
        "route": "cli",
        "workspace": "/selected/workspace",
        "session_id": "",
    }, task)
    invalid_continue = request(identity, {
        "product": "Codex",
        "harness": "codex",
        "client_or_harness": "Codex CLI",
        "channel": "CLI",
        "inference_mechanism": "harness.direct",
        "execution_adapter": "cli.codex.continue",
        "operation": "continue",
        "route": "cli",
        "workspace": "",
        "session_id": "",
    }, task)
    manual = request(identity, {
        "product": "Muse Code",
        "harness": "muse",
        "client_or_harness": "Muse Code desktop",
        "channel": "manual paste",
        "inference_mechanism": "pending operator selection",
        "execution_adapter": "manual-copy",
        "operation": "manual",
        "route": "manual",
        "workspace": "",
        "session_id": "",
    }, {
        **task,
        "direct_instruction": "Preserve this example instruction verbatim.",
        "next_action": "Paste the packet into the selected Muse workspace.",
    })
    write_json(AUTHORING / "example-request.json", manual)

    write_json(AUTHORING / "atlas-reuse-query.json", {
        "schema": "atlas.reuse_query.v1",
        "purpose_terms": ["cross-harness handoff", "explicit destination", "preserve direct instruction", "portable task packet"],
        "inputs": [reuse_port("request", "handoff.request.v1", request_type)],
        "outputs": [
            reuse_port("handoff_packet", "handoff.packet.v1", packet_type),
            reuse_port("handoff_prompt", "handoff.prompt.v1", {"type": "string"}),
            reuse_port("packet_sha256", "handoff.packet.sha256", {"type": "string"}),
        ],
        "allowed_effects": [],
    })

    def runway(name, purpose, use_when, pointer, fields, cases):
        return {
            "schema": "forge.author_runway_request.v1",
            "function": {
                "name": name,
                "purpose": purpose,
                "use_when": use_when,
                "avoid_when": ["an actual harness launch or authorization decision is required"],
                "tags": ["harness-handoff", "portable-packet"],
                "declared_by": "harness-handoff authoring",
                "code_pointer": pointer,
                "pattern": {"key": "node.v1", "digest": "144731dd834259d024c98b17ea7e62805ce5af074128133790a5dcdfafa0e24f"},
                "fields": fields,
                "cases": cases,
            },
            "source_file": "../../module/nodes/" + pointer.split("/nodes/", 1)[1].rsplit(".", 1)[0].replace(".", "/") + "/entry.go",
        }

    gate = runway(
        "handoff.request.validate",
        "Validate that a portable handoff request names its task, explicit destination, operation, route, next action, and acceptance criteria.",
        ["a typed request must be checked before a handoff packet is assembled"],
        MODULE_PATH + "/nodes/requestgate.Validate",
        [field("request", "input", "handoff.request.v1", request_type, "Explicit task handoff request"),
         field("request", "output", "handoff.request.v1", request_type, "Validated request, preserved without editing")],
        [
            {"id": "fresh-explicit-target", "inputs": {"request": fresh}},
            {"id": "continue-without-exact-session", "inputs": {"request": invalid_continue}, "error": "handoff_request: continue requires an exact session id and cli or sdk route"},
            {"id": "manual-explicit-target", "inputs": {"request": manual}},
        ],
    )
    builder = runway(
        "handoff.packet.render",
        "Create a compact portable packet that preserves the direct instruction and keeps identity, product, client, channel, inference, adapter, and destination in separate fields.",
        ["a validated handoff request must become a portable, machine-readable packet"],
        MODULE_PATH + "/nodes/packetbuilder.Build",
        [field("request", "input", "handoff.request.v1", request_type, "Validated task handoff request"),
         field("packet", "output", "handoff.packet.v1", packet_type, "Portable packet with no dispatch claim"),
         field("packet_json", "output", "handoff.packet.json.v1", {"type": "string"}, "Compact JSON encoding of the packet"),
         field("handoff_prompt", "output", "handoff.prompt.v1", {"type": "string"}, "Copy-ready prompt preserving the typed packet")],
        [{"id": "packet-with-explicit-codex-target", "inputs": {"request": fresh}}],
    )
    hasher = runway(
        "handoff.packet.fingerprint",
        "Compute a stable lowercase SHA-256 fingerprint of compact handoff packet JSON.",
        ["packet identity is needed to compare or cite the exact prepared handoff"],
        MODULE_PATH + "/nodes/fingerprint.Fingerprint",
        [field("packet_json", "input", "handoff.packet.json.v1", {"type": "string"}, "Compact packet JSON"),
         field("sha256", "output", "handoff.packet.sha256", {"type": "string"}, "Lowercase SHA-256 of the packet JSON bytes")],
        [{"id": "fingerprint-valid-packet", "inputs": {"packet_json": "{\"schema\":\"harness.handoff_packet.v1\"}"}}],
    )
    for filename, value in (("request_gate.json", gate), ("render_packet.json", builder), ("fingerprint_packet.json", hasher)):
        write_json(RUNWAY / filename, value)

    write_json(AUTHORING / "plan.json", {
        "schema": "forge.author_plan.v1",
        "module": MODULE_PATH,
        "tool_name": "prepare_handoff",
        "nodes": [
            {"key": "request_gate", "runway_file": "runway/request_gate.json"},
            {"key": "render_packet", "runway_file": "runway/render_packet.json"},
            {"key": "fingerprint_packet", "runway_file": "runway/fingerprint_packet.json"},
        ],
        "blocks": [
            {
                "key": "intent",
                "name": "harness.handoff.intent",
                "nodes": [{"key": "validate", "node": "request_gate"}],
                "inputs": [{"name": "request", "to": {"node": "validate", "port": "request"}}],
                "outputs": [{"name": "validated_request", "from": {"node": "validate", "port": "request"}}],
            },
            {
                "key": "packet",
                "name": "harness.handoff.packet",
                "nodes": [{"key": "render", "node": "render_packet"}, {"key": "fingerprint", "node": "fingerprint_packet"}],
                "edges": [{"from": {"node": "render", "port": "packet_json"}, "to": {"node": "fingerprint", "port": "packet_json"}}],
                "inputs": [{"name": "request", "to": {"node": "render", "port": "request"}}],
                "outputs": [
                    {"name": "handoff_packet", "from": {"node": "render", "port": "packet"}},
                    {"name": "packet_json", "from": {"node": "render", "port": "packet_json"}},
                    {"name": "handoff_prompt", "from": {"node": "render", "port": "handoff_prompt"}},
                    {"name": "packet_sha256", "from": {"node": "fingerprint", "port": "sha256"}},
                ],
            },
        ],
        "process": {
            "name": "harness.handoff.prepare",
            "policy": {
                "allowed_effects": [],
                "acceptance": {
                    "schema": "praxis.process_outcome_coverage.v1",
                    "required_outcomes": [
                        {
                            "id": "explicit_request_validated",
                            "purpose": "Validate that the task and execution destination are explicit before packet construction.",
                            "owner": {"block": "intent", "node": "validate"},
                            "node_outcome": "completed",
                            "deliveries": [{"node_output": "request", "process_output": "handoff_packet"}],
                        },
                        {
                            "id": "portable_packet_prepared",
                            "purpose": "Preserve the complete task and distinct identity and destination fields in the portable packet.",
                            "owner": {"block": "packet", "node": "render"},
                            "node_outcome": "completed",
                            "deliveries": [
                                {"node_output": "packet", "process_output": "handoff_packet"},
                                {"node_output": "packet_json", "process_output": "packet_json"},
                                {"node_output": "handoff_prompt", "process_output": "handoff_prompt"},
                            ],
                        },
                        {
                            "id": "packet_fingerprint_created",
                            "purpose": "Return a digest for the exact compact JSON packet bytes.",
                            "owner": {"block": "packet", "node": "fingerprint"},
                            "node_outcome": "completed",
                            "deliveries": [{"node_output": "sha256", "process_output": "packet_sha256"}],
                        },
                    ],
                },
            },
            "blocks": [{"key": "intent", "block": "intent"}, {"key": "packet", "block": "packet"}],
            "edges": [{"from": {"block": "intent", "port": "validated_request"}, "to": {"block": "packet", "port": "request"}}],
            "inputs": [{"name": "request", "to": {"block": "intent", "port": "request"}}],
            "outputs": [
                {"name": "handoff_packet", "from": {"block": "packet", "port": "handoff_packet"}},
                {"name": "packet_json", "from": {"block": "packet", "port": "packet_json"}},
                {"name": "handoff_prompt", "from": {"block": "packet", "port": "handoff_prompt"}},
                {"name": "packet_sha256", "from": {"block": "packet", "port": "packet_sha256"}},
            ],
        },
    })


if __name__ == "__main__":
    main()
