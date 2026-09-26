#!/usr/bin/env python3
"""Report which contracted harness binaries are installed and their versions.

Read-only and credential-free: it resolves each harness's `binary` with
`shutil.which` and runs `<binary> --version` with a short timeout. Missing
binaries are reported, not fatal, because skill authors routinely work on
machines that do not have every harness installed. This never launches model
work, opens sessions, or touches credentials.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parent.parent)
    args = parser.parse_args()

    document = json.loads((args.repo / "skills-src" / "contracts.json").read_text(encoding="utf-8"))
    harnesses = document["harnesses"]
    print(f"{'harness':<12}{'binary':<16}{'status':<10}version")
    for name in sorted(harnesses):
        binary = harnesses[name]["binary"]
        path = shutil.which(binary)
        if path is None:
            print(f"{name:<12}{binary:<16}{'missing':<10}-")
            continue
        try:
            completed = subprocess.run(
                [binary, "--version"], capture_output=True, text=True, timeout=30
            )
        except (OSError, subprocess.SubprocessError) as exc:
            print(f"{name:<12}{binary:<16}{'error':<10}{exc}")
            continue
        output = (completed.stdout or completed.stderr).strip().splitlines()
        version = output[0] if output else f"exit={completed.returncode}"
        print(f"{name:<12}{binary:<16}{'present':<10}{version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
