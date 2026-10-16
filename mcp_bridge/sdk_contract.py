"""Project-owned declarations and validation for printed fresh SDK Nodes."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

BINDINGS_PATH = Path(__file__).with_name('sdk_bindings.json')


def digest(raw: bytes) -> str:
    return 'sha256:' + hashlib.sha256(raw).hexdigest()


def bindings() -> dict:
    return json.loads(BINDINGS_PATH.read_text(encoding='utf-8'))['bindings']


def validate(value, schema: dict, path: str = 'settings', *, nonempty_strings=False) -> None:
    """Validate the closed JSON-schema subset emitted by this project's author."""
    kind = schema['type']
    valid = {'object': isinstance(value, dict), 'array': isinstance(value, list),
             'string': isinstance(value, str), 'boolean': isinstance(value, bool)}[kind]
    if not valid:
        raise ValueError(f'{path} must be {kind}')
    if 'enum' in schema and value not in schema['enum']:
        raise ValueError(f'{path} is not a declared selection')
    if kind == 'string' and nonempty_strings and not value.strip():
        raise ValueError(f'{path} must be nonempty')
    if kind == 'object':
        for key in schema.get('required', []):
            if key not in value:
                raise ValueError(f'{path}.{key} is required')
        for key, item in value.items():
            child = schema.get('properties', {}).get(key, schema.get('additionalProperties', False))
            if child is False:
                raise ValueError(f'{path}.{key} is not declared')
            validate(item, child, f'{path}.{key}', nonempty_strings=nonempty_strings)
    if kind == 'array':
        for index, item in enumerate(value):
            validate(item, schema['items'], f'{path}[{index}]', nonempty_strings=nonempty_strings)


def validate_request(request: dict, language: str) -> dict:
    if not isinstance(request, dict):
        raise ValueError('SDK request must be an object')
    allowed = {'harness', 'operation', 'distribution', 'version', 'module', 'entrypoint',
               'adapter', 'adapter_digest', 'runner_digest', 'contract_digest', 'bindings_digest',
               'prompt', 'workspace', 'settings'}
    unknown = set(request) - allowed
    if unknown:
        raise ValueError('undeclared SDK request field: ' + sorted(unknown)[0])
    binding = bindings().get(request.get('harness'))
    if not binding or binding['language'] != language:
        raise ValueError('unsupported SDK binding')
    if request.get('operation') not in binding['operations']:
        raise ValueError('SDK Node supports fresh operations only')
    for key in ('distribution', 'module', 'entrypoint'):
        if request.get(key) != binding[key]:
            raise ValueError(f'SDK {key} differs from the declaration')
    if request.get('version') != binding['version']:
        raise ValueError('SDK version differs from the declaration')
    expected_adapter = f"{request['harness']}{'_ts' if language == 'typescript' else ''}_fresh"
    if request.get('adapter') != expected_adapter:
        raise ValueError('SDK adapter differs from the declaration')
    if request.get('bindings_digest') != digest(BINDINGS_PATH.read_bytes()):
        raise ValueError('SDK declaration digest drift')
    for key in ('prompt', 'workspace'):
        if not isinstance(request.get(key), str) or not request[key].strip():
            raise ValueError(f'{key} must be nonempty')
    if not Path(request['workspace']).is_absolute() or not Path(request['workspace']).is_dir():
        raise ValueError('workspace must be an existing absolute directory')
    # Old flat settings must not silently override the typed settings object.
    for key in ('model', 'approval', 'provider_id', 'session_id', 'session_owner'):
        if key in request:
            raise ValueError(f'{key} is not a fresh SDK request field')
    validate(request.get('settings'), binding['settings'], nonempty_strings=binding['settings_nonempty_strings'])
    return binding
