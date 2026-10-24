import net from "node:net";

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
    case "opencode": return opencode(request, sdk);
    default: throw new Error("Unsupported TypeScript SDK harness");
  }
}
