## Direct lane spawning

For a new handoff, spawn the requested number of independent caller-owned Muse executions directly through the contract-authorized SDK or CLI route. Each lane gets its own prompt, owned MSP-session/process handle, and result. A per-lane owned SDK host is that lane's execution handle, not a shared server. Do not use a lane manager, leader, coordinator, relay, shared server, shared MSP host, child-message relay, or parent agent to fan out or run the lanes. Existing-session continuation is allowed only when the operator explicitly asks to continue that exact session.
