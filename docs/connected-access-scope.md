# Connected access product: first-release scope

Status: scoped proposal, 30 September 2026. The architecture is selected; the
product, contracts and capability definitions below are not implemented or
admitted. This document grants no system access, provider spend or external
write authority. It records the scope earned by the eight-voice architecture
debate and the current interface inventory.

## Outcome and experience

An operator starts a harness and connects to one access product. The trusted
connection binds identity and product access automatically. The harness sees
permitted capabilities and uses them without selecting policy files or saved
harness settings profiles. Every governed operation resolves its concrete
target, receives an ABAC decision, enforces the approved operation and returns
a receipt.

Deployment administrators provision identity trust, product/access mappings,
resource registrations and credentials once. Authentication or consent may be
needed on first connection or expiry; existing login state is reused only where
the authenticated transport supports it. Zero per-session policy setup does
not mean anonymous access or automatic grants.

The guarantee covers operations through this product's enforced interfaces.
Native shell/file access, independent credentials and direct third-party app
connections keep their own authority unless explicitly brought into a qualified
execution boundary.

## Selected architecture and ownership

| Component | Responsibility |
| --- | --- |
| Trusted connection host | Authenticate the connection, bind the operator/session and product/access context, carry typed I/O, protect credential and recording custody, and mount the fixed product interfaces. |
| ABAC | Own policy vocabulary and evaluation semantics. The printed policy-evaluation Function pins the authoritative implementation; no parallel policy engine is introduced. |
| Printed Process | Own the complete flattened typed DAG for one governed outcome: context verification, resource resolution, decision, enforcement, effect certainty, recovery and receipt semantics. |
| Reusable Blocks | Compose exact pinned Nodes for trusted-context verification, resource resolution, access decisions and effect/receipt handling. |
| Nodes | Independently verifiable deterministic mechanisms or narrow integration mechanisms. No inference or agent-tool loop is needed for exact access decisions. |
| Deployment | Own transport configuration, storage, credentials, trusted policy publication and OS/container isolation where needed. |
| Product app / harness adapter | Present supported operations, access state and guidance; route requests through the same contracts. It cannot manufacture authority. |

The connection host never chooses Nodes, mappings, configuration, failure
behavior or business logic. Its endpoint-to-Process mapping is fixed by the
released product contract. It does not orchestrate a collection of tiny workers.
Each operation Process includes all the steps required to establish its outcome.

Work owns build-time authoring; current factory implementation is in Forge
source. Printing uses admitted Nodes, pinned Blocks and compiled Processes.
After delivery, Work, Forge, Printer, their databases and source checkouts are
absent. The printed product does not require a Rynth or OE execution runtime.

## First-release capability boundary

| Capability | Included behavior | Limit |
| --- | --- | --- |
| Connect and access status | Bind authenticated identity, session and product access; report valid, expired, revoked or unavailable state. | The client cannot supply authoritative roles, realm or permission context. |
| Capability projection | Return the allowed registered capability descriptions, typed inputs/outputs and pointable documentation. | This is the product's catalog; it does not hide or control tools supplied by other hosts. |
| Managed files | Read bounded content, create/replace a file with explicit preconditions, and list permitted directory entries beneath registered roots. | No arbitrary host path, recursive delete, rename, general patch language or shell command in v1. |
| Managed systems | Execute fixed, registered typed read/write operations against a registered deployment/account/resource. | One representative system binding must be selected and qualified before release. No arbitrary URL, provider, tool name or HTTP passthrough. |
| Results and receipts | Read status, result and receipt for permitted operations; preserve denial and uncertain effects. | Reads, exports and history are access-controlled too. A receipt is evidence, not a grant. |
| Connected permission updates | Use current trusted access revisions for subsequent operations without rewriting executable code or editing per-session pins. | Expanding sealed executable capability or adding an operation is a release change. |
| Operator/deployment access administration | Publish authenticated access changes through the trusted policy owner's existing administration path. | No agent permission-editing tool or new admin console is required in v1. If the publication path is absent, it must be supplied before claiming live management. |

Managed file creation/replacement resolves the allowed root and normalized
relative target, checks current authority, then uses a root-confined operation.
Existing-file replacement requires the expected content revision/digest; a
stale target refuses before writing. Creation must refuse an unexpected existing
target. Parent/symlink traversal and target substitution are part of proof.
Directory listing is a resource read, not automatic permission to read every
returned file. Writes report committed, not-started or uncertain outcomes rather
than implying cross-system transactions.

Every remote operation pins its supported account/resource resolver, schema,
service operation and credential scope. Secrets stay in deployment custody and
reach only the declared integration mechanism through its narrow operation
client. Denied operations do not resolve provider credentials or contact the
provider. A generic URL fetch or shell gateway is outside this release.

## Public interfaces

One product exposes MCP, HTTP/API and CLI adapters over the same fixed Process
contracts. A product-owned read/status view uses those contracts as well.
Frontends contain protocol parsing and presentation only; access decisions and
effects cannot be implemented independently in each adapter.

- Remote HTTP and Streamable HTTP MCP authenticate against a selected trusted
  issuer and bind tokens to the intended product/resource. Standard MCP
  authorization/discovery is reused where supported.
- Local stdio MCP and CLI use a trusted local connection binding. Its subject
  must be derived by the trusted host; caller flags and ordinary environment
  labels do not attest permission. Local mode does not claim isolation from an
  unrestricted process with the same underlying OS authority.
- The API declares fixed capability identifiers and typed resources. Raw
  caller-selected Process, Node, executable, provider or policy targets are
  refused.
- The result/receipt interface enforces principal and resource ownership; a
  guessed invocation identifier does not grant visibility.

These are proposed interfaces, not existing command names or URLs. A supported
remote MCP client and a supported local MCP client are qualified separately;
the package does not claim every harness supports both transports.

## Contracts to define and verify

The following names describe proposed contracts, not admitted schema IDs.

| Contract | Required binding |
| --- | --- |
| Trusted access context | Operator/principal, session reference, product reference, permission context, realm, issuer/audience, expiry/revocation identity and access revision. Harness, transport and execution adapter remain separate metadata. |
| Resource registration | Stable product-owned resource identity, canonical local root or fixed system/account binding, permitted supported operations, implementation bounds and revision. |
| Operation request | Capability identifier, resource reference, typed inputs, effect key and applicable target preconditions. No self-asserted authority fields. |
| Resolved operation plan | Exact targets, operation, adapter/configuration identity, input binding/digest, access-context binding and side-effect class. Private payloads and secrets are omitted from public metadata. |
| Trusted policy snapshot | Authenticated policy-owner revision, freshness/revocation state and publication provenance, within the released capability ceiling. Policy semantics remain ABAC-owned. |
| Access decision | Verdict bound to context, plan, policy revision and exact requested action. A decision cannot authorize a changed target or payload. |
| Operation receipt | Context/plan/implementation/policy bindings, effect identity, stage and outcome; permitted result reference and safe recovery instruction. |

Reuse the existing resolved launch-plan boundary where its contract fits.
General resource-operation plans are a separate explicit contract; launch
metadata is not proof that a child harness's later effects were governed.

## Policy changes, state and recovery

Pinned release material fixes executable mechanisms, supported configuration,
capability ceilings and trusted authority sources. Current policy assignments
are verified runtime data. The client cannot choose the policy source or inject
an authoritative snapshot. Adding capability beyond the ceiling requires new
proof and a release; changing permitted access inside it does not require
reprinting the evaluator.

Before a new effect starts, its Process verifies current authority and binds
the accepted revision to the exact operation. The successful dispatch gate is
the authorization point for that effect. Revocation observed before that point
refuses it. Revocation after an effect starts prevents future dispatch but does
not claim to undo an external effect. The release must specify and test the
trusted source's freshness behavior; an old login or cached allow is not enough.

V1 provides immediate bounded operation dispatch and readback, without a general
job scheduler or durable pending-work queue. It persists effect identities and
receipts so reconnect/restart can read an accepted operation's known outcome.
If an effect cannot be proven not started or completed, it is fenced as
uncertain. The client does not retry writes with a fresh effect key after losing
a response. Existing remote idempotency support is used only when the selected
operation's contract establishes it.

No session-lifetime writer lock, cross-session assignment mechanism or
coordination-record authority is introduced. Product access never depends on
another worker's presence declaration.

## Reuse map and integration scope

| Current source | Reuse / extension |
| --- | --- |
| ABAC core and bindings | Pin pure evaluation and canonical policy semantics; extend typed seams that currently lose concrete resource or access-context information. |
| harness-handoff resolved plans | Reuse resolve-once, decision binding, exact consumption and readable receipt lessons. Add connection binding through an explicit host adapter. |
| OE / SDK | Reuse trusted-binding, file-root, credential-custody and effect-certainty mechanisms where they can become verified standalone Nodes. Existing source is a donor, not runtime authority for the print. |
| Rynth | Consider mechanism slices when their current code is the best fit. A runtime fork is not part of this first-release scope. |
| Forge / Work factory | Author missing Nodes at build time, run exact mechanism proofs, admit, compose Blocks, compile Processes and print. No runtime decomposition or factory fallback. |
| Virtual Lab | Use local protocol/failure scenarios, with simulated evidence labeled accordingly. Live qualification remains separate. |

V1 qualifies the product's owned MCP/API/CLI paths and one managed filesystem
binding plus one selected system integration. It does not simultaneously retrofit
every current consumer. Fleet, Skillflow, coordination, mdview, discovery tools,
FL and app backends each require an explicit owner integration if they are to
claim this product's governance. Existing FL actor and access distinctions are
preserved; AO-FL-A is never inferred from a harness.

An integration is complete only when all relevant entrypoints share the gate.
Adding an MCP wrapper while CLI or Studio can perform the same privileged
operation directly does not govern that component as a whole. Alternatively,
those direct paths remain explicitly independently controlled.

## Excluded from the first release

- Whole-machine interception, live rewriting of arbitrary vendor-session
  permissions, or takeover of existing sessions.
- A Rynth/OE fork, resident scheduling runtime, agent loop, generic workflow
  engine, arbitrary MCP proxy, general shell or provider router.
- OS sandbox implementation. Contained harness execution is a separately
  qualified deployment mode; printing or signing is not containment.
- New admin UI, identity provider, credential vault or policy language. Bind
  existing trusted implementations; missing bindings are readiness blockers.
- Automatic control of third-party app connections or universal compatibility
  with all fourteen handoff harnesses.
- Runtime dependence on factory services, automatic Node admission, or policy
  changes made by an agent to bypass a refusal.

## Delivery and readiness gates

Deliver one installable access product: fixed connection interfaces,
standalone printed operation Processes, reusable pinned definitions, deployment
bindings, safe denial/recovery guidance and documentation of the governed
boundary. Shared Node/Block definitions belong to the factory catalog; users
do not install individual Nodes or manage an internal worker topology.

The release requires passing evidence bound to exact implementations:

1. A fresh local and remote harness connection obtains its authenticated access
   context without per-session profile or policy-path setup.
2. MCP, API and CLI produce matching decisions for the same context and exact
   operation, including result/history reads and malformed requests.
3. Another principal/session, forged product/profile/realm, expired context,
   replayed decision or substituted plan is refused before an effect.
4. File success and refusal exercise root escape, symlinks, target replacement,
   stale content, denied listing/read/write and unexpected existing targets.
5. The selected authorized system/account proves a permitted operation and
   safe refusal, with no credential resolution or provider call on denial.
6. Permission change, unavailable policy source and restart prove the declared
   dispatch freshness rule and prevent reuse of stale authority.
7. Lost response and interrupted write preserve effect identity and distinguish
   not-started, completed and uncertain outcomes without blind duplicate writes.
8. The printed package runs without factory checkouts/services or an OE/Rynth
   execution dependency. Host adapters do not choose its DAG or behavior.

Mocks, schema validation and signing checks supplement these proofs; they do
not substitute for exact real-use evidence. Local tests use representative
inputs; remote system qualification requires the specific authorized account
and spend/write permission. Missing authority blocks admission, not scope work.

## Conditions that would reopen the runtime decision

Reconsider a native OE/Rynth application or an independent fork if the product
actually requires prolonged jobs, durable scheduling, subscriptions,
reconnectable execution or recovery machinery that is materially cheaper to
qualify there. A long-lived listener alone is insufficient. A runtime-backed
product is a distinct implementation option; it must not be hidden beneath a
Process described as standalone.

## Supporting documentation

- [Access contexts and harness settings](access-profiles.md)
- [Current launch-plan boundary](launch-plans.md)
- [Existing bridge governance and limits](harness-control.md)

The source inventory found existing ABAC and OE mechanisms alongside consumers
without evaluator calls. Tool-name authorization currently lacks concrete
filepath/system targets. Those observations motivate this scope; they do not
establish a deployed universal access layer. No live integration or release
qualification was performed to produce this document.
