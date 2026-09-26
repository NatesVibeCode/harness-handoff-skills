# Claude Session Client

A small Go library for the documented Claude Code CLI session surface. It
uses the installed `claude` executable; it does not call the Anthropic API
directly and does not use the Agent SDK. The package has no third-party Go
dependencies and never installs or updates the CLI.

## Requirements and authentication

Install Claude Code using an official method and confirm the binary:

```sh
claude --version
```

Authenticate the CLI before use: API-key auth via `ANTHROPIC_API_KEY` in the
environment at runtime, or the CLI's own login. This package inherits the
process environment and stores no credentials. Note the documented product
rule: third-party products built on Claude sessions should use the API-key
authentication methods, not a subscription login token.

The client launches the CLI in the selected working directory, so Claude
uses that workspace's normal configuration, permissions, tools, and local
session store. The client does not change permission modes or settings.

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

	claude "github.com/NatesVibeCode/harness-handoff-skills/clients/claude-session-client"
)

func main() {
	ctx := context.Background()
	client := claude.Client{
		Binary:           "claude",
		WorkingDirectory: "/path/to/workspace",
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
	for _, s := range sessions {
		fmt.Println(s.ID, s.Modified, s.Size)
	}

	transcript, err := client.Inspect(ctx, branch.SessionID)
	if err != nil {
		panic(err)
	}
	fmt.Print(string(transcript))
}
```

`Start`, `Resume`, and `Fork` use the CLI's `-p --output-format json` array
output and return the documented `session_id` plus the result text and the
complete JSON bytes. `Stream` copies native `stream-json` bytes to the
supplied writer without interpreting its event schema. `List` reads the
documented local transcript store for the workspace; `Inspect` returns the
selected session's JSONL transcript verbatim.

Prompts travel over the CLI process's stdin, keeping prompt text out of the
process argument list. Captured JSON and transcript output is bounded to 16
MiB by default; set `Client.MaxOutputBytes` to choose another positive
bound. Streaming is passed directly to the caller's writer.

## Scope

The package supports Claude Code CLI sessions only. It does not use the
Agent SDK, the Messages API, or API request IDs. Session IDs are local
Claude session IDs and must be used with the workspace whose store holds
them; the store key derives from the resolved working directory, and
`$CLAUDE_CONFIG_DIR` overrides the `~/.claude` base when set. Forking
always requires an explicit session ID and branches conversation history,
not the working tree. Sessions created headlessly do not appear in the
interactive session picker but remain resumable by ID.

The library does not parse transcript contents. `Inspect` returns each
JSONL transcript exactly as stored.

## Verification

See [CONFORMANCE.md](CONFORMANCE.md) for the installed CLI version, source
checks, offline wrapper tests, documented limitations, and live
re-verification steps.
