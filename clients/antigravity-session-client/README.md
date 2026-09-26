# Antigravity Session Client

A small Go library for the documented Antigravity CLI session surface
(`agy --print`). It uses the installed `agy` executable; it does not use
the Python Antigravity SDK or the Gemini Interactions managed agent. The
package has no third-party Go dependencies and never installs or updates
the CLI.

Do not confuse `agy` with the legacy `gemini` CLI: they are different
products with different flags.

## Requirements and authentication

Install the Antigravity CLI using an official method and confirm it:

```sh
agy --version
```

Authenticate before use: the CLI's native session (OS keyring silent
sign-in, browser OAuth, or SSH code flow) or API-key mode
(`modelProvider:"gemini"` in CLI settings plus `GEMINI_API_KEY` in the
environment — the env var alone has no effect). This package inherits the
process environment and stores no credentials.

The client launches the CLI from the configured working directory, since
history is workspace-scoped: resume from the checkout that owns the
conversation. It does not change approval or sandbox settings, which are
separate controls; unapproved tools may soft-deny with exit 0, so check
`status` and artifacts, not just the error return.

## Install the library

Use the directory as a local Go module:

```sh
go test ./...
```

There are no package downloads or build-time network calls.

## Examples

```go
package main

import (
	"context"
	"fmt"
	"os"

	antigravity "github.com/NatesVibeCode/harness-handoff-skills/clients/antigravity-session-client"
)

func main() {
	ctx := context.Background()
	client := antigravity.Client{
		Binary:           "agy",
		WorkingDirectory: "/path/to/checkout",
		Stderr:           os.Stderr,
	}

	fresh, err := client.Start(ctx, "Explain this codebase in three bullets.")
	if err != nil {
		panic(err)
	}
	fmt.Println("session:", fresh.SessionID, "text:", fresh.Text)

	continued, err := client.Resume(ctx, fresh.SessionID, "Now summarize the risks.")
	if err != nil {
		panic(err)
	}
	fmt.Println("resumed:", continued.SessionID)

	if err := client.Stream(ctx, continued.SessionID, "Give me the short version.", os.Stdout); err != nil {
		panic(err)
	}
}
```

`Start` and `Resume` use the CLI's `--print --output-format json`
envelope and return the documented `conversation_id` plus the response
text and the complete JSON bytes. `Stream` opens a streaming session with
one documented user frame and copies the CLI's bytes to the supplied
writer without interpreting them.

`Fork`, `List`, and `Inspect` are unsupported: no fork flag, session-list
command, or export command is documented, and the local SQLite/transcript
paths are explicitly not an API. All three return `ErrUnsupported`
without invoking the CLI.

One-shot prompts are passed as an argv element (the CLI's documented
prompt delivery), so prompt text is visible in the process list while the
command runs. Captured JSON output is bounded to 16 MiB by default; set
`Client.MaxOutputBytes` to choose another positive bound. Streaming is
passed directly to the caller's writer.

## Scope

The package supports local Antigravity CLI conversations only. It does
not use the Python SDK (which builds new SDK-owned agents and cannot
drive existing `agy`/IDE conversations), the managed Interactions agent
(which provisions separate cloud sandboxes), or the legacy Gemini CLI.
Resume never uses `--continue`, which would select the newest session
instead of the requested ID.

## Verification

See [CONFORMANCE.md](CONFORMANCE.md) for sources, documented limitations,
and the surfaces behind each method.
