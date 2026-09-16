## Direct lane spawning

For a new handoff, spawn the requested number of independent Grok Build CLI processes directly with `--no-leader` when that installed CLI supports the flag. Each lane gets its own prompt, process handle, and result. Do not use a lane manager, shared leader, coordinator, relay, server, or parent agent to fan out or run the lanes. Existing-session continuation is allowed only when the operator explicitly asks to continue that exact session.
