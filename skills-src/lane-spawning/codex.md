## Direct lane spawning

For a new handoff, spawn the requested number of independent caller-owned Codex executions directly through the contract-authorized fresh SDK or CLI route. Each lane gets its own prompt, owned thread/process handle, and result. Do not use a lane manager, leader, coordinator, relay, shared server, background task manager, or parent agent to fan out or run the lanes. Continuation, resume, fork, and app-server routes remain forbidden for this fresh-only handoff.
