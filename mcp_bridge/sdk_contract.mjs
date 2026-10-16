import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';

export const digest = (bytes) => `sha256:${createHash('sha256').update(bytes).digest('hex')}`;
export function validate(value, schema, path = 'settings') {
  const kind = Array.isArray(value) ? 'array' : value === null ? 'null' : typeof value;
  if (kind !== schema.type) throw new Error(`${path} must be ${schema.type}`);
  if (schema.enum && !schema.enum.includes(value)) throw new Error(`${path} is not a declared selection`);
  if (kind === 'string' && schema.minLength && !value.trim()) throw new Error(`${path} must be nonempty`);
  if (kind === 'object') {
    for (const key of schema.required ?? []) if (!Object.hasOwn(value, key)) throw new Error(`${path}.${key} is required`);
    for (const [key, item] of Object.entries(value)) {
      const child = Object.hasOwn(schema.properties ?? {}, key) ? schema.properties[key] : schema.additionalProperties;
      if (!child) throw new Error(`${path}.${key} is not declared`);
      validate(item, child, `${path}.${key}`);
    }
  }
  if (kind === 'array') value.forEach((item, index) => validate(item, schema.items, `${path}[${index}]`));
}

export function validateRequest(request, bindingsPath) {
  const allowed = new Set(['harness', 'operation', 'distribution', 'version', 'module', 'entrypoint',
    'adapter', 'adapter_digest', 'runner_digest', 'contract_digest', 'bindings_digest',
    'prompt', 'workspace', 'settings']);
  for (const key of Object.keys(request)) if (!allowed.has(key)) throw new Error(`undeclared SDK request field: ${key}`);
  const raw = readFileSync(bindingsPath);
  if (digest(raw) !== request.bindings_digest) throw new Error('SDK declaration digest drift');
  const binding = JSON.parse(raw).bindings[request.harness];
  if (!binding || binding.language !== 'typescript') throw new Error('Unsupported TypeScript SDK binding');
  if (!binding.operations.includes(request.operation)) throw new Error('SDK Node supports fresh operations only');
  for (const key of ['distribution', 'module', 'entrypoint', 'version']) {
    if (request[key] !== binding[key]) throw new Error(`SDK ${key} differs from the declaration`);
  }
  if (request.adapter !== `${request.harness}_ts_fresh`) throw new Error('SDK adapter differs from the declaration');
  for (const key of ['prompt', 'workspace']) {
    if (typeof request[key] !== 'string' || !request[key].trim()) throw new Error(`${key} must be nonempty`);
  }
  for (const key of ['model', 'approval', 'provider_id', 'session_id', 'session_owner']) {
    if (Object.hasOwn(request, key)) throw new Error(`${key} is not a fresh SDK request field`);
  }
  validate(request.settings, binding.settings);
  return binding;
}
