## Direct lane spawning

For a new handoff, spawn the requested number of independent native Antigravity CLI processes directly. Each lane gets its own prompt, process handle, and result. Do not use a lane manager, leader, coordinator, relay, server, or parent agent to fan out or run the lanes. Existing-session continuation is allowed only when the operator explicitly asks to continue that exact session.
