"""Local mechanics only. These fixtures are never Node admission evidence."""
import asyncio
import copy
import hashlib
import json
import subprocess
import sys
import types
from pathlib import Path

import pytest

from mcp_bridge import sdk_contract, sdk_operations

ROOT = Path(__file__).resolve().parents[1]
BINDINGS = sdk_contract.bindings()


def sample(schema):
    if 'enum' in schema:
        return copy.deepcopy(schema['enum'][0]) if schema['enum'] else None
    if schema['type'] == 'object':
        return {key: sample(schema['properties'].get(key, schema['additionalProperties'])) for key in schema.get('required', [])}
    return {'string': 'selected', 'boolean': False, 'array': []}[schema['type']]


def request(harness, workspace):
    binding = BINDINGS[harness]
    return {**{key: binding[key] for key in ['distribution', 'version', 'module', 'entrypoint']},
            'harness': harness, 'operation': 'fresh',
            'adapter': harness + ('_ts' if binding['language'] == 'typescript' else '') + '_fresh',
            'bindings_digest': sdk_contract.digest(sdk_contract.BINDINGS_PATH.read_bytes()),
            'prompt': 'same prompt', 'workspace': str(workspace), 'settings': sample(binding['settings'])}


@pytest.mark.parametrize('harness', BINDINGS)
def test_all_declared_bindings_accept_explicit_settings(harness, tmp_path):
    req = request(harness, tmp_path)
    assert sdk_contract.validate_request(req, BINDINGS[harness]['language']) == BINDINGS[harness]


@pytest.mark.parametrize('harness', BINDINGS)
@pytest.mark.parametrize('change', ['missing', 'unknown', 'wrong_type', 'resume', 'flat', 'drift'])
def test_refuse_before_execution(harness, change, tmp_path):
    req = request(harness, tmp_path)
    if change == 'missing': req['settings'].pop(next(iter(req['settings'])))
    if change == 'unknown': req['settings']['invented'] = True
    if change == 'wrong_type': req['settings'] = []
    if change == 'resume': req['operation'] = 'resume'
    if change == 'flat': req['approval'] = 'unattended'
    if change == 'drift': req['version'] = '0.0.0'
    with pytest.raises(ValueError): sdk_contract.validate_request(req, BINDINGS[harness]['language'])


@pytest.mark.parametrize('session,output', [(None, 'ok'), ('', 'ok'), ('id', ''), ('id', None), ('id', object())])
def test_no_placeholder_success(session, output):
    with pytest.raises(RuntimeError): sdk_operations.completed(session, output)


def test_claude_forwards_settings_and_rejects_failed_terminal(monkeypatch, tmp_path):
    seen, drained = [], []
    class Options:
        def __init__(self, **kwargs): seen.append(kwargs)
    class Result:
        def __init__(self, error=False):
            self.is_error, self.session_id, self.result = error, 'fresh-id', 'answer'
            self.subtype, self.errors = 'error_during_execution' if error else 'success', ['provider refused'] if error else []
    error = False
    async def query(**kwargs):
        yield Result(error)
        drained.append(True)
    monkeypatch.setitem(sys.modules, 'claude_agent_sdk', types.SimpleNamespace(ClaudeAgentOptions=Options, ResultMessage=Result, query=query))
    req = request('claude', tmp_path)
    assert asyncio.run(sdk_operations.claude(req))['output'] == 'answer'
    req['settings']['model'] = 'other-model'
    asyncio.run(sdk_operations.claude(req))
    assert seen[0]['model'] == 'selected'
    assert seen[1] == {**seen[0], 'model': 'other-model'}
    req['settings']['permission_mode'] = 'acceptEdits'
    asyncio.run(sdk_operations.claude(req))
    assert seen[2] == {**seen[1], 'permission_mode': 'acceptEdits'}
    error = True
    with pytest.raises(RuntimeError, match='error result') as failure:
        asyncio.run(sdk_operations.claude(req))
    assert 'provider refused' in str(failure.value) and 'fresh-id' in str(failure.value)
    assert len(drained) == 4


def test_cursor_requires_successful_terminal_and_never_stringifies_objects(monkeypatch, tmp_path):
    seen = []
    terminal = types.SimpleNamespace(status='finished', result='answer')
    class Agent:
        agent_id = 'fresh-id'
        @staticmethod
        def create(**kwargs): seen.append(kwargs); return Agent()
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def send(self, prompt): return types.SimpleNamespace(wait=lambda: terminal)
    monkeypatch.setitem(sys.modules, 'cursor_sdk', types.SimpleNamespace(Agent=Agent, LocalAgentOptions=lambda **kwargs: kwargs))
    req = request('cursor', tmp_path)
    assert asyncio.run(sdk_operations.cursor(req))['output'] == 'answer'
    assert seen[0]['local']['sandbox_options'] == {'enabled': False}
    terminal.status = 'cancelled'
    with pytest.raises(RuntimeError, match='did not finish'): asyncio.run(sdk_operations.cursor(req))


def test_copilot_uses_workspace_and_completed_message(monkeypatch, tmp_path):
    seen = []
    response = types.SimpleNamespace(data=types.SimpleNamespace(content='actual assistant output'))
    class Session:
        session_id = 'fresh-id'
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def send_and_wait(self, prompt): return response
    class Client:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def create_session(self, **kwargs): seen.append(kwargs); return Session()
    no = type('PermissionNoResult', (), {})
    monkeypatch.setitem(sys.modules, 'copilot', types.SimpleNamespace(CopilotClient=Client))
    monkeypatch.setitem(sys.modules, 'copilot.session', types.SimpleNamespace(PermissionHandler=types.SimpleNamespace(approve_all=lambda *_: True), PermissionNoResult=no))
    req = request('copilot', tmp_path)
    assert asyncio.run(sdk_operations.copilot(req))['output'] == 'actual assistant output'
    assert seen[0]['working_directory'] == str(tmp_path)
    assert isinstance(seen[0]['on_permission_request'](), no)
    monkeypatch.setenv('OPENROUTER_API_KEY', 'local-fixture')
    req['settings']['provider'] = {'type': 'openai', 'base_url': 'https://provider.invalid/v1',
                                 'api_key_env': 'OPENROUTER_API_KEY', 'wire_api': 'completions'}
    asyncio.run(sdk_operations.copilot(req))
    assert seen[-1]['provider'] == {'type': 'openai', 'base_url': 'https://provider.invalid/v1',
                                    'api_key': 'local-fixture', 'wire_api': 'completions'}
    response.data.content = None
    with pytest.raises(RuntimeError, match='assistant output'): asyncio.run(sdk_operations.copilot(req))


def test_fresh_plans_use_one_declaration_and_map_settings_through_both_layers():
    sys.path.insert(0, str(ROOT/'praxis/handoff/sdk/authoring'))
    import build_sdk_plans as author
    for harness, binding in BINDINGS.items():
        fields = author.operation_fields(harness, 'fresh', binding['language'])
        assert next(f for f in fields if f['name'] == 'settings')['type'] == binding['settings']
        slug = harness + ('-typescript' if binding['language'] == 'typescript' else '') + '-fresh'
        plan = json.loads((author.HERE/f'plan-{slug}.json').read_text())
        assert {'name': 'settings', 'to': {'node': 'invoke', 'port': 'settings'}} in plan['blocks'][0]['inputs']
        assert {'name': 'settings', 'to': {'block': 'operation', 'port': 'settings'}} in plan['process']['inputs']
        spec = json.loads((author.HERE/plan['nodes'][0]['spec_file']).read_text())
        sdk = next(d['contents']['sdk'] for d in spec['dimensions'] if d['name'] == 'handoff')
        assert sdk['bindings_digest'] == sdk_contract.digest(sdk_contract.BINDINGS_PATH.read_bytes())
        assert not spec['proof_spec']['behavior']  # These checks do not invent real-use evidence.


def test_typescript_mechanics():
    subprocess.run(['node', '--test', 'tests/sdk_nodes.test.mjs'], cwd=ROOT, check=True, timeout=60)


def test_sdk_catalogue_pins_local_dispatch_check_without_claiming_vendor_proof():
    root = ROOT / 'praxis/handoff/sdk/authoring'
    test = (root / 'assets/proof_test.go').read_bytes()
    expected = hashlib.sha256(b'praxis.test.go.v1\x00' + test).hexdigest()
    for path in root.glob('plan-*-fresh.json'):
        plan = json.loads(path.read_text())
        spec = json.loads((root / plan['nodes'][0]['spec_file']).read_text())
        stores = json.loads((root / ('stores-' + path.stem.removeprefix('plan-') + '.json')).read_text())
        assert spec['proof_spec']['test'] == {
            'pointer': 'sdkdispatch.TestSDKDispatchRequiresPrintedRuntime', 'digest': expected}
        assert stores['pointers'] == [{
            'kind': 'test', 'pointer': spec['proof_spec']['test']['pointer'],
            'digest': expected, 'path': 'assets/proof_test.go'}]
        assert not spec['proof_spec']['behavior']
        access = next(d['contents'] for d in spec['dimensions'] if d['name'] == 'access')
        assert access['share']['identity'].startswith('sdk-execution-owner:')
    query = json.loads((root / 'atlas-reuse-query.json').read_text())
    assert query['inputs'] == query['outputs'] == []
    assert all('audit' not in term and 'resume' not in term for term in query['purpose_terms'])


def test_muse_selected_profile_is_required_and_completed_text_only(monkeypatch, tmp_path):
    seen, closed = [], []
    class Turn:
        @property
        def completed(self):
            async def done(): return types.SimpleNamespace(kind='completed', params={'terminal': 'completed'})
            return done()
        async def items(self):
            yield {'kind': 'toolCall', 'status': 'completed', 'text': 'not assistant output'}
            yield {'item': {'kind': 'agentMessage', 'status': 'completed', 'text': 'answer'}}
    class Session:
        session_id = 'fresh-id'
        async def send_user_turn(self, options): return Turn()
    class Client:
        @staticmethod
        async def spawn(options): return Client()
        async def start_session(self, options): seen.append(options); return Session()
        async def close(self): closed.append(True)
    monkeypatch.setitem(sys.modules, 'muse_code', types.SimpleNamespace(
        MuseClient=Client, MuseClientSpawnOptions=lambda **kw: kw,
        SendUserTurnOptions=lambda **kw: kw, StartSessionOptions=lambda **kw: kw))
    req = request('muse', tmp_path)
    assert asyncio.run(sdk_operations.muse(req))['output'] == 'answer'
    assert seen == [{**req['settings'], 'workspace_root': str(tmp_path), 'require_permission_profile': True}]
    assert closed == [True]


def test_antigravity_binds_workspace_model_recovery_dirs_and_permission(monkeypatch, tmp_path):
    seen = []
    class Agent:
        conversation_id = 'fresh-id'
        def __init__(self, config): seen.append(config)
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def chat(self, prompt):
            async def text(): return 'answer'
            return types.SimpleNamespace(text=text, stop_reason="UNSPECIFIED")
    monkeypatch.setitem(sys.modules, 'google.antigravity', types.SimpleNamespace(
        Agent=Agent, LocalAgentConfig=lambda **kw: kw,
        policy=types.SimpleNamespace(confirm_run_command=lambda: ['native'], allow_all=lambda: 'allow-all')))
    req = request('antigravity', tmp_path)
    asyncio.run(sdk_operations.antigravity(req))
    assert seen[0] == {'model': 'selected', 'workspaces': [str(tmp_path)], 'policies': ['native'], 'save_dir': 'selected', 'app_data_dir': 'selected'}
    req['settings']['permission'] = 'unattended'
    asyncio.run(sdk_operations.antigravity(req))
    assert seen[1]['policies'] == ['allow-all']


def test_openhands_returns_completed_agent_text_and_closes_on_failure(monkeypatch, tmp_path):
    seen, closed = [], []
    class MessageEvent:
        source = 'agent'
        llm_message = types.SimpleNamespace(content=[types.SimpleNamespace(text='answer')])
    state = types.SimpleNamespace(execution_status='finished', events=[MessageEvent()])
    class Conversation:
        id = 'fresh-id'
        def __init__(self, **kw): self.state = state; seen.append(kw)
        def send_message(self, prompt): pass
        def run(self): pass
        def close(self): closed.append(True)
    monkeypatch.setenv('LLM_API_KEY', 'local-fixture')
    monkeypatch.setitem(sys.modules, 'openhands.sdk', types.SimpleNamespace(
        LLM=lambda **kw: kw, Agent=lambda **kw: kw, Conversation=Conversation))
    monkeypatch.setitem(sys.modules, 'openhands.sdk.event', types.SimpleNamespace(MessageEvent=MessageEvent))
    req = request('openhands', tmp_path)
    assert asyncio.run(sdk_operations.openhands(req))['output'] == 'answer'
    assert seen[0] == {'agent': {'llm': {'model': 'selected', 'api_key': 'local-fixture'}, 'tools': []}, 'workspace': str(tmp_path)}
    state.execution_status = 'stuck'
    with pytest.raises(RuntimeError, match='did not finish'): asyncio.run(sdk_operations.openhands(req))
    assert len(closed) == 2


def test_declaration_is_consistent_with_skill_contracts_and_material_pins():
    contracts = json.loads((ROOT/'skills-src/contracts.json').read_text())['harnesses']
    for harness, binding in BINDINGS.items():
        contract = contracts[harness]
        assert contract['sdk']['packages'][binding['language']] == binding['distribution']
        assert contract['sdk']['entrypoints'][binding['language']] == binding['entrypoint']
        assert len(binding['material']['sha256']) == 64
        assert binding['material']['closure_qualified'] is False


def test_python_printed_runner_checks_sources_before_import_and_keeps_stdout_json(tmp_path):
    import os
    import shutil
    stage = tmp_path/'stage'; (stage/'mcp_bridge').mkdir(parents=True)
    for source, destination in [('sdk_runner.py', stage/'run.py'), ('sdk_contract.py', stage/'mcp_bridge/sdk_contract.py'),
                                ('sdk_operations.py', stage/'mcp_bridge/sdk_operations.py'), ('sdk_bindings.json', stage/'mcp_bridge/sdk_bindings.json')]:
        shutil.copyfile(ROOT/'mcp_bridge'/source, destination)
    runtime = tmp_path/'runtime'; runtime.mkdir()
    packages = runtime/'packages'; packages.mkdir()
    (runtime/'runtime.json').write_text(json.dumps({'python_path': ['packages'], 'native': {}}))
    package = packages/'claude_agent_sdk.py'
    marker = tmp_path/'imported'
    package.write_text(f'''from pathlib import Path
Path({str(marker)!r}).write_text('imported')
print('vendor diagnostic')
class ClaudeAgentOptions:
 def __init__(self, **kwargs): pass
class ResultMessage:
 is_error = False
 session_id = 'fixture-session'
 result = 'fixture completed output'
async def query(**kwargs):
 yield ResultMessage()
''')
    metadata = packages/'claude_agent_sdk-0.2.166.dist-info'; metadata.mkdir()
    (metadata/'METADATA').write_text('Metadata-Version: 2.1\nName: claude-agent-sdk\nVersion: 0.2.166\n')
    req = request('claude', tmp_path)
    for key, path in [('runner_digest', stage/'run.py'), ('contract_digest', stage/'mcp_bridge/sdk_contract.py'), ('adapter_digest', stage/'mcp_bridge/sdk_operations.py')]:
        req[key] = sdk_contract.digest(path.read_bytes())
    env = {**os.environ, 'PRAXIS_SDK_RUNTIME_ROOT': str(runtime)}
    def run(payload):
        return subprocess.run([sys.executable, '-I', str(stage/'run.py')], input=json.dumps(payload), text=True, capture_output=True, env=env, cwd=tmp_path, timeout=15)
    changed = copy.deepcopy(req); changed['settings']['invented'] = True
    refused = run(changed)
    assert refused.returncode == 1 and not marker.exists() and not refused.stdout
    result = run(req)
    assert result.returncode == 0, result.stderr
    assert 'vendor diagnostic' in result.stderr
    receipt = json.loads(result.stdout)
    assert receipt['output'] == 'fixture completed output'
    assert receipt['settings_digest'] == sdk_contract.digest(json.dumps(req['settings'], sort_keys=True, separators=(',', ':')).encode())
    marker.unlink()
    (stage/'mcp_bridge/sdk_operations.py').write_text('# drift\n')
    refused = run(req)
    assert refused.returncode == 1 and not marker.exists() and not refused.stdout


def test_typescript_printed_runner_self_pin_and_stdout_channel(tmp_path):
    import os
    import shutil
    stage = tmp_path/'stage'; stage.mkdir()
    for source, dest in [('sdk_ts_runner.mjs', 'run.mjs'), ('sdk_ts_adapters.mjs', 'adapters.mjs'), ('sdk_contract.mjs', 'contract.mjs'), ('sdk_bindings.json', 'sdk_bindings.json')]:
        shutil.copyfile(ROOT/'mcp_bridge'/source, stage/dest)
    runtime = tmp_path/'runtime'; runtime.mkdir()
    package = runtime/'node_modules/@openai/codex-sdk'; package.mkdir(parents=True)
    binding = BINDINGS['codex']
    (package/'package.json').write_text(json.dumps({'name': binding['distribution'], 'version': binding['version'], 'type': 'module', 'exports': {'.': {'import': './index.mjs'}}}))
    marker = tmp_path/'imported'
    (package/'index.mjs').write_text(f'''import {{ writeFileSync }} from 'node:fs';
writeFileSync({json.dumps(str(marker))}, 'imported');
console.log('vendor diagnostic');
export class Codex {{ startThread() {{ return {{ id: 'fixture-session', run: async () => ({{ finalResponse: 'fixture completed output' }}) }}; }} }}
''')
    req = request('codex', tmp_path)
    for key, name in [('runner_digest', 'run.mjs'), ('contract_digest', 'contract.mjs'), ('adapter_digest', 'adapters.mjs')]:
        req[key] = sdk_contract.digest((stage/name).read_bytes())
    def run(payload):
        return subprocess.run(['node', str(stage/'run.mjs'), str(stage/'adapters.mjs')], input=json.dumps(payload), text=True, capture_output=True, env={**os.environ, 'PRAXIS_SDK_RUNTIME_ROOT': str(runtime)}, cwd=tmp_path, timeout=15)
    changed = copy.deepcopy(req); changed['settings']['invented'] = True
    refused = run(changed)
    assert refused.returncode != 0 and not marker.exists() and not refused.stdout
    result = run(req)
    assert result.returncode == 0, result.stderr
    assert 'vendor diagnostic' in result.stderr
    assert json.loads(result.stdout)['output'] == 'fixture completed output'
    marker.unlink()
    changed = copy.deepcopy(req); changed['runner_digest'] = 'sha256:' + '0'*64
    refused = run(changed)
    assert refused.returncode != 0 and not marker.exists() and not refused.stdout


@pytest.mark.parametrize('kind,terminal', [('completed', 'failed'), ('completed', 'cancelled'), ('terminalUnknown', None), ('unqueued', None)])
def test_muse_resolved_awaitable_is_not_necessarily_success(kind, terminal):
    from mcp_bridge.sdk_executors import _muse_completed_text
    class Turn:
        @property
        def completed(self):
            async def done(): return types.SimpleNamespace(kind=kind, params={'terminal': terminal})
            return done()
        async def items(self): yield {'kind': 'agentMessage', 'status': 'completed', 'text': 'partial answer'}
    with pytest.raises(RuntimeError, match='did not complete'): asyncio.run(_muse_completed_text(Turn()))


@pytest.mark.parametrize('harness', BINDINGS)
def test_nonempty_settings_remain_enforced_outside_forge_type_vocabulary(harness, tmp_path):
    req = request(harness, tmp_path)
    def string_path(schema):
        if schema['type'] == 'string' and 'enum' not in schema:
            return []
        for key, child in schema.get('properties', {}).items():
            path = string_path(child)
            if path is not None:
                return [key, *path]
        return None
    path = string_path(BINDINGS[harness]['settings'])
    selected = req['settings']
    for key in path[:-1]: selected = selected[key]
    selected[path[-1]] = '   '
    with pytest.raises(ValueError, match='nonempty'):
        sdk_contract.validate_request(req, BINDINGS[harness]['language'])


@pytest.mark.parametrize('harness', BINDINGS)
def test_supported_forge_entrypoint_accepts_each_typed_need(harness, tmp_path):
    import shutil
    executable = shutil.which('forge-author')
    if not executable:
        pytest.skip('installed forge-author required for native type-vocabulary regression')
    binding = BINDINGS[harness]
    slug = harness + ('-typescript' if binding['language'] == 'typescript' else '') + '-fresh'
    author = ROOT/'praxis/handoff/sdk/authoring'
    spec = json.loads((author/'nodes'/slug/'spec.json').read_text())
    store = json.loads((author/f'stores-{slug}.json').read_text())
    assert [c['name'] for c in store['contracts']] == [harness]
    plan = json.loads((author/f'plan-{slug}.json').read_text())
    contract_asset = next(asset for asset in plan['assets'] if asset['rel_path'].endswith('/harness.json'))
    assert list(json.loads((author/contract_asset['file']).read_text())['contracts']) == [harness]
    def ports(side):
        return [{'name': f['name'], 'type': f['type'], 'semantic': spec['composition'][side+'s'][f['name']]['semantic'], 'required': f['required']}
                for f in spec['fields'] if f['side'] == side]
    blank = {'schema': 'atlas.legal_blank.v1', 'id': 'sdk.types.'+harness,
             'need': {'purpose': 'Check the authored SDK type vocabulary without claiming execution support',
                      'inputs': ports('input'), 'outputs': ports('output'), 'allowed_effects': ['harness.invoke']},
             'class': 'missing_implementation', 'probe': {'owner': 'project authoring', 'action': 'Native type validation only'},
             'expiry': {'scope_digest': '0'*64, 'evidence': []}}
    path = tmp_path/'need.json'; path.write_text(json.dumps(blank))
    result = subprocess.run([executable, 'blank', '-input', str(path)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)['status'] == 'ok'


def test_openhands_supported_empty_tool_selection_is_not_an_empty_enum(tmp_path):
    req = request('openhands', tmp_path)
    assert req['settings']['tools'] == []
    req['settings']['tools'] = ['unsupported-tool']
    with pytest.raises(ValueError, match='declared selection'):
        sdk_contract.validate_request(req, 'python')


def test_sdk_blocks_and_material_have_exact_private_bindings():
    root = ROOT/'praxis/handoff/sdk'
    index = json.loads((root/'capabilities.json').read_text())
    assert len(index['capabilities']) == len(BINDINGS) == 11
    assert index['readiness']['development_package_built']
    assert not index['readiness']['admitted']
    claimed_paths = set()
    for entry in index['capabilities']:
        plan = json.loads((root/entry['plan']).read_text())
        spec = json.loads((root/entry['node_spec']).read_text())
        block = json.loads((root/entry['block_file']).read_text())
        assert block['nodes'][0]['node']['digest'] == entry['node']['digest']
        assert block['nodes'][0]['node']['name'] == spec['identity']['name']
        sdk = next(d['contents']['sdk'] for d in spec['dimensions'] if d['name'] == 'handoff')
        assert sdk['contract_file'] in sdk['files']
        assert sdk['runner_file'] in sdk['files']
        assert sdk['runtime']['arguments'] is not None
        paths = {asset['rel_path'] for asset in plan['assets']}
        assert not paths & claimed_paths
        claimed_paths |= paths
        assert paths == set(sdk['files'])
        for asset in plan['assets']:
            if asset['file'].startswith('assets/runtime/'):
                assert asset['rel_path'] == sdk['runtime']['bundle_file']
                assert sdk['files'][asset['rel_path']] == 'sha256:' + sdk['runtime']['bundle_digest']
                assert Path(asset['file']).name == sdk['runtime']['bundle_digest'] + '.tar.gz'
            else:
                assert sdk['files'][asset['rel_path']] == sdk_contract.digest((root/'authoring'/asset['file']).read_bytes())
