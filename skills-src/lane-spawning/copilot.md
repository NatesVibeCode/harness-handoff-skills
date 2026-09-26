## Direct lane spawning

For a new handoff, spawn the requested number of independent caller-owned Copilot executions directly through the contract-authorized SDK or CLI route. Each lane gets its own prompt, owned session/process handle, and result. A per-lane owned SDK client is that lane's execution handle, not a shared server. Do not use a lane manager, leader, coordinator, relay, shared CLI server, background task manager, or parent agent to fan out or run the lanes. Existing-session continuation is allowed only when the operator explicitly asks to continue that exact session.
