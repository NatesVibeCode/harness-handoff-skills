#!/usr/bin/env python3
"""Fetch exact public SDK archives for source review. Never install or execute.

Top-level archives and licenses are pinned in sdk_bindings.json. Their declared
ranges are not a dependency closure. This command does not qualify a runtime.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import urllib.request
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mcp_bridge.sdk_contract import bindings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--harness', choices=sorted(bindings()), action='append')
    parser.add_argument('--timeout', type=float, default=60, help='socket wait before retaining a failed/partial download; override for slower registry access')
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    results = []
    failed = False
    for harness in args.harness or sorted(bindings()):
        binding = bindings()[harness]
        for material in [binding['material'], *binding.get('additional_material', [])]:
            target = args.out / material['archive']
            record = {'harness': harness, 'distribution': material.get('distribution', binding['distribution']),
                      'version': material.get('version', binding['version']), **material, 'captured': str(target.resolve())}
            temporary = target.with_name(target.name + '.partial')
            try:
                if not target.exists():
                    # Exclusive creation preserves failed attempts instead of overwriting them.
                    with temporary.open('xb') as output:
                        with urllib.request.urlopen(material['url'], timeout=args.timeout) as response:
                            shutil.copyfileobj(response, output)
                source = target if target.exists() else temporary
                if hashlib.sha256(source.read_bytes()).hexdigest() != material['sha256']:
                    raise ValueError('archive digest drift; material not accepted')
                if not target.exists(): temporary.rename(target)
                record['status'] = 'captured'
            except Exception as exc:
                failed = True
                record.update(status='failed', error=str(exc), partial=str(temporary.resolve()) if temporary.exists() else None)
            results.append(record)
    receipt = args.out / ('material-receipt-' + uuid.uuid4().hex + '.json')
    receipt.write_text(json.dumps({'schema': 'harness.sdk_material_capture.v1',
                                  'qualifies_runtime': False, 'archives': results}, indent=2) + '\n')
    print(json.dumps({'status': 'failed' if failed else 'captured', 'archives': len(results), 'receipt': str(receipt)}))
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
