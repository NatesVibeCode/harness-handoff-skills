#!/usr/bin/env python3
"""Publish exact SDK Node declarations through Forge; publication grants no admission."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True, type=Path, help='selected Atlas data root')
    parser.add_argument('--evidence', required=True, type=Path, help='new publication evidence directory')
    parser.add_argument('--forge-author', default='forge-author')
    args = parser.parse_args()
    executable = shutil.which(args.forge_author)
    if executable is None:
        parser.error('forge-author is unavailable')
    project = Path(__file__).resolve().parents[1]
    sdk = project / 'praxis/handoff/sdk'
    index = json.loads((sdk / 'capabilities.json').read_text())
    args.evidence.mkdir(parents=True, exist_ok=False)
    rows = []
    for capability in index['capabilities']:
        slug = capability['capability']
        spec = sdk / capability['node_spec']
        stores = sdk / f'authoring/stores-{slug}.json'
        author_request = args.evidence / f'{slug}.node.request.json'
        author_request.write_text(json.dumps({
            'schema': 'forge.author_node_request.v1', 'spec': json.loads(spec.read_text()),
            'pins': {'source': str(sdk / 'authoring/assets/sdk_dispatch.go'),
                     'test': str(sdk / 'authoring/assets/proof_test.go')},
        }, indent=2) + '\n')
        checked = subprocess.run([executable, 'node', '-input', str(author_request),
                                  '-stores', str(stores)], capture_output=True, text=True)
        (args.evidence / f'{slug}.node.stdout.json').write_text(checked.stdout)
        (args.evidence / f'{slug}.node.stderr.txt').write_text(checked.stderr)
        if checked.returncode != 0 or json.loads(checked.stdout).get('node', {}).get('digest') != capability['node']['digest']:
            raise RuntimeError(f'{slug}: authoring refused or exact Node revision changed; no publication attempted')
        request = {
            'schema': 'forge.catalog_request.v1', 'node_file': str(spec),
            'source': {'kind': 'forge-node', 'ref': str(spec), 'license': 'MIT',
                       'digest': hashlib.sha256(spec.read_bytes()).hexdigest()},
        }
        request_file = args.evidence / f'{slug}.request.json'
        request_file.write_text(json.dumps(request, indent=2) + '\n')
        argv = [executable, 'catalog', '-input', str(request_file), '-root', str(args.root.resolve()),
                '-stores', str(stores)]
        result = subprocess.run(argv, capture_output=True, text=True)
        (args.evidence / f'{slug}.stdout.json').write_text(result.stdout)
        (args.evidence / f'{slug}.stderr.txt').write_text(result.stderr)
        document = json.loads(result.stdout)
        if result.returncode != 0 or document.get('catalog', {}).get('digest') != capability['node']['digest']:
            raise RuntimeError(f'{slug}: publication refused or exact Node revision changed; inspect retained evidence')
        rows.append({'capability': slug, **document['catalog']})
    (args.evidence / 'summary.json').write_text(json.dumps({
        'schema': 'harness.sdk_catalog_publication.v1', 'nodes': rows,
        'forge_author_sha256': hashlib.sha256(Path(executable).read_bytes()).hexdigest(),
    }, indent=2) + '\n')
    print(json.dumps({'published': len(rows), 'root': str(args.root.resolve()), 'admitted': False}))


if __name__ == '__main__':
    main()
