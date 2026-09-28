# Harness probe

Build-time discovery belongs to harness-handoff. This standalone Go command
captures CLI version/help evidence or a Go SDK entrypoint signature. It requires
explicit declarations for launch behavior it cannot establish from those probes.
It has no Forge dependency and does not launch an agent task.

From the repository root:

```sh
go run ./tools/harnessprobe cli -h
go run ./tools/harnessprobe sdk -h
go test ./tools/harnessprobe/...
```

`cli -out /path/to/candidate.json` writes a launch-description candidate and an
evidence sidecar. This is not a second source of launch authority. Adopt reviewed
values in `skills-src/contracts.json`, then run `python3 scripts/build_skills.py`.
Do not target generated `<harness>-harness-handoff/contract.json` files with the
probe. `scripts/build_skills.py` remains the only writer of generated skill trees.

Forge consumes the selected generated description read-only, applies its own
admission validation, and embeds invocation/parser behavior in the printed
Process. The printed Process owns execution and receipts. Probe output proves
neither real-use success nor readiness for admission.

This command moved from Forge's untracked `cmd/harnessprobe` implementation.
The move removes its reverse dependency on Forge; candidate shape checks are
local to this helper. Consumer admission checks remain with the consumer.
