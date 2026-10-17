import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { invoke } from '../mcp_bridge/sdk_ts_adapters.mjs';
import { validateRequest, digest } from '../mcp_bridge/sdk_contract.mjs';
const bindingsPath = new URL('../mcp_bridge/sdk_bindings.json', import.meta.url);
const bytes = readFileSync(bindingsPath);
const bindings = JSON.parse(bytes).bindings;
function sample(schema) {
  if (schema.enum) return structuredClone(schema.enum[0]);
  if (schema.type === 'object') return Object.fromEntries(schema.required.map(key => [key, sample(schema.properties[key] ?? schema.additionalProperties)]));
  return { string: 'selected', boolean: false, array: [] }[schema.type];
}
function request(harness) {
  const binding = bindings[harness];
  return { harness, operation: 'fresh', distribution: binding.distribution, version: binding.version,
    module: binding.module, entrypoint: binding.entrypoint, adapter: `${harness}_ts_fresh`,
    bindings_digest: digest(bytes), prompt: 'same prompt', workspace: process.cwd(), settings: sample(binding.settings) };
}
for (const [harness, binding] of Object.entries(bindings).filter(([, b]) => b.language === 'typescript')) {
  test(`${harness}: declaration accepts explicit choices and refuses missing/unknown/type/operation drift`, () => {
    const req = request(harness);
    assert.deepEqual(validateRequest(req, bindingsPath), binding);
    for (const mutate of [
      r => delete r.settings[Object.keys(r.settings)[0]],
      r => r.settings.invented = true,
      r => r.settings = [],
      r => r.operation = 'resume',
      r => r.approval = 'unattended',
      r => r.adapter = 'other',
    ]) {
      const changed = structuredClone(req); mutate(changed);
      assert.throws(() => validateRequest(changed, bindingsPath));
    }
  });
}

test('Codex maps selected model and permissions without an adapter profile', async () => {
  const seen = [];
  const sdk = { Codex: class {
    constructor(...args) { assert.deepEqual(args, []); }
    startThread(options) { seen.push(options); return { id: 'fresh-id', run: async () => ({ finalResponse: 'answer' }) }; }
  } };
  const req = request('codex');
  await invoke(req, sdk);
  const baseline = structuredClone(req.settings);
  for (const [key, value] of Object.entries({ model: 'held-out-model', sandboxMode: 'workspace-write',
    networkAccessEnabled: true, approvalPolicy: 'on-request', webSearchMode: 'live' })) {
    req.settings = { ...baseline, [key]: value };
    await invoke(req, sdk);
    assert.deepEqual(seen.at(-1), { workingDirectory: req.workspace, ...baseline, [key]: value });
  }
  assert.deepEqual(seen[0], { workingDirectory: req.workspace, ...baseline });
});

test('Amp forwards visibility, mode and permission choices and requires terminal result', async () => {
  let seen;
  let terminal = true;
  const sdk = { async *execute(options) {
    seen = options;
    yield { type: 'system', subtype: 'init', session_id: 'fresh-id' };
    if (terminal) yield { type: 'result', is_error: false, result: 'answer' };
  } };
  const req = request('amp');
  await invoke(req, sdk);
  assert.deepEqual(seen.options, { cwd: req.workspace, ...req.settings });
  req.settings.visibility = 'workspace'; req.settings.dangerouslyAllowAll = true;
  await invoke(req, sdk);
  assert.equal(seen.options.visibility, 'workspace'); assert.equal(seen.options.dangerouslyAllowAll, true);
  terminal = false;
  await assert.rejects(invoke(req, sdk), /no final result/);
});

test('Cline maps each tool policy and always disposes its owned runtime', async () => {
  let options, input, disposed = 0, fail = false;
  const sdk = { ClineCore: { create: async o => {
    options = o;
    return { start: async i => { input = i; if (fail) throw Error('provider failed'); return { sessionId: 'fresh-id', result: { text: 'answer', finishReason: 'completed' } }; },
      dispose: async () => { disposed++; } };
  } } };
  const req = request('cline');
  await invoke(req, sdk);
  assert.deepEqual(options.toolPolicies, req.settings.toolPolicies);
  assert.equal(input.config.modelId, req.settings.model);
  assert.equal(input.config.enableTools, false);
  req.settings.toolPolicies.editor.autoApprove = true;
  req.settings.unmatched_tool_approval = 'approve';
  await invoke(req, sdk);
  assert.equal(input.toolPolicies.editor.autoApprove, true);
  assert.deepEqual(await options.capabilities.requestToolApproval(), { approved: true });
  fail = true;
  await assert.rejects(invoke(req, sdk), /provider failed/);
  assert.equal(disposed, 3);
});

test('Droid maps native autonomy and requires a successful terminal result', async () => {
  let options, closed = 0, terminal = true;
  const sdk = { ToolConfirmationOutcome: { Cancel: 'cancel' },
    createSession: async o => {
      options = o;
      return { id: 'fresh-id', async *stream() { yield { type: 'assistant', text: 'answer' }; if (terminal) yield { type: 'result', success: true }; },
        close: async () => { closed++; } };
    } };
  const req = request('droid');
  await invoke(req, sdk);
  assert.equal(options.autonomyLevel, req.settings.autonomyLevel);
  assert.equal(options.permissionHandler(), 'cancel');
  req.settings.permission = 'unattended'; req.settings.autonomyLevel = 'high';
  await invoke(req, sdk);
  assert.equal(options.autonomyLevel, 'high'); assert.equal(options.permissionHandler, undefined);
  terminal = false;
  await assert.rejects(invoke(req, sdk), /no successful terminal/);
  assert.equal(closed, 3);
});

test('OpenCode binds both requests to the workspace and closes its owned server', async () => {
  const calls = [];
  let closed = 0, error = false;
  const sdk = { createOpencode: async options => {
    calls.push(['server', options]);
    return { server: { close: async () => { closed++; } }, client: { session: {
      create: async options => { calls.push(['create', options]); return { data: { id: 'fresh-id' } }; },
      prompt: async options => { calls.push(['prompt', options]); return { data: { info: { error: error ? {} : undefined }, parts: [{ type: 'text', text: 'answer' }] } }; },
    } } };
  } };
  const req = request('opencode');
  await invoke(req, sdk);
  assert.deepEqual(calls[0][1].config.permission, req.settings.permission);
  assert.deepEqual(calls[1][1].query, { directory: req.workspace });
  assert.deepEqual(calls[2][1].query, { directory: req.workspace });
  assert.deepEqual(calls[2][1].body.model, req.settings.model);
  error = true;
  await assert.rejects(invoke(req, sdk), /assistant error/);
  assert.equal(closed, 2);
});

test('Droid native stdio is explicit SDK configuration and closes on failed creation', async () => {
  let connected = 0, closed = 0;
  const sdk = {
    ToolConfirmationOutcome: { Cancel: 'cancel' },
    ProcessTransport: class {
      constructor(options) { assert.equal(options.cwd, process.cwd()); }
      async connect() { connected++; }
      async close() { closed++; }
    },
    createSession: async options => {
      assert.ok(options.transport instanceof sdk.ProcessTransport);
      throw Error('owned creation failure');
    },
  };
  const req = request('droid'); req.settings.transport = 'native_stdio';
  await assert.rejects(invoke(req, sdk), /owned creation failure/);
  assert.equal(connected, 1); assert.equal(closed, 1);
});

for (const harness of ['amp', 'cline', 'codex', 'droid', 'opencode']) {
  test(`${harness}: refuses resume before touching SDK`, async () => {
    await assert.rejects(invoke({ ...request(harness), operation: 'resume' }, new Proxy({}, { get() { throw Error('SDK touched'); } })), /fresh operations only/);
  });
}

test('Codex never calls an empty result a success', async () => {
  const sdk = { Codex: class { startThread() { return { id: 'id', run: async () => ({ finalResponse: '' }) }; } } };
  await assert.rejects(invoke(request('codex'), sdk), /assistant output/);
});

test('native array enum uses structural equality', async () => {
  const { validate } = await import('../mcp_bridge/sdk_contract.mjs');
  const schema = bindings.openhands.settings.properties.tools;
  assert.doesNotThrow(() => validate([], schema));
  assert.throws(() => validate(['unsupported-tool'], schema));
});

for (const harness of ['amp', 'cline', 'codex', 'droid']) {
  test(`${harness}: nonempty settings rule survives native schema lowering`, () => {
    const req = request(harness);
    const key = Object.keys(bindings[harness].settings.properties).find(k => {
      const schema = bindings[harness].settings.properties[k];
      return schema.type === 'string' && !schema.enum;
    });
    req.settings[key] = '   ';
    assert.throws(() => validateRequest(req, bindingsPath), /nonempty/);
  });
}
