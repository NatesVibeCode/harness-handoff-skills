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
  const options = { cwd: request.workspace, ...request.settings };
  let sessionId = "";
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

async function cline(request, sdk) {
  const coreFactory = sdk.ClineCore;
  if (!coreFactory || typeof coreFactory.create !== "function") throw new Error("ClineCore SDK entrypoint unavailable");
  const policies = request.settings.toolPolicies;
  const provider = request.settings.provider_id;
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
      // The Process also selects the response to unmatched approval requests.
      requestToolApproval: async () => ({ approved: request.settings.unmatched_tool_approval === "approve" }),
    },
  });
  try {
    const session = await clineRuntime.start({
      prompt: request.prompt,
      interactive: false,
      config: {
        providerId: provider,
        modelId: request.settings.model,
        apiKey: process.env[apiKeyEnv],
        cwd: request.workspace,
        workspaceRoot: request.workspace,
        enableTools: request.settings.enableTools,
        enableSpawnAgent: request.settings.enableSpawnAgent,
        enableAgentTeams: request.settings.enableAgentTeams,
      },
      toolPolicies: policies,
    });
    if (session.result?.finishReason !== "completed") throw new Error("Cline SDK did not return a completed result");
    return { session_id: session.sessionId, output: textFrom(session.result) };
  } finally {
    await clineRuntime.dispose("SDK operation complete");
  }
}

async function codex(request, sdk) {
  if (request.operation !== "fresh") throw new Error("Codex SDK route supports fresh sessions only");
  const codexClient = new sdk.Codex();
  const thread = codexClient.startThread({ workingDirectory: request.workspace, ...request.settings });
  const turn = await thread.runStreamed(request.prompt);
  let output = "";
  let completed = false;
  for await (const event of turn.events) {
    if (event.type === "thread.started") {
      console.error(JSON.stringify({ harness: "codex", event: event.type, session_id: event.thread_id }));
    } else if (event.type === "item.completed" && event.item.type === "agent_message") {
      output = event.item.text;
      console.error(JSON.stringify({ harness: "codex", event: "assistant_output", session_id: thread.id, text: output }));
    } else if (event.type === "turn.completed") {
      completed = true;
    } else if (event.type === "turn.failed" || event.type === "error") {
      throw new Error(event.error?.message ?? event.message ?? "Codex SDK turn failed");
    }
  }
  if (!completed) throw new Error("Codex SDK stream ended without successful completion");
  const sessionId = typeof thread.id === "string" ? thread.id : "";
  if (!sessionId) throw new Error("Codex SDK did not expose the fresh thread id");
  if (typeof output !== "string" || !output.trim()) throw new Error("Codex SDK completed without assistant output");
  return { session_id: sessionId, output };
}

async function droid(request, sdk) {
  const { ToolConfirmationOutcome } = sdk;
  const { permission, transport: transportMode, ...settings } = request.settings;
  const permissionHandler = permission === "unattended"
    ? undefined : () => ToolConfirmationOutcome.Cancel;
  const ownedTransport = transportMode === "native_stdio"
    ? new sdk.ProcessTransport({ cwd: request.workspace, env: process.env }) : undefined;
  let sessionId = "";
  let output = "";
  let failed = false;
  let completed = false;
  try {
    if (ownedTransport) await ownedTransport.connect();
    const session = await sdk.createSession({ cwd: request.workspace, ...settings, permissionHandler,
      ...(ownedTransport ? { transport: ownedTransport } : {}) });
    sessionId = session.id;
    try {
      for await (const message of session.stream(request.prompt)) {
        if (message?.type === "assistant" && typeof message.text === "string") output += message.text;
        if (message?.type === "error") failed = true;
        if (message?.type === "result") {
          completed = true;
          if (message.success !== true) failed = true;
        }
      }
    } finally {
      await session.close();
    }
  } finally {
    if (ownedTransport) await ownedTransport.close();
  }
  if (failed || !completed) throw new Error("Droid SDK turn returned no successful terminal result");
  if (!output.trim()) throw new Error("Droid SDK operation returned no assistant output");
  return { session_id: sessionId, output };
}

async function opencode(request, sdk) {
  const { permission, model } = request.settings;
  const owned = await sdk.createOpencode({
    hostname: "127.0.0.1",
    port: await choosePort(),
    config: { permission },
  });
  try {
    const client = owned.client;
    const directory = request.workspace;
    const created = unwrap(await client.session.create({ query: { directory }, body: { title: "Praxis SDK handoff" } }));
    const sessionId = created?.id ?? "";
    if (!sessionId) throw new Error("OpenCode SDK did not return the new session id");
    const body = { parts: [{ type: "text", text: request.prompt }], model };
    const response = unwrap(await client.session.prompt({ path: { id: sessionId }, query: { directory }, body }));
    if (response?.info?.error) throw new Error("OpenCode SDK returned an assistant error");
    const output = textFrom(response);
    if (!output.trim()) throw new Error("OpenCode SDK operation returned no assistant output");
    return { session_id: sessionId, output };
  } finally {
    await owned.server.close();
  }
}

export async function invoke(request, sdk) {
  if (request.operation !== "fresh") throw new Error("SDK Node supports fresh operations only");
  const operation = { amp, cline, codex, droid, opencode }[request.harness];
  if (!operation) throw new Error("Unsupported TypeScript SDK harness");
  const result = await operation(request, sdk);
  if (typeof result?.session_id !== "string" || !result.session_id.trim() ||
      typeof result.output !== "string" || !result.output.trim()) {
    throw new Error("SDK completed without a session identity or assistant output");
  }
  return result;
}
