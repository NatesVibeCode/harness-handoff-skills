# Codex model and launch settings

This reference is the portable entrypoint for launching an already selected
model. Copy the entire `codex-harness-handoff/` folder, including its bundled
`model_settings.py`, `settings.json`, and `references/`. All local links are
relative; no private service, checkout, or username is required.

## Exact settings and native syntax

The [bundled catalog](../settings.json) is generated from the repository's
`skills-src/settings.json`. In a full checkout,
`python3 scripts/harness-control describe` or MCP `settings_describe` exposes
the same setting definitions. Those commands describe syntax; model support
must be checked separately. Keep model, provider, native harness authentication,
workspace, and permission posture separate.

Check `codex --version` and `codex exec --help` in the selected execution context.
For an explicit model and supported effort, insert these arguments into the
authorized fresh launch recipe, before its stdin prompt marker:

```sh
--model MODEL_ID -c 'model_reasoning_effort="EFFORT"'
```

Replace both placeholders with exact operator-selected values. This fragment
does not select a sandbox or approval posture. Omit model/effort flags when
the operator selected native defaults. Do not guess a latest model, translate
model names between products, or copy Responses API parameters into CLI argv.

## Read-only capability validation, including pointable evidence

Run the bundled helper before dispatch. `SKILL_DIR` means the location where
the portable skill folder was installed; set it in your shell:

```sh
python3 "$SKILL_DIR/model_settings.py" --model MODEL_ID --reasoning-effort EFFORT
python3 "$SKILL_DIR/model_settings.py" --model MODEL_ID --reasoning-effort EFFORT \
  --capabilities /absolute/path/to/model-capabilities.json
```

The preflight helper makes no network calls, launches no worker, and reads no
conversation history. By default it reads native `models_cache.json` under `CODEX_HOME` or
the current user's `.codex` directory. `--capabilities` points to a caller-selected
file with the same native shape; it avoids dependence on a particular machine.
The MCP `handoff_fresh` equivalent is `model_capabilities="/absolute/path/..."`.
This is a file pointer, not a URL; fetch official evidence separately if needed.

Required shape (placeholders are illustrative, not live model evidence):

```json
{
  "fetched_at": "UTC timestamp from native metadata",
  "client_version": "installed Codex version",
  "models": [{
    "slug": "EXACT_MODEL_ID",
    "supported_reasoning_levels": [{"effort": "high"}]
  }]
}
```

Evidence must be at most 24 hours old, not future-dated, and contain exactly one
matching model. An explicit effort requires an explicit model and support in
that model's reasoning levels. Stale, missing, malformed, or unsupported evidence
refuses the pair before execution. A model-only request without a supplied file
may pass through with `status: unknown`; the native CLI still resolves access.
Omitted overrides return `status: inherited`, with no claimed default value.
Never manufacture timestamps or add a requested effort to make validation pass.
Native caches are version-specific; an unfamiliar shape requires refreshed
evidence. A hash binds the checked bytes but does not authenticate their source
or prove account access. Retain the evidence in the authorized execution context;
do not publish a private cache, identity metadata, or session transcript.

For the CLI bridge, `handoff_fresh("codex", ..., use="cli", model="MODEL_ID",
reasoning_effort="EFFORT", model_capabilities="/absolute/path/...")` validates
the rendered launch before starting the child. Saved profiles use the same
preflight; profiles with an effort must also name the exact model. The bridge's
SDK route does not implement this preflight and refuses these options.

## When official documentation is needed

Use current [Codex configuration documentation](https://developers.openai.com/codex/config-reference)
and [CLI reference](https://developers.openai.com/codex/cli/reference) for changed
flags/configuration, and the [model catalog](https://developers.openai.com/api/docs/models)
for a model-specific capability gap. Open the exact model page; API availability
does not establish availability through the current Codex account/provider.
The [reasoning guide](https://developers.openai.com/api/docs/guides/reasoning)
explains why effort support varies by model. These links were checked on
2026-09-30; they are refresh pointers, not frozen promises about every model.

An installed OpenAI Docs skill can perform that lookup, but is optional. Current
capability evidence plus installed CLI help is enough for routine exact-model
launch mechanics. Pricing, comparative recommendations, current limits, and
migration still require their current official documentation.

## Receipt: requested, validated, observed

Retain the selected workspace, route, native execution/session handle, exact
model/effort request, capability status/source hash/time, terminal result, and
artifact checks. The CLI bridge reports `model_preflight` plus `model_settings`:
`requested` comes from rendered argv; `observed` comes only from native
`turn_context` metadata actually emitted by the owned execution. The bridge
checks the fresh thread's journal by its returned UUID and confirms its
`session_meta` identity before reading turn metadata. It never reads unrelated
session contents. If that owned journal is unavailable, it checks the CLI JSON
stream. Assistant prose,
argv, a saved profile, and a successful exit are not observed effective settings.
If neither native source provides that metadata, `observed` is empty and
`effective_settings_verified` stays false. A partial observation stays partial;
compare only fields actually observed. A mismatch leaves verification false and
`matches_request: false`; do not claim a successful launch configuration or
silently change/retry the target. Never infer a model from the sender.

## ABAC boundary

In a full checkout, see [harness control](../../docs/harness-control.md) for saved
profiles and ABAC integration. That link is optional when installing only this
skill; the portable launch workflow above needs no ABAC service. ABAC decides
whether an authenticated caller may use a setting for the selected workspace.
The configured bridge also gates projection, launch, continuation and history
through a trusted product access context, separately from its saved settings
profile. See the optional [access-profile map](../../docs/access-profiles.md).
Capability preflight decides whether current evidence supports the exact
model/effort pair. Native controls enforce the child execution. A capability
file grants no authority and an ABAC allow does not prove model compatibility.
