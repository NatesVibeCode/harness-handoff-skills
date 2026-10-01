# Resolved launch plans

Fresh bridge launches resolve one private, immutable `LaunchPlan`. ABAC approves
that exact plan, and the CLI or SDK executor consumes it. Route, executable,
workspace and native options are not chosen again after approval.

The flow is:

1. Check `handoff.project` using the trusted host's access context.
2. Select the supported adapter and resolve the executable, canonical workspace,
   native settings, staged inputs and original requested controls once.
3. Evaluate `handoff.project` and `handoff.launch` against the resolved plan.
4. Verify the same plan and recheck current host, settings and ABAC policy at dispatch.
5. Execute its captured arguments or SDK callable and return its public metadata.

Saved settings also retain their existing per-setting authorization checks.
Without `HARNESS_CONTROL_CONFIG`, resolution and integrity checks still apply,
but the receipt makes no ABAC governance claim. Continuation and history retain
their existing gates; this plan boundary applies to fresh launches.

## What the plan binds

| Field | Binding |
| --- | --- |
| Adapter | Actual `cli.<harness>.fresh` or `sdk.<harness>.fresh`, after resolving `use=auto` |
| Executable | Absolute resolved file path, SHA-256, device and inode |
| Workspace | Canonical absolute directory, device and inode; captured native workspace options |
| Native settings | Settings emitted by the adapter; `null` represents omitted or inherited values |
| Access context | Trusted product reference, permission context and realm, with host binding |
| Inputs | Contract, settings catalog, adapter source, staged prompt and supplied model evidence |
| Private content | Prompt, arguments and stdin participate in the digest but are omitted from public plan metadata |

CLI plans pin the native CLI executable. SDK plans pin the Python runtime,
captured bridge callable and options. SDK-managed worker executables, vendor
configuration, provider credentials and downstream activity remain outside that
file pin. A setting recorded as inherited is not proof of the vendor's effective
configuration. Governed SDK routes that cannot bind the workspace are refused.

A workspace alias retargeted after resolution cannot change the captured
canonical workspace. Changing a pinned file, directory identity, callable or
sealed plan refuses dispatch. Codex additionally validates that its emitted
model, effort, workspace and approval arguments match the resolved settings.

## ABAC resource labels

Existing `requested_model`, `requested_reasoning_effort`, `requested_approval`
and `requested_use` labels preserve the caller's original request. Fresh launch
decisions additionally receive:

| Label | Value |
| --- | --- |
| `launch_plan_digest` | Digest of the private resolved plan |
| `execution_adapter` | Exact adapter, such as `cli.codex.fresh` |
| `execution_route` | `cli` or `sdk` |
| `executable`, `executable_digest` | Resolved absolute path and file SHA-256 |
| `executable_kind` | `native_cli` or `python_runtime` |
| `workspace` | Canonical absolute workspace |
| `native_settings` | Canonical JSON object |
| `resolved_<setting>` | JSON-encoded setting value, including quotes for strings and `null` |

For example, an `auto` request can resolve to CLI. A rule can constrain
`execution_route=cli` and `resolved_model="MODEL_ID"` while retaining
`requested_use="auto"` as request evidence. Access profiles remain owned by
ABAC and the trusted product host; the adapter does not infer them from a harness.

## Executor boundary and limits

Internal callers use `launch_plan.resolve`, `control.authorize_launch_plan`, then
`cli_executor.run_cli(plan, authorization=receipt)` or
`sdk_executors.run_plan(plan, authorization=receipt)`. The former raw CLI
argument/receipt interface is removed. A governed executor requires a receipt
bound to the same plan digest and performs a fresh policy check.

The public `harness.launch_plan.v1` metadata and
`harness.launch_authorization.v1` receipt are audit records, not signed replay
tokens. Only the trusted in-memory plan is executable. The trusted host must
protect the resolver, evaluator and execution implementation. File checks occur
before dispatch and do not provide an atomic operating-system lock against all
concurrent filesystem mutation.

This boundary does not change session-ID ownership, descendant cleanup on
timeout, or the global saved-profile revision behavior. No native approval hook,
policy installation or live host activation is performed automatically.
