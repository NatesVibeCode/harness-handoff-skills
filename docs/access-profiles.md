# Access profiles, products, and harness settings

ABAC is the authorization owner. A trusted host supplies identity and access
context; ABAC decides whether a capability may be projected and whether the
requested action may occur. Native adapters enforce the resulting execution.

Keep these three layers separate:

| Layer | Owner and selection | What it governs |
| --- | --- | --- |
| Product access profile / permission context | Trusted product host, evaluated by ABAC | Principal, roles, scope, product/realm, resources and permitted actions |
| Saved harness launch settings | Explicit `settings_profile` in this bridge, scoped by harness and repository | Model, reasoning effort and product-specific native controls |
| Native named configuration | Native product, explicitly selected where supported | Native configuration layering; Codex uses `native_profile` → `--profile` |

AO-FL-A is a Fact Lens access context. It is not a global Codex, Muse, or Claude
launch profile, nor an automatic grant. The existing ABAC Fact Lens policy
binds AO-FL-A to a named FL principal, role, altitude and OE run resource.
Those rules do not authorize harness launches simply because a caller supplies
that name. The corresponding harness resource and action must also be allowed
by the selected ABAC policy set.

## One access profile can govern one or several harnesses

Use the host's required `access_context` in
[`harness.control_host.v2`](harness-control.md#host-configuration):

```json
{
  "product_ref": "PRODUCT_REF",
  "permission_context": "ACCESS_PROFILE_REF",
  "realm": "DEPLOYMENT_REF"
}
```

The profile definition/rules stay in the host-selected ABAC `policy_files`.
The product reference, permission context and realm become resource labels on
every settings and handoff request. The worker cannot supply these labels,
roles or principal through MCP arguments. A reference alone is not trusted
identity. Protect the host configuration, policy files, evaluator and execution
boundary from worker writes.

A policy may allow several exact harness resources under one access context,
or separate access contexts may each allow one harness. There is no forced
one-profile-per-harness rule and no automatic AO-FL-A default. Product access
context is never inferred from the active model, harness, workspace name or
transport. A host configuration binds one trusted context; another context
uses its own explicitly selected host configuration.

Policy files can declare their `realm` to isolate consumers. The existing ABAC
loader injects that namespace into every rule; intentionally shared base files
use `realm: "*"`. Keep this behavior in ABAC rather than duplicating it here.

## Implemented governance doors

| Bridge surface | ABAC question before use |
| --- | --- |
| `list_harnesses`, `get_contract`, `settings_describe` | `handoff.project`; unavailable harnesses are omitted or return a bland refusal |
| `handoff_fresh` on CLI or SDK, with or without saved settings | `handoff.project`, then `handoff.launch` |
| `handoff_continue` on CLI or SDK | `handoff.project`, then `handoff.continue`, with the exact session ID |
| `session_history` | `handoff.project`, then `handoff.review`, with the exact session ID |
| `settings_profiles`, `settings_get` | `settings.get` for each selected saved profile |
| `settings_plan`, `settings_apply` | `settings.get`, then `settings.apply` for every changed setting |
| Saved settings at dispatch | `settings.get`, then `handoff.launch_settings` for every selected setting |

Execution/history requires an existing absolute workspace that matches exactly
one host-owned repository mapping. Discovery checks product-level projection
without guessing a repository; the three discovery tools also accept an explicit
`workspace` when projection rules are repository-specific. The governance gate preserves the selected
product/access context, harness, workspace, session identity and native settings
profile. Direct overrides are resource labels `requested_model`,
`requested_reasoning_effort`, `requested_approval`, `requested_use`; each value
is JSON encoded, including quotes around strings and `null` for omitted values.
These labels let access-specific rules constrain ad hoc launches. Omission of a
saved settings profile does not omit the launch governance gate.

Fresh launch decisions also receive the [resolved launch plan](launch-plans.md):
actual adapter, executable, canonical workspace and emitted native settings.
Policies can constrain these resolved values even when the caller selected `auto`.

CLI effects and SDK effects recheck policy immediately before dispatch. A
changed host, policy set, workspace identity, selected settings or final deny
refuses the action. No new session, native default, different model or alternate
harness is substituted after refusal. The receipt retains request digests,
ABAC verdicts and policy digests, plus host/profile/argument bindings. These
prove what was checked; native effective settings still require observation.

## Current native settings adapters

Saved launch profile names are user-defined; `build` under Codex does not
select `build` under another harness. Inventory is explicitly scoped:

```sh
python3 scripts/harness-control profiles --harness codex --repo REPO_ID
python3 scripts/harness-control profiles --harness muse --repo REPO_ID
python3 scripts/harness-control profiles --harness claude --repo REPO_ID
```

`settings_profiles(harness, repo)` is the MCP equivalent. It lists only profiles
the caller may read, and does not reveal names or values of denied profiles.

| Adapter | Supported saved native controls |
| --- | --- |
| Codex | `native_profile`, `model`, `reasoning_effort`, `sandbox`, `approval` |
| Muse | `model`, `reasoning_effort`, `disable_approval`, `disable_sandbox`, `trust_workspace` |
| Claude Code | `model`, `reasoning_effort`, `permission_mode` |
| Other eleven harnesses | ABAC handoff governance is implemented; saved native settings adapters are not yet implemented |

Control definitions remain in [`skills-src/settings.json`](../skills-src/settings.json).
Foreign controls are refused rather than translated. Codex saved profiles must
explicitly select sandbox and approval. False Muse booleans omit flags; this does
not prove an effective false value in native configuration. SDK saved-profile
application is unimplemented and refused; ordinary SDK launches still pass the
access governance gate. Profile argument and settings digests are rechecked
before CLI dispatch.

## Installation and limits

Setting `HARNESS_CONTROL_CONFIG` engages this bridge's ABAC gates. Missing,
invalid or old host configuration refuses protected operations; v2 requires an
explicit access context and uses `harness-handoff` as the settings resource owner
and `run` as the governing environment altitude. Update old host configurations
and their rules deliberately; there is no implicit profile or schema migration.
With no configuration selected, this remains the portable native handoff adapter
under the operator's existing authorization, and makes no claim of ABAC governance.

This implementation gates this bridge's interfaces. Direct shell/CLI use,
`scripts/codex-task-bridge`, Go session clients, standalone session-review scripts,
and child tool calls still require their own trusted host/native enforcement.
It does not retrofit every process on the machine. No FL policy, live product
access profile or global harness configuration is changed by this implementation.
