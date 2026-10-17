#!/usr/bin/env python3
"""Build exact SDK capabilities through Forge's plan door and retain diagnostics."""
from __future__ import annotations
import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path, help='new build/evidence directory')
    parser.add_argument('--forge-author', default='forge-author')
    parser.add_argument('--develop', action='store_true', help='also compile unsigned development packages')
    args = parser.parse_args()
    executable = shutil.which(args.forge_author)
    if executable is None:
        parser.error('installed forge-author is unavailable')
    project = Path(__file__).resolve().parents[1]
    sdk = project/'praxis/handoff/sdk'
    author = sdk/'authoring'
    args.out = args.out.resolve()
    args.out.mkdir(parents=True, exist_ok=False)
    rows = []
    for plan in sorted(author.glob('plan-*-fresh.json')):
        slug = plan.stem.removeprefix('plan-')
        command = [executable, 'plan', '-input', str(plan), '-stores', str(author/f'stores-{slug}.json'), '-out', str(args.out/slug)]
        if args.develop:
            command.append('-develop')
        result = subprocess.run(command, cwd=project, capture_output=True, text=True)
        (args.out/f'{slug}.stdout.json').write_text(result.stdout)
        (args.out/f'{slug}.stderr.txt').write_text(result.stderr)
        if result.returncode:
            raise RuntimeError(f'{slug}: factory refused; inspect {args.out}')
        report = json.loads(result.stdout)['plan']
        node = json.loads(plan.read_text())['nodes'][0]
        rows.append({'capability': slug, 'node': report['node_pins']['invoke'],
                     'node_spec': f"authoring/{node['spec_file']}", 'block': report['block_pins']['operation'],
                     'block_file': f'blocks/{slug}.json', 'process': report['process_pin'], 'plan': f'authoring/{plan.name}'})
        print(json.dumps({'capability': slug, 'built': True, 'development': args.develop, 'admitted': False}), flush=True)
    # Publish the index only when every native authoring operation succeeded.
    for row in rows:
        shutil.copyfile(args.out/row['capability']/'blocks/operation.json', sdk/row['block_file'])
    index = {'schema': 'harness.sdk_capabilities.v1', 'readiness': {
        'native_plan_checked': True, 'development_package_built': args.develop,
        'real_use_qualified': False, 'admitted': False, 'release_printed': False}, 'capabilities': rows}
    (sdk/'capabilities.json').write_text(json.dumps(index, indent=2)+'\n')
    (args.out/'summary.json').write_text(json.dumps({**index, 'forge_author_sha256': hashlib.sha256(Path(executable).read_bytes()).hexdigest()}, indent=2)+'\n')


if __name__ == '__main__':
    main()
