## Direct lane spawning

For a new handoff, spawn the requested number of independent caller-owned Amp executions directly through the contract-authorized SDK or CLI route. Each lane gets its own prompt, owned thread/process handle, and result. A per-lane owned SDK run is that lane's execution handle, not a shared backend. Do not use a lane manager, leader, coordinator, relay, shared server, shared thread, background task manager, or parent agent to fan out or run the lanes. Existing-thread continuation is allowed only when the operator explicitly asks to continue that exact thread.
