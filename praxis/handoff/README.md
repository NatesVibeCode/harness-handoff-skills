# Typed harness handoff authoring

The deterministic packet Process prepares a portable handoff packet and prompt
from explicit caller context. Its three Function Nodes form two reusable Blocks.
It preserves the operator instruction and separates destination product, harness,
client, channel, inference mechanism, execution adapter, workspace, operation,
task state, acceptance criteria and evidence. It fingerprints the exact packet
JSON. It has no external effects and does not establish identity or authorization.

`contracts/` holds its typed input and packet schemas; `module/` holds the Function
implementations. Refresh its authoring inputs with:

```sh
python3 praxis/handoff/authoring/build_requests.py
forge-author plan -input praxis/handoff/authoring/plan.json \
  -stores praxis/handoff/authoring/stores.json -out /path/to/new-print -develop
```

Historical unsigned packet prints and discovery receipts are retained separately;
they are not included in this source tree and do not qualify current source.
The existing MCP bridge performs its own live authorization and launch-plan
checks. Connecting a printed Process to that bridge requires evidence for that
exact connection.

The [fresh SDK plans](sdk/README.md) provide eleven SDK operation Nodes, reusable
Blocks and one-operation Processes. Their current factory and real-use gaps are
listed there. They are not admitted capabilities.
