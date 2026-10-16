#!/usr/bin/env python3
"""Capture every fresh plan's native factory diagnostics; never print or invoke."""
from __future__ import annotations
import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path, help='new diagnostics directory')
    parser.add_argument('--forge-author', default='forge-author')
    parser.add_argument('--timeout', type=float, default=60, help='seconds before recording a stalled factory check; override for slower printers')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    author = Path('praxis/handoff/sdk/authoring')
    executable = shutil.which(args.forge_author)
    if not executable: parser.error('supported forge-author is unavailable')
    args.out.mkdir(parents=True, exist_ok=False)
    findings = []
    for plan in sorted((root/author).glob('plan-*-fresh.json')):
        argv = [executable, 'plan', '-check', '-input', str(plan.relative_to(root)), '-stores', str(author/'stores.json')]
        try:
            result = subprocess.run(argv, cwd=root, capture_output=True, text=True, timeout=args.timeout)
        except subprocess.TimeoutExpired as exc:
            def decoded(value): return value.decode(errors='replace') if isinstance(value, bytes) else value or ''
            result = subprocess.CompletedProcess(argv, 124, decoded(exc.stdout), decoded(exc.stderr) + '\nFactory preflight timed out; no print attempted.\n')
        name = plan.stem.removeprefix('plan-')
        (args.out/f'{name}.stdout.json').write_text(result.stdout)
        (args.out/f'{name}.stderr.txt').write_text(result.stderr)
        document = json.loads(plan.read_text())
        paths = [plan, root/author/'stores.json']
        for node in document['nodes']:
            paths.extend(plan.parent/node[key] for key in ('spec_file', 'source_file') if key in node)
        paths.extend(plan.parent/asset['file'] for asset in document.get('assets', []))
        store = json.loads((root/author/'stores.json').read_text())
        paths.extend(root/author/contract['path'] for contract in store.get('contracts', []))
        artifact_pins = {str(path.resolve().relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
                         for path in paths}
        findings.append({'capability': name, 'artifact_pins': artifact_pins, 'plan_sha256': hashlib.sha256(plan.read_bytes()).hexdigest(),
                         'exit_code': result.returncode, 'status': 'plan_checked' if result.returncode == 0 else 'factory_refused',
                         'diagnostics': f'{name}.stdout.json', 'printed': False, 'admitted': False})
    report = {'schema': 'harness.sdk_plan_checks.v1',
              'forge_author_sha256': hashlib.sha256(Path(executable).read_bytes()).hexdigest(),
              'capabilities': findings, 'unchecked': ['standalone build', 'runtime closure', 'provider execution', 'Node admission', 'release', 'native AO consumption']}
    (args.out/'summary.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({'plans': len(findings), 'passed': sum(f['exit_code'] == 0 for f in findings), 'out': str(args.out)}))
    return 0 if all(f['exit_code'] == 0 for f in findings) else 1


if __name__ == '__main__': raise SystemExit(main())
