"""Harness SDK bridge: optional operator MCP tooling for harness-handoff.

This package is not part of the generated skills and is not a lane manager:
each tool call creates one caller-owned execution in exactly one harness and
returns its receipt. Session, credential, approval, and product boundaries come
from skills-src/contracts.json, which remains the single source of truth.
"""
