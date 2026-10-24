# Typed SDK action Blocks

Each supported SDK action is a reusable typed Block backed by its Node
implementation. The library declarations contain Nodes, Block inputs/outputs
and pinned implementation material. They create no per-action Process, Tool or
worker. A job composes the required Blocks and supplies its Process policy.

`authoring/build_sdk_plans.py` generates the supported Python action Blocks.
`authoring/build_ts_sdk_plans.py --modules-only` generates the TypeScript action
Blocks. `--dsh-only` generates DSH's `session_turn` Block. The builders reuse
existing field, source-hash, runtime and contract bindings.

DSH's Node implements ACP. Its caller supplies `prompt`, `workspace`, optional
exact `session_id`, `route_provider`, `route_model`, `route_overlay_path` and
`route_overlay_digest`. It checks the route DSH reports before prompting and
returns requested, configured and observed route fields separately. DSH resolves
its customer credentials. Ordinary field values do not require a rebuild.

The job's worker owns scheduling, typed checks, authority, cancellation and
receipts. Nodes supply SDK execution implementations and native session binding.
Forge builds the selected job; factory source and services are absent at runtime.

The shared runner source uses this boundary: TypeScript locates its pinned
sibling adapter, the obsolete shared DSH dispatch is removed, and Python
failure diagnostics are retained. Language contract envelopes remain separate.
