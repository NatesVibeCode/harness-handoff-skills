# Codex Session Client

A small Go library for the documented Codex CLI session surface
(`codex exec`). It uses the installed `codex` executable; it does not call
the OpenAI API directly and does not use the Codex SDKs or the app-server
protocol. The package has no third-party Go dependencies and never installs
or updates the CLI.

## Requirements and authentication

Install Codex using an official method and confirm the binary:

```sh
codex --version
```

Authenticate the CLI before use: ChatGPT login (`codex login`) or API-key
auth. The documented automation guidance prefers `CODEX_API_KEY` inline
for a single invocation rather than exported job-wide. This package
inherits the process environment and stores no credentials.

The client launches the CLI in the selected working directory, so Codex
uses that workspace's normal configuration, permissions, sandbox, and
local session store. The client does not change sandbox, approval, or
model settings; `--skip-git-repo-check` is always passed so disposable
non-git workspaces work.

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

	codex "github.com/NatesVibeCode/harness-handoff-skills/clients/codex-session-client"
)

func main() {
	ctx := context.Background()
	client := codex.Client{
		Binary:           "codex",
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
		fmt.Println(s.ID, s.Cwd, s.Modified, s.Size)
	}

	transcript, err := client.Inspect(ctx, branch.SessionID)
	if err != nil {
		panic(err)
	}
	fmt.Print(string(transcript))
}
```

`Start`, `Resume`, and `Fork` use the CLI's `exec --json` JSONL output and
return the `thread_id` plus the final agent message text and the complete
JSONL bytes. `Stream` copies native `--json` JSONL bytes to the supplied
writer without interpreting events. `List` reads the documented local
session store for the workspace; `Inspect` returns the selected session's
stored JSONL verbatim.

Prompts travel over the CLI process's stdin (the `-` prompt argument),
keeping prompt text out of the process argument list. Captured JSONL and
transcript output is bounded to 16 MiB by default; set
`Client.MaxOutputBytes` to choose another positive bound. Streaming is
passed directly to the caller's writer.

## Scope

The package supports local Codex CLI sessions only. It does not use the
TypeScript or Python Codex SDKs, the app-server protocol, or API thread
IDs. Session IDs are local thread IDs and must be used where the CLI can
find them; the store base is `$CODEX_HOME/sessions`, or
`~/.codex/sessions` when `CODEX_HOME` is unset. Forking always requires an
explicit session ID and starts a new thread. Resume and fork run in the
client's working directory because those subcommands accept no `-C` flag.

The library does not parse stored transcript contents. `Inspect` returns
each file exactly as stored.

The fresh-only `codex-harness-handoff` skill forbids continuation
(`continuation: forbidden` in its contract): handoff lanes use `Start`
only, and the bridge refuses codex continuation without executing.
`Resume`, `Fork`, resumed `Stream`, `List`, and `Inspect` exist for
non-handoff tooling and must not be used from a handoff lane.

## Verification

See [CONFORMANCE.md](CONFORMANCE.md) for the installed CLI version, source
checks, offline wrapper tests, documented limitations, and live
re-verification steps.
