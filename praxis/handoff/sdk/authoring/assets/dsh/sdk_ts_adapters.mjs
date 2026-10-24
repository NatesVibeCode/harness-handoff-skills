import { spawn } from "node:child_process";
import { accessSync, constants as fsConstants, readFileSync } from "node:fs";
import { createHash } from "node:crypto";
import net from "node:net";
import { isAbsolute } from "node:path";

function textFrom(value) {
  if (typeof value === "string") return value;
  if (!value || typeof value !== "object") return "";
  for (const key of ["finalResponse", "outputText", "text", "result"]) {
    if (typeof value[key] === "string") return value[key];
    if (value[key] && typeof value[key] === "object") {
      const nested = textFrom(value[key]);
      if (nested) return nested;
    }
  }
  const parts = value.parts ?? value.content ?? value.messages;
  if (Array.isArray(parts)) {
    return parts.map((part) => textFrom(part)).filter(Boolean).join("\n");
  }
  return "";
}

function unwrap(value) {
  if (value && typeof value === "object" && "data" in value) return value.data;
  return value;
}

async function choosePort() {
  const server = net.createServer();
  await new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", resolve);
  });
  const address = server.address();
  if (!address || typeof address === "string") throw new Error("loopback port allocation failed");
  const port = address.port;
  await new Promise((resolve, reject) => server.close((error) => error ? reject(error) : resolve()));
  return port;
}

async function amp(request, sdk) {
  if (request.operation === "history") {
    if (typeof sdk.threads?.markdown !== "function") throw new Error("Amp history API unavailable");
    return { session_id: request.session_id, output: await sdk.threads.markdown({ threadId: request.session_id }) };
  }
  if (request.operation === "resume" && request.session_owner !== "operator_owned") throw new Error("Amp continuation requires operator-owned session confirmation");
  if (request.approval !== "native") throw new Error("Amp SDK must retain native permission settings");
  const options = { cwd: request.workspace, visibility: "private" };
  if (request.operation === "resume") options.continue = request.session_id;
  let sessionId = request.operation === "resume" ? request.session_id : "";
  let output = "";
  let failed = false;
  let completed = false;
  for await (const message of sdk.execute({ prompt: request.prompt, options })) {
    if (message?.type === "system" && message.subtype === "init" && typeof message.session_id === "string") sessionId = message.session_id;
    if (message?.type === "result") {
      completed = true;
      if (message.is_error) failed = true;
      else if (typeof message.result === "string") output = message.result;
      if (!sessionId && typeof message.session_id === "string") sessionId = message.session_id;
    }
  }
  if (failed) throw new Error("Amp SDK operation returned an error result");
  if (!completed || !sessionId || !output.trim()) throw new Error("Amp SDK operation returned no final result, session id, or output");
  return { session_id: sessionId, output };
}

function clinePolicies(approval) {
  const unattended = approval === "unattended";
  if (!unattended && approval !== "deny_unapproved") throw new Error("Cline SDK requires explicit approval mode");
  return {
    read_files: { autoApprove: true },
    search_codebase: { autoApprove: true },
    run_commands: { autoApprove: unattended },
    editor: { autoApprove: unattended },
  };
}

async function cline(request, sdk) {
  const coreFactory = sdk.ClineCore;
  if (!coreFactory || typeof coreFactory.create !== "function") throw new Error("ClineCore SDK entrypoint unavailable");
  const policies = clinePolicies(request.approval);
  const provider = request.provider_id;
  const apiKeyEnv = {
    anthropic: "ANTHROPIC_API_KEY",
    openai: "OPENAI_API_KEY",
    google: "GOOGLE_API_KEY",
    gemini: "GEMINI_API_KEY",
    openrouter: "OPENROUTER_API_KEY",
    groq: "GROQ_API_KEY",
    mistral: "MISTRAL_API_KEY",
    deepseek: "DEEPSEEK_API_KEY",
  }[provider];
  if (!provider || !apiKeyEnv) throw new Error("Cline provider is not in the explicit provider allowlist");
  const clineRuntime = await coreFactory.create({
    clientName: "praxis-harness-handoff",
    backendMode: "local",
    toolPolicies: policies,
    capabilities: {
      requestToolApproval: async () => ({ approved: request.approval === "unattended" }),
    },
  });
  try {
    if (request.operation === "history") {
      return { session_id: request.session_id, output: JSON.stringify(await clineRuntime.readMessages(request.session_id)) };
    }
    if (request.operation === "resume") {
      if (request.session_owner !== "operator_owned") throw new Error("Cline continuation requires operator-owned session confirmation");
      const prior = await clineRuntime.get(request.session_id);
      const priorDirectory = prior?.manifest?.workspaceRoot ?? prior?.manifest?.cwd ?? "";
      if (priorDirectory && priorDirectory !== request.workspace) throw new Error("Cline session workspace differs from the selected workspace");
      const result = await clineRuntime.send({ sessionId: request.session_id, prompt: request.prompt });
      return { session_id: request.session_id, output: textFrom(result) };
    }
    const session = await clineRuntime.start({
      prompt: request.prompt,
      interactive: false,
      config: {
        providerId: provider,
        modelId: request.model,
        apiKey: process.env[apiKeyEnv],
        cwd: request.workspace,
        workspaceRoot: request.workspace,
        enableTools: true,
        enableSpawnAgent: false,
        enableAgentTeams: false,
      },
      toolPolicies: policies,
    });
    return { session_id: session.sessionId, output: textFrom(session.result) };
  } finally {
    await clineRuntime.dispose("SDK operation complete");
  }
}

async function codex(request, sdk) {
  if (request.operation !== "fresh") throw new Error("Codex SDK route supports fresh sessions only");
  const codexClient = new sdk.Codex({ config: { default_permissions: ":read-only" } });
  const thread = codexClient.startThread({ workingDirectory: request.workspace });
  const result = await thread.run(request.prompt);
  const sessionId = typeof thread.id === "string" ? thread.id : "";
  if (!sessionId) throw new Error("Codex SDK did not expose the fresh thread id");
  return { session_id: sessionId, output: textFrom(result) };
}

async function droid(request, sdk) {
  const { AutonomyLevel, DroidInteractionMode, DroidMessageType } = sdk;
  const unattended = request.approval === "unattended";
  if (!unattended && request.approval !== "deny_unapproved") throw new Error("Droid SDK requires explicit approval mode");
  const { ToolConfirmationOutcome } = sdk;
  const permissionHandler = unattended ? undefined : () => ToolConfirmationOutcome.Cancel;
  let session;
  if (request.operation === "resume") {
    if (request.session_owner !== "operator_owned") throw new Error("Droid continuation requires operator-owned session confirmation");
    session = await sdk.resumeSession(request.session_id, { permissionHandler });
    await session.updateSettings({
      interactionMode: DroidInteractionMode.Auto,
      autonomyLevel: unattended ? AutonomyLevel.High : AutonomyLevel.Off,
    });
  } else {
    const options = {
      cwd: request.workspace,
      interactionMode: DroidInteractionMode.Auto,
      autonomyLevel: unattended ? AutonomyLevel.High : AutonomyLevel.Off,
      permissionHandler,
    };
    if (request.model) options.modelId = request.model;
    session = await sdk.createSession(options);
  }
  const sessionId = session.id;
  let output = "";
  let failed = false;
  try {
    for await (const message of session.stream(request.prompt)) {
      if (message?.type === DroidMessageType.Assistant && typeof message.text === "string") output += message.text;
      if (message?.type === DroidMessageType.Error) failed = true;
      if (message?.type === DroidMessageType.Result && message.success === false) failed = true;
    }
  } finally {
    await session.close();
  }
  if (failed) throw new Error("Droid SDK turn returned a failed result");
  if (!output.trim()) throw new Error("Droid SDK operation returned no assistant output");
  return { session_id: sessionId, output };
}

const DSH_PROFILE_ID = "acp";

function rawDigest(bytes) {
  return `sha256:${createHash("sha256").update(bytes).digest("hex")}`;
}

function exactKeys(value, expected) {
  return value && typeof value === "object" && !Array.isArray(value) &&
    JSON.stringify(Object.keys(value).sort()) === JSON.stringify([...expected].sort());
}

function configuredDshRoute(configOptions, requested, patch, digest) {
  if (!Array.isArray(configOptions)) throw new Error("DSH ACP session returned no configOptions route evidence");
  const option = configOptions.find((entry) => entry?.id === "model" && entry?.category === "model");
  if (!option || typeof option.currentValue !== "string") throw new Error("DSH ACP session returned no currentValue for its model config option");
  let selection;
  try {
    selection = JSON.parse(option.currentValue);
  } catch {
    throw new Error("DSH ACP model config currentValue is not the supported provider/model selection");
  }
  if (!Array.isArray(selection) || selection.length !== 2 || selection.some((value) => typeof value !== "string")) {
    throw new Error("DSH ACP model config currentValue is not a provider/model pair");
  }
  const observed = { provider: selection[0], model: selection[1] };
  if (observed.provider !== requested.provider || observed.model !== requested.model) {
    throw new Error(`DSH ACP session route mismatch: requested ${requested.provider}/${requested.model}, observed ${observed.provider}/${observed.model}`);
  }
  return {
    observed,
    currentValue: option.currentValue,
    patch,
    overlay_sha256: digest,
  };
}

function validateDshOverlay(request) {
  if (typeof request.route_provider !== "string" || request.route_provider.length === 0) throw new Error("DSH requires a typed route_provider input");
  if (typeof request.route_model !== "string" || request.route_model.length === 0) throw new Error("DSH requires a typed route_model input");
  if (typeof request.patch !== "string" || !isAbsolute(request.patch)) throw new Error("DSH requires a staged absolute route overlay");
  if (typeof request.route_overlay_digest !== "string" || !/^sha256:[0-9a-f]{64}$/.test(request.route_overlay_digest)) throw new Error("DSH route_overlay_digest must be sha256 followed by 64 lowercase hex digits");
  const bytes = readFileSync(request.patch);
  const digest = rawDigest(bytes);
  if (digest !== request.route_overlay_digest) throw new Error(`DSH staged route overlay digest mismatch: expected ${request.route_overlay_digest}, got ${digest}`);
  let overlay;
  try {
    overlay = JSON.parse(bytes.toString("utf8"));
  } catch {
    throw new Error("DSH staged route overlay is not one JSON/YAML patch-list document");
  }
  if (!Array.isArray(overlay) || overlay.length !== 1) throw new Error("DSH staged route overlay must contain exactly one `acp` row");
  const row = overlay[0];
  if (!exactKeys(row, ["id", "config"]) || row.id !== DSH_PROFILE_ID) throw new Error("DSH staged route overlay must target exactly the `acp` profile row");
  if (!exactKeys(row.config, ["provider", "model"])) throw new Error("DSH staged `acp` route config must contain only provider and model");
  if (row.config.provider !== request.route_provider || row.config.model !== request.route_model) throw new Error("DSH staged overlay route differs from the typed route inputs");
  if (!Array.isArray(request.arguments)) throw new Error("DSH ACP arguments must be an explicit array");
  const patchIndexes = request.arguments.flatMap((value, index) => value === "--patch" ? [index] : []);
  if (patchIndexes.length !== 1 || request.arguments[patchIndexes[0] + 1] !== request.patch) throw new Error("DSH ACP arguments do not carry the exact staged route overlay");
  return {
    requested: { provider: request.route_provider, model: request.route_model },
    configured: { provider: row.config.provider, model: row.config.model },
    overlay_sha256: digest,
  };
}

function dshBinary(request) {
  if (typeof request.binary !== "string" || !isAbsolute(request.binary)) throw new Error("DSH binary must be an explicit absolute path");
  try {
    accessSync(request.binary, fsConstants.X_OK);
  } catch {
    throw new Error(`DSH binary is not executable: ${request.binary}`);
  }
  return request.binary;
}

function dshConnection(binary, args, cwd, permissionOptionId) {
  const child = spawn(binary, args, { cwd, stdio: ["pipe", "pipe", "pipe"] });
  child.stdout.setEncoding("utf8");
  child.stderr.setEncoding("utf8");
  child.stdin.on("error", () => {});
  child.stdout.on("error", () => {});
  let buffer = "";
  let nextId = 1;
  let failure = "";
  let closed = false;
  const pending = new Map();
  const chunks = [];

  const fail = (message) => {
    if (!failure) failure = message;
    for (const entry of pending.values()) entry.reject(new Error(message));
    pending.clear();
  };

  const reply = (id, payload) => {
    child.stdin.write(JSON.stringify({ jsonrpc: "2.0", id, ...payload }) + "\n");
  };

  const receive = (frame) => {
    if (frame.method !== undefined) {
      receiveRequest(frame);
      return;
    }
    if (frame.id !== undefined && pending.has(frame.id)) {
      const entry = pending.get(frame.id);
      pending.delete(frame.id);
      if (frame.error) entry.reject(new Error(frame.error.message ?? "DSH ACP JSON-RPC error"));
      else entry.resolve(frame.result);
    }
  };

  const receiveRequest = (frame) => {
    if (frame.method === "session/update") {
      const update = frame.params?.update;
      if (update?.sessionUpdate === "agent_message_chunk" && update.content?.type === "text" && typeof update.content.text === "string") chunks.push(update.content.text);
      return;
    }
    if (frame.method && frame.id !== undefined) {
      if (frame.method === "session/request_permission") reply(frame.id, { result: { outcome: { outcome: "selected", optionId: permissionOptionId } } });
      else reply(frame.id, { error: { code: -32601, message: `Unsupported DSH ACP server request: ${frame.method}` } });
    }
  };

  child.on("error", (error) => fail(`DSH ACP process could not launch: ${error.message}`));
  child.stderr.pipe(process.stderr, { end: false });
  child.on("close", () => { closed = true; });
  child.stdout.on("data", (chunk) => {
    buffer += chunk;
    for (let newline = buffer.indexOf("\n"); newline >= 0; newline = buffer.indexOf("\n")) {
      const line = buffer.slice(0, newline).trim();
      buffer = buffer.slice(newline + 1);
      if (!line) continue;
      let frame;
      try {
        frame = JSON.parse(line);
      } catch {
        fail("DSH ACP stdout carried a non-protocol line");
        child.kill("SIGKILL");
        return;
      }
      receive(frame);
    }
  });
  child.on("exit", (code, signal) => fail(`DSH ACP process exited before completion (code ${code}, signal ${signal})`));

  function call(method, params) {
    if (failure) return Promise.reject(new Error(failure));
    if (child.exitCode !== null || child.signalCode !== null) return Promise.reject(new Error(`DSH ACP process is not running for ${method}`));
    const id = nextId++;
    return new Promise((resolve, reject) => {
      pending.set(id, {
        resolve,
        reject,
      });
      try {
        child.stdin.write(JSON.stringify({ jsonrpc: "2.0", id, method, params }) + "\n");
      } catch (error) {
        pending.delete(id);
        reject(new Error(`DSH ACP ${method} could not be written: ${error.message}`));
      }
    });
  }

  async function stop() {
    if (closed || child.exitCode !== null || child.signalCode !== null) return;
    child.stdin.end();
    await new Promise((resolve) => {
      if (closed) resolve();
      else child.once("close", resolve);
    });
  }

  return { call, stop, output: () => chunks.join(""), failed: () => Boolean(failure) };
}

async function dsh(request, sdk) {
  if (request.operation !== "session_turn") throw new Error("DSH ACP route serves one session turn per call");
  // The mode is never a caller assertion: a non-empty exact session id asks to
  // continue that session and an empty one opens a fresh session. Whether the
  // continuation is authorized is decided by the pinned runner from its own
  // durable record, before this adapter is called.
  const resume = typeof request.session_id === "string" && request.session_id !== "";
  if (typeof request.workspace !== "string" || !request.workspace) throw new Error("DSH ACP operation requires an explicit workspace");
  if (!Array.isArray(request.arguments) || !request.arguments.every((argument) => typeof argument === "string")) throw new Error("DSH ACP arguments must be an explicit array");
  const route = validateDshOverlay(request);
  const connection = dshConnection(dshBinary(request), [...request.arguments], request.workspace, request.approval === "unattended" ? "allow-once" : "reject-once");
  let sessionId = resume ? request.session_id : "";
  let ready = false;
  let observed;
  try {
    const initialized = await connection.call("initialize", {
      protocolVersion: 1,
      clientCapabilities: {},
      clientInfo: { name: "praxis-harness-handoff", version: "1.0.0" },
    });
    const capabilities = initialized?.agentCapabilities?.sessionCapabilities ?? {};
    if (resume && !capabilities.resume) throw new Error("DSH ACP profile does not advertise session/resume");
    if (!resume) {
      const created = await connection.call("session/new", { cwd: request.workspace, mcpServers: [] });
      sessionId = typeof created?.sessionId === "string" ? created.sessionId : "";
      if (!sessionId) throw new Error("DSH ACP session/new returned no session id");
      ready = true;
      observed = configuredDshRoute(created?.configOptions, route.requested, route.configured, route.overlay_sha256);
    } else {
      try {
        const resumed = await connection.call("session/resume", { sessionId, cwd: request.workspace, mcpServers: [] });
        ready = true;
        observed = configuredDshRoute(resumed?.configOptions, route.requested, route.configured, route.overlay_sha256);
      } catch (error) {
        throw new Error(`DSH ACP session/resume was refused: ${error.message}`);
      }
    }
    const result = await connection.call("session/prompt", { sessionId, prompt: [{ type: "text", text: request.prompt }] });
    if (result?.stopReason !== "end_turn") throw new Error(`DSH ACP prompt stopped with ${result?.stopReason ?? "no stop reason"}`);
    const output = connection.output();
    if (!output.trim()) throw new Error("DSH ACP operation returned no assistant output");
    return {
      session_id: sessionId,
      output,
      stop_reason: result.stopReason,
      route_requested_provider: route.requested.provider,
      route_requested_model: route.requested.model,
      route_configured_provider: route.configured.provider,
      route_configured_model: route.configured.model,
      route_observed_provider: observed.observed.provider,
      route_observed_model: observed.observed.model,
      route_overlay_sha256: route.overlay_sha256,
      route_observation_source: resume
        ? "session/resume.configOptions[model].currentValue"
        : "session/new.configOptions[model].currentValue",
      route_observed_value: observed.currentValue,
    };
  } finally {
    if (ready && !connection.failed()) {
      try {
        await connection.call("session/close", { sessionId });
      } catch {
        // A close-stage failure must not replace the operation result.
      }
    }
    await connection.stop();
  }
}

async function opencode(request, sdk) {
  if (request.operation !== "history" && request.approval !== "unattended" && request.approval !== "deny_unapproved") {
    throw new Error("OpenCode SDK requires explicit approval mode");
  }
  const permission = request.approval === "unattended"
    ? "allow"
    : { "*": "deny", read: "allow", glob: "allow", grep: "allow" };
  const owned = await sdk.createOpencode({
    hostname: "127.0.0.1",
    port: await choosePort(),
    config: { permission },
  });
  try {
    const client = owned.client;
    let sessionId;
    if (request.operation === "fresh") {
      const created = unwrap(await client.session.create({ body: { title: "Praxis SDK handoff" } }));
      sessionId = created?.id ?? "";
      if (!sessionId) throw new Error("OpenCode SDK did not return the new session id");
    } else {
      if (request.operation === "resume" && request.session_owner !== "operator_owned") throw new Error("OpenCode continuation requires operator-owned session confirmation");
      sessionId = request.session_id;
      const current = unwrap(await client.session.get({ path: { id: sessionId } }));
      const directory = current?.directory ?? current?.workspace ?? "";
      if (directory && directory !== request.workspace) throw new Error("OpenCode session workspace differs from the selected workspace");
    }
    if (request.operation === "history") {
      return { session_id: sessionId, output: JSON.stringify(unwrap(await client.session.messages({ path: { id: sessionId } }))) };
    }
    const body = { parts: [{ type: "text", text: request.prompt }] };
    if (request.model) {
      const split = request.model.indexOf("/");
      if (split <= 0 || split === request.model.length - 1) throw new Error("OpenCode model must use provider/model format");
      body.model = { providerID: request.model.slice(0, split), modelID: request.model.slice(split + 1) };
    }
    const response = unwrap(await client.session.prompt({ path: { id: sessionId }, body }));
    const output = textFrom(response);
    if (!output.trim()) throw new Error("OpenCode SDK operation returned no assistant output");
    return { session_id: sessionId, output };
  } finally {
    await owned.server.close();
  }
}

export async function invoke(request, sdk) {
  switch (request.harness) {
    case "amp": return amp(request, sdk);
    case "cline": return cline(request, sdk);
    case "codex": return codex(request, sdk);
    case "droid": return droid(request, sdk);
    case "dsh": return dsh(request, sdk);
    case "opencode": return opencode(request, sdk);
    default: throw new Error("Unsupported TypeScript SDK harness");
  }
}
