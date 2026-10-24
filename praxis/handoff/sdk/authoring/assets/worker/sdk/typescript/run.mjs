import { readFileSync, realpathSync } from "node:fs";
import { dirname, isAbsolute, join, relative, sep } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { createHash } from "node:crypto";

const bindings = {
  amp: { kind: "module", distribution: "@ampcode/sdk", module: "@ampcode/sdk", entrypoint: "execute" },
  cline: { kind: "module", distribution: "@cline/sdk", module: "@cline/sdk", entrypoint: "ClineCore" },
  codex: { kind: "module", distribution: "@openai/codex-sdk", module: "@openai/codex-sdk", entrypoint: "Codex" },
  droid: { kind: "module", distribution: "@factory/droid-sdk", module: "@factory/droid-sdk/node", entrypoint: "createSession" },
  opencode: { kind: "module", distribution: "@opencode-ai/sdk", module: "@opencode-ai/sdk", entrypoint: "createOpencode" },
};

const raw = await new Promise((resolve, reject) => {
  let data = "";
  process.stdin.setEncoding("utf8");
  process.stdin.on("data", (chunk) => { data += chunk; });
  process.stdin.on("end", () => resolve(data));
  process.stdin.on("error", reject);
});
const request = JSON.parse(raw);
const adapterPath = join(dirname(fileURLToPath(import.meta.url)), "adapters.mjs");
const rawDigest = (bytes) => `sha256:${createHash("sha256").update(bytes).digest("hex")}`;
if (rawDigest(readFileSync(adapterPath)) !== request.adapter_digest) throw new Error("TypeScript SDK adapter digest drift");
const runtimeMajor = Number(process.versions.node.split(".")[0]);
const declaration = bindings[request.harness];
const minimum = { cline: 22, amp: 18, codex: 18, droid: 18, opencode: 18 }[request.harness];
if (minimum !== undefined) {
  if (runtimeMajor < minimum) throw new Error(`Node.js ${minimum}+ required for ${request.harness} SDK`);
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
