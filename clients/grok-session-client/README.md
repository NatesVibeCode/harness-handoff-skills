# Grok Session Client

A small Go library for the documented Grok Build CLI session surface. It uses
the installed `grok` executable; it does not call the xAI model API directly.
The package has no third-party Go dependencies and never installs or updates
the CLI.

## Requirements and authentication

Install Grok Build using an official method, then authenticate with `grok login`
or provide `XAI_API_KEY` in the environment at runtime. For example, the
official macOS/Linux installer is:

```sh
curl -fsSL https://x.ai/cli/install.sh | bash
```

The official npm CLI distribution is also available as
`@xai-official/grok`. This package does not run either installer. The Grok CLI
also supports its documented cached-session authentication. This package
inherits the process environment and stores no credentials.

The client launches the CLI in the selected working directory, so Grok uses
that workspace's normal configuration, permissions, tools, and local session
store. The client does not enable auto-approval or change those settings.

The current official headless guide documents `--no-auto-update` and the
`[cli] auto_update = false` configuration setting. The installed Grok 1.0.41
help did not list `--no-auto-update`, so this package does not pass that flag.
To suppress background update checks with that version, set this in
`~/.grok/config.toml`:

```toml
[cli]
auto_update = false
```

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

	grok "github.com/NatesVibeCode/harness-handoff-skills/clients/grok-session-client"
)

func main() {
	ctx := context.Background()
	client := grok.Client{
		Binary:           "grok",
		WorkingDirectory: "/path/to/workspace",
		Stderr:           os.Stderr,
	}

	fresh, err := client.Start(ctx, "Explain this codebase in three bullets.")
	if err != nil {
		panic(err)
	}
	fmt.Println("session:", fresh.SessionID)

	continued, err := client.Resume(ctx, fresh.SessionID, "Now summarize the risks.")
	if err != nil {
		panic(err)
	}
	fmt.Println("resumed:", continued.SessionID)

	branch, err := client.Fork(ctx, fresh.SessionID, "Explore a different approach.")
	if err != nil {
		panic(err)
	}
	fmt.Println("fork:", branch.SessionID)

	if err := client.Stream(ctx, branch.SessionID, false, "Give me the short version.", os.Stdout); err != nil {
		panic(err)
	}

	sessions, err := client.List(ctx, 20)
	if err != nil {
		panic(err)
	}
	fmt.Print(string(sessions))

	transcript, err := client.Inspect(ctx, branch.SessionID)
	if err != nil {
		panic(err)
	}
	fmt.Print(string(transcript))
}
```

`Start`, `Resume`, and `Fork` use the CLI's JSON output and return the
documented `sessionId` plus the complete JSON bytes. `Stream` copies native
`streaming-json` NDJSON to the supplied writer without interpreting its event
schema. `List` and `Inspect` return the installed CLI's output verbatim:
`grok sessions list` and `grok export <session-id>`.

Prompts are written to a mode-0600 temporary file and removed after the CLI
exits. This keeps prompt text out of the process argument list. Captured JSON,
list, and transcript output is bounded to 16 MiB by default; set
`Client.MaxOutputBytes` to choose another positive bound. Streaming is passed
directly to the caller's writer.

## Scope

The package supports Grok Build CLI sessions only. It does not use `xai-sdk`,
the xAI Responses API, or API response IDs. Session IDs are local Grok Build
session IDs and must be used with the workspace and session store where Grok
can find them. Forking always requires an explicit session ID.

The library does not parse the human-readable session list or Markdown
transcript. It returns each exactly as emitted by the installed CLI.

## Verification

See [CONFORMANCE.md](CONFORMANCE.md) for the installed CLI version, source
checks, offline wrapper tests, documented limitations, and live re-verification
steps.
