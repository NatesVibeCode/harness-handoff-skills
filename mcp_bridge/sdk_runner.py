"""One-shot printed Python SDK runner; never installs, retries, or falls back."""
from __future__ import annotations

import asyncio
import contextlib
import hashlib
import importlib
import importlib.metadata
import importlib.util
import json
import os
import re
import sys
from pathlib import Path

SECRET_PATTERN = re.compile(r'(?:sk-|xai-|sgamp_|crsr_|perm-)[A-Za-z0-9_-]{8,}')


def digest(raw):
    return 'sha256:' + hashlib.sha256(raw).hexdigest()


def run(request: dict) -> dict:
    if not isinstance(request, dict):
        raise ValueError('SDK request must be an object')
    base = Path(__file__).resolve().parent
    runtime_root = os.environ.get('PRAXIS_SDK_RUNTIME_ROOT')
    if not runtime_root:
        raise RuntimeError('Captured SDK runtime is required')
    runtime = Path(runtime_root).resolve(strict=True)
    selection = json.loads((runtime / 'runtime.json').read_text())
    for path in reversed(selection.get('python_path', [])):
        selected = (runtime / path).resolve(strict=True)
        if not selected.is_relative_to(runtime) or not selected.is_dir():
            raise RuntimeError('SDK dependency path leaves captured material')
        sys.path.insert(0, str(selected))
    # Verify every project runtime source before importing any of it or a vendor.
    for path, key in [(Path(__file__).resolve(), 'runner_digest'),
                      (base / 'mcp_bridge/sdk_contract.py', 'contract_digest'),
                      (base / 'mcp_bridge/sdk_operations.py', 'adapter_digest')]:
        if digest(path.read_bytes()) != request.get(key):
            raise ValueError(f'SDK {key} drift')
    def load_source(name, path):
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    contract = load_source('printed_sdk_contract', base / 'mcp_bridge/sdk_contract.py')
    binding = contract.validate_request(request, 'python')
    if sys.version_info[:2] < tuple(map(int, binding['minimum_runtime'].split('.'))):
        raise RuntimeError('Python runtime is below the SDK contract minimum')
    if importlib.metadata.version(binding['distribution']) != binding['version']:
        raise RuntimeError('Installed Python SDK version differs from the Node pin')
    for material in binding.get('additional_material', []):
        if importlib.metadata.version(material['distribution']) != material['version']:
            raise RuntimeError('Installed supplemental SDK material differs from the Node pin')
    # Import output belongs in diagnostics, never in the JSON receipt channel.
    with contextlib.redirect_stdout(sys.stderr):
        sdk = importlib.import_module(binding['module'])
        if not hasattr(sdk, binding['entrypoint']):
            raise RuntimeError('Pinned SDK entrypoint is unavailable')
        operations = load_source('printed_sdk_operations', base / 'mcp_bridge/sdk_operations.py')
        result = asyncio.run(operations.invoke(request))
    return {
        'schema': 'praxis.harness_sdk_receipt.v1', 'status': 'succeeded',
        'harness': request['harness'], 'sdk_operation': request['operation'],
        'distribution': binding['distribution'], 'distribution_version': binding['version'],
        'module': binding['module'], 'entrypoint': binding['entrypoint'],
        'adapter': request['adapter'], 'adapter_digest': request['adapter_digest'],
        'runner_digest': request['runner_digest'], 'contract_digest': request['contract_digest'],
        'bindings_digest': request['bindings_digest'],
        'settings_digest': digest(json.dumps(request['settings'], sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()),
        'session_id': result['session_id'],
        'output': result['output'],
    }


def main() -> int:
    try:
        receipt = run(json.load(sys.stdin))
        sys.stdout.write(json.dumps(receipt, ensure_ascii=False, separators=(',', ':')) + '\n')
        return 0
    except Exception as exc:
        # Keep complete failure details; the owning Process retains stderr and
        # decides recovery. An interrupted invocation never resubmits here.
        message = SECRET_PATTERN.sub('[redacted-credential]', str(exc))
        sys.stderr.write(f'SDK invocation refused: {message}\n')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
