# Cursor Session Client

A small Go library for the documented Cursor Agent CLI session surface. It
uses the installed `cursor-agent` executable; it does not call the Cloud
Agents API directly and does not use the TypeScript/Python SDKs. The
package has no third-party Go dependencies and never installs or updates
the CLI.

Docs invoke the CLI as `agent`; this package defaults to `cursor-agent`
(the same first-party binary family) and accepts an override via
`Client.Binary`.

## Requirements and authentication

Install the Cursor Agent CLI using an official method and confirm it:

```sh
cursor-agent --version
```

Authenticate before use: the CLI's native login (`agent login`) or
`CURSOR_API_KEY` in the environment at runtime. This package inherits the
process environment and stores no credentials.

The client passes the workspace via `--workspace` and always enables the
documented sandbox flag. It does not change model defaults (unless
`Client.Model` is set), approval, or mode settings. Discover models with
the CLI's `--list-models` option.

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

	cursor "github.com/NatesVibeCode/harness-handoff-skills/clients/cursor-session-client"
)

func main() {
	ctx := context.Background()
	client := cursor.Client{
		Binary:           "cursor-agent",
		WorkingDirectory: "/path/to/workspace",
		Model:            "composer-2.5",
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

	sessions, err := client.List(ctx)
	if err != nil {
		panic(err)
	}
	fmt.Print(string(sessions))
}
```

`Start` and `Resume` use the CLI's `--print --output-format json` object
output and return the documented `session_id` plus the result text and the
complete JSON bytes. `Stream` copies native `stream-json` NDJSON to the
supplied writer without interpreting events. `List` returns the CLI's `ls`
output verbatim; no machine-readable contract is documented for it.

`Fork` and `Inspect` are unsupported: the documented CLI surface exposes
no fork operation and no passive transcript read. Both return
`ErrUnsupported` without invoking the CLI.

Prompts are passed as the final argv element (the CLI's documented prompt
delivery), so prompt text is visible in the process list while the command
runs. Captured JSON and list output is bounded to 16 MiB by default; set
`Client.MaxOutputBytes` to choose another positive bound. Streaming is
passed directly to the caller's writer.

## Scope

The package supports local Cursor Agent CLI sessions only. It does not use
the TypeScript/Python SDKs, the SDK Bridge, or Cloud Agents REST IDs: CLI
chat IDs, local `agent-…` IDs, and cloud `bc-…` IDs are different
namespaces and are not interchangeable. Resume never uses `--continue`,
which would select the latest session instead of the requested ID.

## Verification

See [CONFORMANCE.md](CONFORMANCE.md) for sources, documented limitations,
and the surfaces behind each method.
