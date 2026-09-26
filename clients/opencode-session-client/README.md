# OpenCode Session Client

A small Go library for the documented OpenCode CLI session surface
(`opencode run`, `session list`, `export`). It uses the installed
`opencode` executable; it does not use the JS SDKs or speak the HTTP
server API directly. The package has no third-party Go dependencies and
never installs or updates the CLI.

## Requirements and authentication

Install OpenCode using an official method and confirm the binary:

```sh
opencode --version
```

Authenticate provider access before use (`opencode auth login` or
provider keys in the environment). This package inherits the process
environment and stores no credentials. It never attaches to a remote
server: `--dir` always names a local directory.

The client does not change model defaults (unless `Client.Model` is set),
approval, or sharing settings. It never passes `--share`, which would
publish the session.

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

	opencode "github.com/NatesVibeCode/harness-handoff-skills/clients/opencode-session-client"
)

func main() {
	ctx := context.Background()
	client := opencode.Client{
		Binary:           "opencode",
		WorkingDirectory: "/path/to/workspace",
		Model:            "anthropic/claude-3-5-sonnet-20241022",
		Stderr:           os.Stderr,
	}

	fresh, err := client.Start(ctx, "Explain this codebase in three bullets.")
	if err != nil {
		panic(err)
	}
	fmt.Println(string(fresh.JSON))

	// Resume and fork need a session ID extracted from the JSON above per
	// the server/SDK reference; see Scope.
	continued, err := client.Resume(ctx, "ses-...", "Now summarize the risks.")
	if err != nil {
		panic(err)
	}
	fmt.Println(string(continued.JSON))

	branch, err := client.Fork(ctx, "ses-...", "Explore a different approach.")
	if err != nil {
		panic(err)
	}
	fmt.Println(string(branch.JSON))

	if err := client.Stream(ctx, "ses-...", false, "Give me the short version.", os.Stdout); err != nil {
		panic(err)
	}

	sessions, err := client.List(ctx, 20)
	if err != nil {
		panic(err)
	}
	fmt.Print(string(sessions))

	transcript, err := client.Inspect(ctx, "ses-...")
	if err != nil {
		panic(err)
	}
	fmt.Print(string(transcript))
}
```

`Start`, `Resume`, and `Fork` use the CLI's `run --format json` event
output and return the bytes verbatim. `Stream` copies native event bytes
to the supplied writer without interpreting them. `List` returns
`session list --format json` output verbatim; `Inspect` returns
`opencode export <id> --sanitize` JSON with the installed CLI's redaction.

Prompts are passed as a trailing argv element (the CLI's documented prompt
delivery), so prompt text is visible in the process list while the command
runs. Captured output is bounded to 16 MiB by default; set
`Client.MaxOutputBytes` to choose another positive bound. Streaming is
passed directly to the caller's writer.

## Scope

The package supports local OpenCode CLI sessions only. It does not parse
event envelopes: session IDs must be extracted from the returned bytes per
the server/SDK reference, because envelope field names are outside the
consulted documentation. Session IDs belong to the backend that created
them and are not portable except via export/import. Resume never uses
`--continue`, which would select the latest session instead of the
requested ID. Fork copies history and returns a new session; it does not
isolate files.

## Verification

See [CONFORMANCE.md](CONFORMANCE.md) for sources, documented limitations,
and the surfaces behind each method.
