import { accessSync, constants as fsConstants, chmodSync, mkdirSync, mkdtempSync, readFileSync, realpathSync, renameSync, rmSync, writeFileSync } from "node:fs";
import { dirname, isAbsolute, join, relative, sep } from "node:path";
import { tmpdir } from "node:os";
import { fileURLToPath, pathToFileURL } from "node:url";
import { createHash } from "node:crypto";

const BINARY_MIN_NODE = 18;
const bindings = {
  amp: { kind: "module", distribution: "@ampcode/sdk", module: "@ampcode/sdk", entrypoint: "execute" },
  cline: { kind: "module", distribution: "@cline/sdk", module: "@cline/sdk", entrypoint: "ClineCore" },
  codex: { kind: "module", distribution: "@openai/codex-sdk", module: "@openai/codex-sdk", entrypoint: "Codex" },
  droid: { kind: "module", distribution: "@factory/droid-sdk", module: "@factory/droid-sdk/node", entrypoint: "createSession" },
  dsh: {
    kind: "binary",
    binary: "/opt/homebrew/bin/dsh",
    sha256: "sha256:0ff7f1d72c4e0cbe14001709c81e20a04b70464118a7f78568952988e28f2ac5",
    version: "0.1.5-rc.1",
    arguments: ["--profile", "acp"],
    operations: ["session_turn"],
  },
  opencode: { kind: "module", distribution: "@opencode-ai/sdk", module: "@opencode-ai/sdk", entrypoint: "createOpencode" },
};

// A DSH continuation is authorized only by what this runner recorded after a
// successful fresh turn. The ledger lives inside the selected workspace, so a
// session cannot be adopted from another workspace's record, and no request
// field can assert ownership.
const DSH_LEDGER_SCHEMA = "praxis.dsh_session_ledger.v2";
const DSH_LEDGER_DIRECTORY = ".praxis";
const DSH_LEDGER_FILE = "dsh-sessions.json";

function dshLedgerPath(workspace) {
  if (typeof workspace !== "string" || !isAbsolute(workspace)) throw new Error("DSH workspace must be an exact absolute directory");
  return join(workspace, DSH_LEDGER_DIRECTORY, DSH_LEDGER_FILE);
}

function readDshSessions(workspace) {
  const path = dshLedgerPath(workspace);
  let raw;
  try {
    raw = readFileSync(path, "utf8");
  } catch (error) {
    if (error?.code === "ENOENT") return [];
    throw new Error(`DSH session ledger is unreadable: ${path}`);
  }
  let document;
  try {
    document = JSON.parse(raw);
  } catch {
    throw new Error(`DSH session ledger is not valid JSON: ${path}`);
  }
  if (!document || !Array.isArray(document.sessions)) throw new Error(`DSH session ledger has no session list: ${path}`);
  return document.sessions.filter((entry) => entry && typeof entry.session_id === "string" && typeof entry.workspace === "string");
}

function authorizeDshContinuation(workspace, sessionId, route) {
  const path = dshLedgerPath(workspace);
  const recorded = readDshSessions(workspace).filter((entry) => entry.session_id === sessionId);
  if (recorded.length === 0) throw new Error(`DSH continuation refused: session ${sessionId} is not recorded in ${path}`);
  const exactWorkspace = recorded.find((entry) => entry.workspace === workspace);
  if (!exactWorkspace) {
    throw new Error(`DSH continuation refused: session ${sessionId} is recorded for workspace ${recorded[0].workspace}, not ${workspace}`);
  }
  if (
    exactWorkspace.route_provider !== route.provider ||
    exactWorkspace.route_model !== route.model ||
    exactWorkspace.route_overlay_sha256 !== route.overlay_sha256
  ) {
    throw new Error(`DSH continuation refused: session ${sessionId} was recorded for a different provider, model, or route overlay`);
  }
}

function recordDshSession(workspace, sessionId, route) {
  if (typeof sessionId !== "string" || sessionId === "") throw new Error("DSH fresh turn returned no session identity to record");
  const path = dshLedgerPath(workspace);
  const sessions = readDshSessions(workspace);
  const prior = sessions.find((entry) => entry.session_id === sessionId && entry.workspace === workspace);
  if (prior) {
    if (
      prior.route_provider !== route.provider ||
      prior.route_model !== route.model ||
      prior.route_overlay_sha256 !== route.overlay_sha256
    ) throw new Error(`DSH session ${sessionId} already has a different route recorded in ${path}`);
    return;
  }
  sessions.push({
    session_id: sessionId,
    workspace,
    created_at: new Date().toISOString(),
    route_provider: route.provider,
    route_model: route.model,
    route_overlay_sha256: route.overlay_sha256,
  });
  mkdirSync(dirname(path), { recursive: true });
  const temporary = `${path}.${process.pid}.tmp`;
  writeFileSync(temporary, JSON.stringify({ schema: DSH_LEDGER_SCHEMA, sessions }, null, 2) + "\n", { mode: 0o600 });
  renameSync(temporary, path);
}

function exactKeys(value, expected) {
  return value && typeof value === "object" && !Array.isArray(value) &&
    JSON.stringify(Object.keys(value).sort()) === JSON.stringify([...expected].sort());
}

function readDshRouteOverlay(request) {
  const provider = request.route_provider;
  const model = request.route_model;
  const sourcePath = request.route_overlay_path;
  const expectedDigest = request.route_overlay_digest;
  if (typeof provider !== "string" || provider.length === 0) throw new Error("DSH route_provider must be a non-empty typed input");
  if (typeof model !== "string" || model.length === 0) throw new Error("DSH route_model must be a non-empty typed input");
  if (typeof sourcePath !== "string" || !isAbsolute(sourcePath)) throw new Error("DSH route_overlay_path must be an absolute path");
  if (typeof expectedDigest !== "string" || !/^sha256:[0-9a-f]{64}$/.test(expectedDigest)) throw new Error("DSH route_overlay_digest must be sha256 followed by 64 lowercase hex digits");
  let sourceBytes;
  try {
    sourceBytes = readFileSync(sourcePath);
  } catch {
    throw new Error(`DSH route overlay is unreadable: ${sourcePath}`);
  }
  const overlayDigest = rawDigest(sourceBytes);
  if (overlayDigest !== expectedDigest) throw new Error(`DSH route overlay digest mismatch: expected ${expectedDigest}, got ${overlayDigest}`);
  let overlay;
  try {
    overlay = JSON.parse(sourceBytes.toString("utf8"));
  } catch {
    throw new Error("DSH route overlay must be one JSON/YAML patch-list document");
  }
  if (!Array.isArray(overlay) || overlay.length !== 1) throw new Error("DSH route overlay must contain exactly one `acp` row");
  const row = overlay[0];
  if (!exactKeys(row, ["id", "config"]) || row.id !== "acp") throw new Error("DSH route overlay must target exactly the `acp` profile row");
  if (!exactKeys(row.config, ["provider", "model"])) throw new Error("DSH `acp` route overlay config must contain only provider and model");
  if (row.config.provider !== provider || row.config.model !== model) throw new Error("DSH route overlay provider/model do not match the typed route inputs");
  return { provider, model, overlay_sha256: overlayDigest, sourceBytes };
}

function stageDshRouteOverlay(route) {
  const directory = mkdtempSync(join(tmpdir(), "praxis-dsh-route-"));
  const path = join(directory, "route-overlay.json");
  try {
    writeFileSync(path, route.sourceBytes, { flag: "wx", mode: 0o600 });
    chmodSync(path, 0o400);
    if (rawDigest(readFileSync(path)) !== route.overlay_sha256) throw new Error("DSH route overlay snapshot changed while staging");
    return { path, cleanup: () => rmSync(directory, { recursive: true, force: true }) };
  } catch (error) {
    rmSync(directory, { recursive: true, force: true });
    throw error;
  }
}

const raw = await new Promise((resolve, reject) => {
  let data = "";
  process.stdin.setEncoding("utf8");
  process.stdin.on("data", (chunk) => { data += chunk; });
  process.stdin.on("end", () => resolve(data));
  process.stdin.on("error", reject);
});
const request = JSON.parse(raw);
// The printed worker executes exactly `node <runner>`: it passes no adapter
// argument. The adapter is the sibling asset the plan ships beside the runner
// under the same pinned material, and its bytes are still checked against the
// Node pin before anything is dispatched.
const adapterPath = fileURLToPath(new URL("./adapters.mjs", import.meta.url));
const rawDigest = (bytes) => `sha256:${createHash("sha256").update(bytes).digest("hex")}`;
let adapterBytes;
try {
  adapterBytes = readFileSync(adapterPath);
} catch {
  throw new Error(`TypeScript SDK adapter asset is missing beside the runner: ${adapterPath}`);
}
if (rawDigest(adapterBytes) !== request.adapter_digest) throw new Error("TypeScript SDK adapter digest drift");
const runtimeMajor = Number(process.versions.node.split(".")[0]);
const declaration = bindings[request.harness];
const minimum = { cline: 22, amp: 18, codex: 18, droid: 18, opencode: 18 }[request.harness];
if (minimum !== undefined) {
  if (runtimeMajor < minimum) throw new Error(`Node.js ${minimum}+ required for ${request.harness} SDK`);
} else if (declaration?.kind === "binary" && runtimeMajor < BINARY_MIN_NODE) {
  throw new Error(`Node.js ${BINARY_MIN_NODE}+ required for ${request.harness} harness`);
}
if (!declaration || (declaration.kind !== "module" && declaration.kind !== "binary")) {
  throw new Error(`harness ${request.harness} declares no binding kind`);
}
const requestKind = request.distribution !== undefined || request.module !== undefined || request.entrypoint !== undefined
  ? "module"
  : request.binary !== undefined
    ? "binary"
    : declaration.kind;

if (declaration.kind === "binary") {
  if (typeof declaration.binary !== "string" || !isAbsolute(declaration.binary)) {
    throw new Error(`harness ${request.harness} declares no absolute binary path`);
  }
  let binaryPath;
  try {
    binaryPath = realpathSync(declaration.binary);
  } catch {
    throw new Error(`DSH binary is unavailable for harness ${request.harness}: ${declaration.binary}`);
  }
  try {
    accessSync(binaryPath, fsConstants.X_OK);
  } catch {
    throw new Error(`DSH binary is not executable for harness ${request.harness}: ${binaryPath}`);
  }
  if (request.binary !== undefined) {
    if (typeof request.binary !== "string" || !isAbsolute(request.binary)) {
      throw new Error(`harness ${request.harness} binary request path must be absolute`);
    }
    let requestedBinary;
    try {
      requestedBinary = realpathSync(request.binary);
    } catch {
      throw new Error(`harness ${request.harness} binary request path is unavailable: ${request.binary}`);
    }
    if (requestedBinary !== binaryPath) {
      throw new Error(`harness ${request.harness} binary request path differs from the pinned binary`);
    }
  }
  const binaryDigest = rawDigest(readFileSync(binaryPath));
  if (binaryDigest !== declaration.sha256) {
    throw new Error(`DSH binary digest mismatch: expected ${declaration.sha256}, got ${binaryDigest} (harness ${request.harness})`);
  }
  if (!Array.isArray(declaration.arguments) || !declaration.arguments.every((argument) => typeof argument === "string")) {
    throw new Error(`harness ${request.harness} declares no binary argument array`);
  }
  if (requestKind !== "binary") {
    throw new Error(`harness ${request.harness} declares kind binary but request requires ${requestKind}`);
  }
  if (typeof request.version !== "string" || request.version !== declaration.version) {
    throw new Error(`harness ${request.harness} declares version ${declaration.version} but request requires ${request.version ?? "nothing"}`);
  }
  if (!Array.isArray(declaration.operations) || !declaration.operations.includes(request.operation)) {
    throw new Error(`harness ${request.harness} does not declare operation ${request.operation}`);
  }
  const argv = [...declaration.arguments];
  const route = request.harness === "dsh" ? readDshRouteOverlay(request) : undefined;
  // DSH continuation is checked before the adapter is even imported, so an
  // unrecorded, cross-workspace, or route-mismatched session never reaches a
  // DSH process spawn.
  const continuation = typeof request.session_id === "string" && request.session_id !== "";
  if (route && continuation) authorizeDshContinuation(request.workspace, request.session_id, route);
  let stagedOverlay;
  try {
    const binaryRequest = { ...request, binary: binaryPath, arguments: argv };
    if (route) {
      stagedOverlay = stageDshRouteOverlay(route);
      binaryRequest.patch = stagedOverlay.path;
      argv.push("--patch", stagedOverlay.path);
    } else if (request.patch !== undefined && request.patch !== null && request.patch !== "") {
      if (typeof request.patch !== "string" || !isAbsolute(request.patch)) {
        throw new Error(`harness ${request.harness} patch overlay must be an absolute path`);
      }
      try {
        accessSync(request.patch, fsConstants.R_OK);
      } catch {
        throw new Error(`harness ${request.harness} patch overlay is unreadable: ${request.patch}`);
      }
      binaryRequest.patch = request.patch;
      argv.push("--patch", request.patch);
    }
    binaryRequest.arguments = argv;
    const { invoke } = await import(pathToFileURL(adapterPath).href);
    const result = await invoke(binaryRequest, {});
    if (!result || typeof result.session_id !== "string" || typeof result.output !== "string" || typeof result.stop_reason !== "string") throw new Error("TypeScript SDK adapter returned an invalid result");
    if (route) {
      for (const [key, expected] of Object.entries({
        route_requested_provider: route.provider,
        route_requested_model: route.model,
        route_configured_provider: route.provider,
        route_configured_model: route.model,
        route_overlay_sha256: route.overlay_sha256,
      })) {
        if (result[key] !== expected) throw new Error(`DSH ACP adapter returned a mismatched ${key}`);
      }
      if (result.route_observed_provider !== route.provider || result.route_observed_model !== route.model) {
        throw new Error("DSH ACP adapter's observed provider/model do not match the pinned route");
      }
      if (typeof result.route_observation_source !== "string" || typeof result.route_observed_value !== "string") {
        throw new Error("DSH ACP adapter returned no actual session configuration evidence");
      }
    }
    if (route && !continuation) recordDshSession(request.workspace, result.session_id, route);
    const receipt = {
      schema: "praxis.harness_sdk_receipt.v1",
      status: "succeeded",
      harness: request.harness,
      sdk_operation: request.operation,
      binding: {
        kind: "binary",
        binary: binaryPath,
        sha256: declaration.sha256,
        version: declaration.version,
        arguments: argv,
      },
      adapter: request.adapter,
      adapter_digest: request.adapter_digest,
      runner_digest: request.runner_digest,
      session_id: result.session_id,
      output: result.output,
      stop_reason: result.stop_reason,
    };
    if (route) {
      for (const name of [
        "route_requested_provider",
        "route_requested_model",
        "route_configured_provider",
        "route_configured_model",
        "route_observed_provider",
        "route_observed_model",
        "route_overlay_sha256",
        "route_observation_source",
        "route_observed_value",
      ]) receipt[name] = result[name];
      const routeEvidence = {
        schema: "praxis.dsh_route_evidence.v1",
        requested: { provider: result.route_requested_provider, model: result.route_requested_model },
        configured: { provider: result.route_configured_provider, model: result.route_configured_model },
        observed: { provider: result.route_observed_provider, model: result.route_observed_model },
        overlay_sha256: result.route_overlay_sha256,
        observation_source: result.route_observation_source,
        observed_value: result.route_observed_value,
      };
      await new Promise((resolve, reject) => {
        process.stderr.write(`PRAXIS_DSH_ROUTE_EVIDENCE:${JSON.stringify(routeEvidence)}\n`, (error) => error ? reject(error) : resolve());
      });
    }
    await new Promise((resolve, reject) => {
      process.stdout.write(JSON.stringify(receipt) + "\n", (error) => error ? reject(error) : resolve());
    });
  } finally {
    stagedOverlay?.cleanup();
  }
} else {
if (requestKind !== "module") {
  throw new Error(`harness ${request.harness} declares kind module but request requires ${requestKind}`);
}
const binding = bindings[request.harness];
if (!binding || request.distribution !== binding.distribution || request.module !== binding.module || request.entrypoint !== binding.entrypoint) {
  throw new Error("TypeScript SDK binding differs from the pinned adapter table");
}
const packageJsonPath = realpathSync(join(process.cwd(), "node_modules", ...request.distribution.split("/"), "package.json"));
const packageRoot = dirname(packageJsonPath);
const packageDoc = JSON.parse(readFileSync(packageJsonPath, "utf8"));
if (packageDoc.name !== request.distribution || packageDoc.version !== request.version) {
  throw new Error("Installed TypeScript SDK version differs from the pinned exact version");
}
const subpath = request.module === request.distribution ? "." : `.${request.module.slice(request.distribution.length)}`;
function importTarget(value) {
  if (typeof value === "string") return value;
  if (!value || typeof value !== "object") return "";
  for (const key of ["import", "node", "default"]) {
    if (key in value) {
      const nested = importTarget(value[key]);
      if (nested) return nested;
    }
  }
  return "";
}
const target = importTarget(packageDoc.exports?.[subpath]) || packageDoc.module || packageDoc.main;
if (typeof target !== "string" || !target.startsWith("./")) throw new Error("Pinned TypeScript SDK ESM export is unavailable");
const modulePath = realpathSync(join(packageRoot, target));
const moduleRelative = relative(packageRoot, modulePath);
if (moduleRelative === ".." || moduleRelative.startsWith(`..${sep}`) || isAbsolute(moduleRelative)) {
  throw new Error("Pinned TypeScript SDK export leaves its package root");
}
const sdk = await import(pathToFileURL(modulePath).href);
if (!(request.entrypoint in sdk)) throw new Error("Pinned TypeScript SDK entrypoint is unavailable");

const { invoke } = await import(pathToFileURL(adapterPath).href);
const result = await invoke(request, sdk);
if (!result || typeof result.session_id !== "string" || typeof result.output !== "string") throw new Error("TypeScript SDK adapter returned an invalid result");
process.stdout.write(JSON.stringify({
  schema: "praxis.harness_sdk_receipt.v1",
  status: "succeeded",
  harness: request.harness,
  sdk_operation: request.operation,
  distribution: request.distribution,
  distribution_version: packageDoc.version,
  module: request.module,
  entrypoint: request.entrypoint,
  adapter: request.adapter,
  adapter_digest: request.adapter_digest,
  runner_digest: request.runner_digest,
  session_id: result.session_id,
  output: result.output,
}) + "\n");
}
