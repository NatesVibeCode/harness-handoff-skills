# Harness control and ABAC

Status: access-profile governance added 30 September 2026. ABAC governs bridge
projection, fresh launch, continuation, review, and saved settings. Saved launch
settings for Codex, Muse and Claude are implemented in this checkout. Native approval-hook
integration, native global settings and running-session settings are not implemented.
No host configuration or policy is installed by this change.

Start with [access profiles, products, and harness settings](access-profiles.md)
for the product/access boundary, native control map, and governance coverage.
An access profile is separate from a saved launch-settings profile.
Fresh execution uses [resolved launch plans](launch-plans.md), including the
policy labels, executable pins and SDK boundary described there.

## Ownership

| Component | Responsibility |
| --- | --- |
| `agent-orient` / `repo-discover` | Find repositories, identities, ownership and reuse candidates within selected roots. Discovery does not grant access. |
| ABAC | Pure policy evaluation: attributes to allow/deny, policy reference and guidance. |
| Trusted local host | Authenticate caller, bind operator grants to sessions and resources, invoke policy, enforce decisions and retain receipts. |
| `harness-handoff` | Native adapters, supported settings contracts, launch and handoff. |
| Native harness controls and sandbox | Enforce approval outcomes and bound actual file, process and network access. |

Keep shared policy in ABAC and adapter-specific mechanics here. Do not recreate
this control system inside Forge or an old Atom Forge checkout. Repo discovery
should identify the selected canonical owner before edits are dispatched.

## Available commands

From this checkout:

```sh
python3 scripts/harness-control describe
python3 scripts/harness-control profiles --harness codex --repo work
python3 scripts/harness-control get --harness codex --profile build --repo work
python3 scripts/harness-control plan --changes changes.json
python3 scripts/harness-control apply --changes changes.json --expected-digest DIGEST_FROM_PLAN
```

The MCP bridge exposes the same operations as `settings_describe`, `settings_profiles`, `settings_get`,
`settings_plan` and `settings_apply`. `handoff_fresh(..., settings_profile="build")`
uses the saved profile through the existing CLI contract and separately evaluates
permission to use each setting for that launch. Profile use requires an explicitly
selected workspace. It cannot be combined with the existing model or approval
override arguments. Codex profiles must contain both `sandbox` and `approval`.

Codex model/effort pairs also undergo the portable
[capability preflight](../codex-harness-handoff/references/model-and-settings.md)
before child execution. A profile with `reasoning_effort` must name `model`.
MCP `handoff_fresh` accepts `model_capabilities` to point at fresh native model
metadata, including when using a saved profile. Outside profiles, the Codex CLI
route also accepts an explicit `reasoning_effort` with `model`. Profile receipts
retain `requested_settings`; CLI model receipts distinguish requested argv,
capability validation, and native runtime observations. Existing profile
`effective_settings_verified` remains false for the entire profile because
sandbox/approval runtime enforcement is not observed. Capability compatibility
and ABAC permission are separate checks; capability evidence grants no authority.

`plan` evaluates up to 64 explicitly named profiles, returning before/after values,
policy verdicts and a digest. `apply` reevaluates policy and checks that digest
against the current host, evaluator, contracts, policies and state. It publishes
the batch in one atomic profile-store replacement under a short, nonblocking
publication gate. Policy subprocesses run before that gate. Contention returns
immediately; the caller continues independent work and may later create a fresh
plan. This gate never claims a repository, file section or task. A denied target
prevents the whole batch from applying. To proceed with an
independent allowed subset, submit an explicit new plan for that subset.

The digest binds an exact change; it is not a human-approval requirement. A trusted
host can plan and apply automatically within the operator's existing grant.
It must never invent broader authority to make a denied plan succeed.

This updates saved launch profiles only. Existing sessions and native global
configuration are untouched. Receipts explicitly report that runtime effective
settings have not been observed. Native defaults can still matter: a false Muse
boolean omits its override flag; it does not force the opposite native setting.
The capability catalog's effort values describe CLI syntax, not a promise that
each model supports each value.

Example `changes.json` (values are requests, not grants):

```json
[
  {"harness":"codex","profile":"build","repo":"work",
   "settings":{"model":"gpt-6-luna","reasoning_effort":"max",
               "sandbox":"workspace-write","approval":"on-request"}},
  {"harness":"claude","profile":"review","repo":"work",
   "settings":{"permission_mode":"plan"}}
]
```

## Host configuration

Build the companion ABAC checkout with `go build -o /absolute/path/abac ./cmd/abac`.
The added `evaluate` command accepts native Request JSON, including action
operations and host-attested labels; it does not authenticate JSON by itself.

The host sets `HARNESS_CONTROL_CONFIG` to an absolute, protected JSON file:

```json
{
  "schema":"harness.control_host.v2",
  "abac_binary":"/absolute/path/abac",
  "policy_files":["/absolute/path/control-policy.json"],
  "subject":{"principal_ref":"authorized-session-principal","altitude":"run"},
  "access_context":{"product_ref":"PRODUCT_REF","permission_context":"ACCESS_PROFILE_REF","realm":"DEPLOYMENT_REF"},
  "repositories":{
    "work":{"path":"/absolute/path/canonical-work-repo","status":"active"}
  },
  "state_file":"/absolute/path/launch-profiles.json"
}
```

Repository IDs come from this host map, not folder-name inference. The host must
bind the subject to the actual session and its operator grant. Do not share one
privileged subject configuration across workers with different authority. Roles
are optional. The host configuration, evaluator, policy and adapter code must be
outside worker write access. The profile store should be writable only through
the trusted host.

Requests use resource kind `data`, owner `harness-handoff`, ref
`harness-settings/<harness>/<profile>`; labels `harness`, `repo_id`, canonical
`repo_path`, and `repo_status`. Per-setting decisions also include `setting` and
`value`, where value is JSON encoded (a string retains its JSON quotes).

All requests also carry trusted `product_ref`, `permission_context`, and `realm`
from the required v2 host `access_context`. Governance actions use
`a2a.agent / harness-handoff/<harness>`, owner `harness-handoff`, with
`handoff.project` (read), `handoff.launch` (spawn), and `handoff.continue`
(dispatch). History uses `data / harness-session-review`, `handoff.review`
(read). The environment altitude is `run`. The host supplies these attributes;
the model cannot select an access profile through launch arguments.

| Operation | Verb | Evaluated before |
| --- | --- | --- |
| `settings.get` | `read` | Returning existing profile settings |
| `settings.apply` | `write` | Saving each requested setting |
| `handoff.launch_settings` | `spawn` | Using each effective setting at launch |

Policies should constrain the subject, exact repository, harness, profile,
operation, setting and allowed value as appropriate. Reading settings must not
implicitly authorize launching. Model changes must not implicitly authorize
sandbox bypass or permission changes. Prefer allow rules restricted to active
repositories; frozen or superseded repositories need independent authority for
writes. The default ABAC result is deny. Author guidance on explicit deny rules
so a refused action explains the exact missing authority.

Example narrow read grant, intentionally granting neither writes nor launches:

```json
{
  "schema":"abac.policyfile.v1",
  "policies":[{
    "id":"read-work-build-profile","effect":"allow","priority":10,
    "scope":{
      "subject.principal":"authorized-session-principal",
      "resource.kind":"data",
      "resource.ref":"harness-settings/codex/build",
      "resource.labels.repo_id":"work",
      "action.verb":"read",
      "action.operation":"settings.get"
    }
  }]
}
```

## Native approvals: next integration

### Implemented: optional Jev interpretation for settings

`python3 scripts/harness-control resolve --request request.json` and the async
MCP tool `settings_resolve(request)` resolve settings ambiguity within one
explicit harness/profile/repository. They return a normal digest-bound plan or
a focused question; neither executes anything. Native tool-approval callbacks
remain a separate adapter integration.

The structured settings request contains `harness`, `profile`, `repo`, `intent` (up to 4096
characters), and one to eight `candidates`. Each candidate has a unique `id`,
validated `settings`, and `evidence` (up to 4096 characters). Example:

```json
{
  "harness":"codex", "profile":"build", "repo":"work",
  "intent":"Use the stronger reasoning setting we discussed.",
  "candidates":[
    {"id":"high","settings":{"reasoning_effort":"high"},
     "evidence":"The earlier explicit setting was high."},
    {"id":"max","settings":{"reasoning_effort":"max"},
     "evidence":"A later message mentioned max without choosing it."}
  ]
}
```

The trusted host/adapter owns candidate construction and source attribution.
Model-authored evidence is not an authority statement. All interpretations stay
within the already selected target. The resolver checks reads and each candidate
setting with ABAC first. A single distinct settings interpretation returns a
normal plan or denial without Jev. Mixed interpretations may use the optional
reviewer to establish what was intended, even when some candidate actions are
denied. The selected action is checked again: Jev cannot convert that denial to
permission. A denied concrete action includes a recovery task to propose a
distinct alternative, which requires its own ABAC decision before execution.

### Catch-all recovery

Use `python3 scripts/harness-control recover --request request.json` or async
MCP `control_recover(request)` when there is no clean candidate list: unclear
intent, missing context, conflicting evidence, unsupported input, or a denied
action needing alternatives. Supply the selected `harness`, `profile`, `repo`
and `intent`; additional bounded fields are context, not permission attributes.
The whole request is limited to 32 KiB. `settings_resolve` also routes unsupported
interpretation shapes here when the target and intent can be identified.
`resolve` and `recover` exit successfully for valid structured outcomes,
including denial, recovery, contention and needs-input; callers branch on
`status` instead of blindly retrying a nonzero process exit. Malformed input or
host/evaluator errors still exit nonzero. A busy journal requests no human input.

Jev can choose `gather_context`, `clarify_request`, `propose_alternative`, or
`request_authority`. This advisory route does not use the numeric confidence
threshold needed to select a concrete settings plan. It returns a task for the
current harness; no additional agent is launched. Each returned task asks for
one authorized step, then resubmission to ABAC or the recovery router. A private
SQLite journal beside the profile store issues at most three continuations in
five minutes for the same host-attested principal, canonical target and original
intent. Changed failure text or coordination claims do not reset it. Expired or
exhausted episodes return `needs_input`, no task, and no automatic restart.
Contention returns `recovery_busy` without waiting. Transactions close before any
provider call. Normal deterministic operations and unrelated episodes remain
available. The journal contains opaque episode IDs, deadlines and counters,
never file ownership, claims, assignments, dependencies or wait-for edges.

The host must retain the original intent and its session/task identity across
retries. A genuinely new task gets a new host-attested task principal or intent;
the router does not offer an agent-controlled reset. Changing arbitrary caller
text cannot establish new authority. Direct worker access to the journal is
outside the trusted boundary; protect its directory like the profile store.
This bounds issuance by this router, not arbitrary tool calls by an unrestricted
agent. Native enforcement remains a separate integration.

On reviewer failure, deterministic routing supplies the same recovery task:
unsupported shapes get clarification, reported policy denials get alternative
proposals, and other ambiguity gets context gathering. Only missing authority
requires escalation. A proposal never authorizes execution or silently replaces
an explicitly selected operator action. The normal authority gate still applies
to every read, tool call and resulting action. The host must attest evidence and
failure information before treating them as facts; caller labels are advisory.

Host configuration can opt in with this optional member:

```json
"jev_review": {
  "enabled": true,
  "key_env": "OPENROUTER_API_KEY",
  "model": "typesafe/jev-1.13",
  "timeout_ms": 3000,
  "min_confidence": 0.95
}
```

This is not enabled or installed automatically. ABAC must separately allow
`action.operation=ambiguity.review`, verb `call`, for the selected target and
`setting=model`, `value` equal to the JSON-encoded configured model. That grant
also authorizes sending the intent and candidate evidence to the fixed
OpenRouter Decisions endpoint. Do not include credentials or unrelated context.
The wire shape reuses the existing local Jev Decisions client contract; the new
adapter has not yet been exercised against the provider.

Jev receives finite choice criteria and an `unresolved` choice. It has no tools,
cannot gather additional files, change settings, issue grants or invent a new
target. Only a typed answer with a complete finite probability distribution and
confidence meeting the configured floor can select a candidate. The original
validated settings, not model-returned settings, are used to build a fresh ABAC
plan. The subsequent `apply` still rechecks policy and the exact plan digest.

**Deterministic behavior has no Jev dependency.** Disabled review, missing keys,
invalid reviewer configuration, HTTP errors (including exhausted spend or
expired keys), timeouts, malformed responses and inconclusive evidence return
`needs_recovery` with a deterministic task. The operator question is retained
as a fallback after bounded recovery, not an immediate mandatory interruption.
Existing `get`, `plan`, `apply`, and
launch-policy checks do not load credentials, import the reviewer, or call the
provider. A failed ABAC evaluator still refuses protected actions: Jev cannot
replace the deterministic authority check.
Only interpretation validation enters the catch-all. Host configuration errors,
policy failures and stale bindings retain their original refusal instead of
being relabeled ambiguous. Missing unrelated repositories do not stop work on a
valid selected repository; canonical paths are included in the host binding.

One subprocess makes one HTTPS request with no retries, redirects or inherited
proxy settings. The parent kills it at the configured total deadline (default
3 seconds, maximum 5). Input/output are capped at 64 KiB. Provider failure opens
a 60-second circuit breaker in the current host process; concurrency is limited
to one review and six attempts per minute. Separate CLI invocations have separate
process-local counters; these are not durable account-wide spend quotas. A timed
out remote request may already have incurred provider cost. Persistent spend
budgets belong to the trusted host/provider account policy.

The async MCP wrapper runs review off its event loop. Unrelated deterministic
work continues. Fresh-handoff profile preparation is also run off the event
loop. Receipts retain the request digest, host/state binding, per-key
ABAC decisions and typed reviewer response. Provider error bodies and keys are
not retained. These remain ordinary receipts, not signed authorization tokens.

Desired path:

```text
Native approval request
  -> adapter normalizes exact action and resource
  -> trusted host supplies session identity and existing grant
  -> in-memory ABAC evaluation
     -> allow: answer the native request automatically
     -> deny with existing hard boundary: refuse, give guidance
     -> missing authority eligible for escalation: one scoped operator question
  -> bind response and receipt to the exact native request
```

ABAC currently returns allow/deny. Escalation is a host workflow; an ambiguous
request is never converted to allow. A user-approved exception creates a narrow,
expiring grant through the trusted host, not a rewrite initiated by the worker.
Keep the native sandbox enabled and retain controls for paths, credentials,
network destinations and external writes separately. A generic shell approval
does not establish the safety of arbitrary child programs. Requests that cannot
be bounded need a narrower command adapter, sandbox, or human decision.

The current authored Muse guide describes answering approvals through the
owning MSP client and changing session approval mode on the wire. It also says
host sandbox posture is fixed for the host lifetime. This makes Muse a candidate
for the first owned-session approval adapter. Exact request/response schema,
timeouts, cancellation, replay binding and enforced behavior still need evidence.
Codex/Claude launch settings are documented here, but this implementation has
not established a generic approval callback for their CLI routes. Unsupported
hooks must remain explicit; do not use terminal auto-clicking or permission
bypass as a substitute. Any new protocol route must respect the selected
skill's session and transport restrictions.

### Session-speed requirements (proposed, not measured)

- Keep the evaluator loaded inside the host; `Store.Evaluate` uses validated,
  ordered policy in memory. Avoid a subprocess, provider call or remote round
  trip for each tool request. The present CLI subprocess is only the settings
  control implementation, not the desired per-tool fast path.
- Target under 10 ms p95 added local decision latency, measured from native
  request receipt to response submission. Track p99 and receipt overhead too.
- Evaluate exact actions cheaply before introducing decision caches. If caching
  is needed, bind entries to subject, grant, action, canonical resources, argument
  digest, policy version and expiry. Never reuse a stale grant after revocation.
- Reload policies atomically and before `Store.ReloadBefore()` expires. An
  unhealthy evaluator pauses protected actions; it never disables controls.
- Do not ask again for an action already covered by an unchanged grant. Show
  routine receipts in a quiet summary; interrupt only when user input is needed.
- Continue independent authorized work while one request needs more authority.
- Native permissions that pre-approve an action must be no broader than ABAC's
  effective grant, or they can skip the callback entirely.

### Ordered rollout

1. Recover discovery and record canonical ownership, frozen/superseded state and
   missing metadata across operator-selected roots. Keep visibility distinct
   from read and edit permissions; private repo existence may itself be gated.
2. Adopt saved profiles and explicit ABAC grants for a selected host. Capture
   before/after receipts and verify effective native settings before expanding.
3. Implement one native approval adapter in an owned session, then measure allowed
   work, denied work, missing authority, cancellation, revocation and latency.
4. Add more adapters behind an explicit capability matrix. Add bulk native
   settings only where supported, with per-target preflight, rollback limits and
   honest partial-result receipts. No global cross-harness transaction is assumed.

## Present enforcement limits

ABAC governance is engaged when `HARNESS_CONTROL_CONFIG` is selected. It then
gates bridge projection, fresh launch (including omitted `settings_profile`),
continuation, history, and settings. Missing or malformed v2 host configuration
fails closed. Without a selected config, portable native handoff retains its
existing operator-authorized behavior and makes no ABAC enforcement claim.
Direct CLI use, other local clients and arbitrary shell/filesystem operations
remain outside this module. Do not present it as universal repo access control.
No current full-access worker was retroactively sandboxed by these changes.

An unrestricted same-user worker can rewrite configuration or invoke a native
CLI directly. A real security boundary requires a separately protected host and
native/OS enforcement. File hashes and plan digests detect configuration drift;
they are not authentication, signatures or tamper-proof audit storage. The
current ABAC verdict is JSON, not a signed execution receipt. Credential routing,
per-session host identity, grant lifecycle and durable audit storage remain
host integration work.

## Coordination boundary

Presence and change notifications can inform an agent; they never grant or deny
access, reserve a section, or make another agent the permission authority. A
real edit collision is evidence that the base content changed. Read that exact
change and reconcile the affected operation. Do not negotiate ownership of
sections, wait on informal claims, or automatically undo another session's work.
The existing `work-coordination` project already owns advisory observations;
this module adds no coordination manager or claims protocol.
