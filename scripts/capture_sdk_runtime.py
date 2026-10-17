"""Capture selected installed material into a deterministic, relocatable bundle.

This build-time command never installs dependencies or reads account state. Its
input selects source directories/files and the runtime entrypoint explicitly.
The printed Process carries the resulting archive; it needs no source checkout.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import tarfile


def safe_path(value):
    path = PurePosixPath(value)
    if not value or str(path) != value or path.is_absolute() or '..' in path.parts or '\\' in value:
        raise ValueError('material destination must be a clean relative path')
    return value


def capture(selection, output):
    files = {}
    for selected in selection['sources']:
        source = Path(selected['source']).resolve(strict=True)
        destination = safe_path(selected['destination'])
        candidates = sorted(source.rglob('*')) if source.is_dir() else [source]
        for candidate in candidates:
            if candidate.is_symlink() and candidate.is_dir():
                raise ValueError(f'select a resolved directory explicitly: {candidate}')
            if candidate.is_dir() or '__pycache__' in candidate.parts or candidate.suffix == '.pyc':
                continue
            # Dereference only explicitly selected source trees. Symlinked files
            # must remain inside that selection; executable modes are captured.
            resolved = candidate.resolve(strict=True)
            if source.is_dir() and not resolved.is_relative_to(source):
                raise ValueError(f'material link leaves selected tree: {candidate}')
            if not resolved.is_file():
                raise ValueError(f'material is not a regular file: {candidate}')
            relative = candidate.relative_to(source).as_posix() if source.is_dir() else ''
            name = safe_path(destination + ('/' + relative if relative else ''))
            if name in files:
                raise ValueError(f'duplicate runtime material: {name}')
            if name in {'runtime.json', 'manifest.json'}:
                raise ValueError('reserved runtime metadata destination')
            files[name] = (resolved, 0o555 if resolved.stat().st_mode & 0o111 else 0o444)
    manifest = {'schema': 'harness.sdk_runtime_manifest.v1', 'target': selection['target'],
                'runtime': selection['runtime'], 'configuration': selection['configuration'],
                'provenance': selection['provenance'], 'files': {}}
    for name, (source, mode) in sorted(files.items()):
        manifest['files'][name] = {'sha256': hashlib.sha256(source.read_bytes()).hexdigest(), 'mode': mode}
    runtime = selection['runtime']
    if runtime['binary'] not in files:
        raise ValueError('selected runtime executable is absent')
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    temporary = output / 'capturing.tar.gz'
    with temporary.open('wb') as raw, gzip.GzipFile(fileobj=raw, mode='wb', filename='', mtime=0) as compressed, tarfile.open(fileobj=compressed, mode='w') as archive:
        for name, (source, mode) in sorted(files.items()):
            header = tarfile.TarInfo(name); header.size = source.stat().st_size; header.mode = mode
            with source.open('rb') as content:
                class ObservedReader:
                    def __init__(self): self.hash = hashlib.sha256()
                    def read(self, size):
                        data = content.read(size); self.hash.update(data); return data
                observed = ObservedReader()
                archive.addfile(header, observed)
                if observed.hash.hexdigest() != manifest['files'][name]['sha256']:
                    raise ValueError(f'material changed during capture: {name}')
        for name, value in [('runtime.json', selection['configuration']), ('manifest.json', manifest)]:
            data = (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()
            header = tarfile.TarInfo(name); header.size = len(data); header.mode = 0o444
            archive.addfile(header, io.BytesIO(data))
    digest = hashlib.sha256(temporary.read_bytes()).hexdigest()
    target = output / (digest + '.tar.gz')
    os.replace(temporary, target)
    (output / (digest + '.manifest.json')).write_text(json.dumps(manifest, indent=2) + '\n')
    result = {**runtime, 'sha256': manifest['files'][runtime['binary']]['sha256'],
              'target': selection['target'], 'bundle_digest': digest, 'bundle_file': target.name}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(capture(json.loads(args.input.read_text()), args.out), indent=2))


if __name__ == '__main__':
    main()
