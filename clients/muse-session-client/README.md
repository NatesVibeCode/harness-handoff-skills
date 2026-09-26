# Muse Session Client

A small Go library for the documented Muse Code CLI session surface
(`muse exec`, `muse export`). It uses the installed `muse` executable; it
does not speak the Muse Session Protocol directly and does not use the
TypeScript/Python SDKs. The package has no third-party Go dependencies and
never installs or updates the CLI.

## Requirements and authentication

Install Muse Code using an official method and confirm the binary:

```sh
muse --version
```

Authenticate before use: browser sign-in (`muse`, then `/login`) or
`META_API_KEY` in the environment at runtime (`META_API_KEY` wins over
stored credentials). This package inherits the process environment and
stores no credentials.

The client passes the workspace via `--workspace` with `--worktree off`.
It does not change approval, sandbox, model, or reasoning settings; choose
an automation posture (e.g. `--disable-approval`) in your own CLI
configuration. A run's exit code reflects how the run ended (0 complete, 1
failed/cancelled, 2 usage), not whether the work is correct — gate on your
own tests.

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

	muse "github.com/NatesVibeCode/harness-handoff-skills/clients/muse-session-client"
)

func main() {
	ctx := context.Background()
	client := muse.Client{
		Binary:           "muse",
		WorkingDirectory: "/path/to/workspace",
		Stderr:           os.Stderr,
	}

	fresh, err := client.Start(ctx, "Explain this codebase in three bullets.")
	if err != nil {
		panic(err)
	}
	fmt.Println(string(fresh.JSON))

	// Inspect needs a session ID extracted from the JSONL above
	// per the MSP wire reference; see Scope.
	if err := client.Stream(ctx, "", "Give me the short version.", os.Stdout); err != nil {
		panic(err)
	}

	transcript, err := client.Inspect(ctx, "01J...")
	if err != nil {
		panic(err)
	}
	fmt.Print(string(transcript))
}
```

`Start` uses the CLI's `exec --json` JSONL output and returns the bytes
verbatim. `Stream` with an empty session ID copies native `--json` JSONL
to the supplied writer without interpreting events. `Inspect` exports the
session document via `muse export --session <id> --out <tmp> --redacted`
and returns the file bytes verbatim.

`Resume` and resumed `Stream` are unsupported: the checked CLI documents
`exec --session-id` as an identity for a new run rather than a
history-preserving continuation, and `muse resume` is interactive-only,
so no documented headless resume-with-prompt exists. `Fork` and `List`
are unsupported: forking and listing exist on the MSP protocol and (for
fork) the interactive UI, but no headless CLI surface is documented. All
unsupported paths return `ErrUnsupported` without invoking the CLI.

Prompts are written to a mode-0600 temporary file and removed after the
CLI exits, keeping prompt text out of the process argument list. Captured
JSONL and export output is bounded to 16 MiB by default; set
`Client.MaxOutputBytes` to choose another positive bound. Streaming is
passed directly to the caller's writer.

## Scope

The package supports local Muse Code CLI sessions only. It does not parse
event envelopes: session IDs and message text must be extracted from the
returned JSONL per the MSP wire reference, because envelope field names
are outside the consulted documentation. There is no headless
resume-with-prompt: `exec --session-id` only selects an identity for a
new run and does not resume history, while `muse resume` continues a
retained session interactively. The on-disk session index is explicitly
not an official API and is never read.

## Verification

See [CONFORMANCE.md](CONFORMANCE.md) for sources, documented limitations,
and the surfaces behind each method.
