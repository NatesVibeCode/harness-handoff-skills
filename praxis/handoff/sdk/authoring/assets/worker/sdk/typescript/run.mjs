import { readFileSync, realpathSync, statSync } from "node:fs";
import { dirname, isAbsolute, join, relative, sep } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { createHash } from "node:crypto";

const raw = await new Promise((resolve, reject) => {
  let data = "";
  process.stdin.setEncoding("utf8");
  process.stdin.on("data", (chunk) => { data += chunk; });
  process.stdin.on("end", () => resolve(data));
  process.stdin.on("error", reject);
});
const request = JSON.parse(raw);
const adapterPath = process.argv[2];
if (!adapterPath) throw new Error("TypeScript SDK adapter asset missing");
const rawDigest = (bytes) => `sha256:${createHash("sha256").update(bytes).digest("hex")}`;
if (rawDigest(readFileSync(adapterPath)) !== request.adapter_digest) throw new Error("TypeScript SDK adapter digest drift");
const runnerPath = fileURLToPath(import.meta.url);
if (rawDigest(readFileSync(runnerPath)) !== request.runner_digest) throw new Error("TypeScript SDK runner digest drift");
const contractPath = join(dirname(runnerPath), "contract.mjs");
if (rawDigest(readFileSync(contractPath)) !== request.contract_digest) throw new Error("SDK contract source digest drift");
const { validateRequest } = await import(pathToFileURL(contractPath).href);
const binding = validateRequest(request, join(dirname(runnerPath), "sdk_bindings.json"));
if (!isAbsolute(request.workspace) || !statSync(request.workspace).isDirectory() || realpathSync(request.workspace) !== realpathSync(process.cwd())) {
  throw new Error("SDK workspace differs from the selected process working directory");
}
const runtimeMajor = Number(process.versions.node.split(".")[0]);
if (runtimeMajor < Number(binding.minimum_runtime)) throw new Error("Node.js runtime is below the SDK contract minimum");
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
  for (const key of Object.keys(value)) {
    if (["import", "node", "default"].includes(key)) {
      const nested = importTarget(value[key]);
      if (nested) return nested;
    }
  }
  return "";
}
const target = importTarget(subpath === "." && (typeof packageDoc.exports === "string" || !Object.keys(packageDoc.exports ?? {}).some((key) => key.startsWith("."))) ? packageDoc.exports : packageDoc.exports?.[subpath]) || packageDoc.module || packageDoc.main;
if (typeof target !== "string" || !target.startsWith("./")) throw new Error("Pinned TypeScript SDK ESM export is unavailable");
const modulePath = realpathSync(join(packageRoot, target));
const moduleRelative = relative(packageRoot, modulePath);
if (moduleRelative === ".." || moduleRelative.startsWith(`..${sep}`) || isAbsolute(moduleRelative)) {
  throw new Error("Pinned TypeScript SDK export leaves its package root");
}
// Vendor stdout is diagnostic output. Only the final receipt uses stdout.
const receiptWrite = process.stdout.write.bind(process.stdout);
process.stdout.write = process.stderr.write.bind(process.stderr);
const sdk = await import(pathToFileURL(modulePath).href);
if (!(request.entrypoint in sdk)) throw new Error("Pinned TypeScript SDK entrypoint is unavailable");

const { invoke } = await import(pathToFileURL(adapterPath).href);
const result = await invoke(request, sdk);
if (!result || typeof result.session_id !== "string" || typeof result.output !== "string") throw new Error("TypeScript SDK adapter returned an invalid result");
function canonical(value) {
  if (Array.isArray(value)) return value.map(canonical);
  if (value && typeof value === "object") return Object.fromEntries(Object.keys(value).sort().map((key) => [key, canonical(value[key])]));
  return value;
}
receiptWrite(JSON.stringify({
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
  contract_digest: request.contract_digest,
  bindings_digest: request.bindings_digest,
  settings_digest: rawDigest(Buffer.from(JSON.stringify(canonical(request.settings)))),
  session_id: result.session_id,
  output: result.output,
}) + "\n");
