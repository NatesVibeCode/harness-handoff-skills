package groksession

import (
	"bytes"
	"context"
	"errors"
	"os"
	"path/filepath"
	"reflect"
	"strings"
	"testing"
)

func TestStartResumeAndFork(t *testing.T) {
	fixture := []byte("{\"sessionId\":\"session-fixture\",\"finalResponse\":\"ready\"}\n")

	t.Run("fresh", func(t *testing.T) {
		client, argsFile, promptFile := fakeClient(t, fixture)
		result, err := client.Start(context.Background(), "say ready")
		if err != nil {
			t.Fatal(err)
		}
		if result.SessionID != "session-fixture" || !bytes.Equal(result.JSON, fixture) {
			t.Fatalf("result = %#v", result)
		}
		args := readArgs(t, argsFile)
		assertContainsSequence(t, args, "--output-format", "json", "--prompt-file")
		if contains(args, "--resume") || contains(args, "--fork-session") {
			t.Fatalf("fresh args unexpectedly resume or fork: %q", args)
		}
		if got := readFile(t, promptFile); got != "say ready" {
			t.Fatalf("prompt file = %q", got)
		}
	})

	t.Run("resume exact id", func(t *testing.T) {
		client, argsFile, promptFile := fakeClient(t, fixture)
		if _, err := client.Resume(context.Background(), "id-123", "continue"); err != nil {
			t.Fatal(err)
		}
		args := readArgs(t, argsFile)
		assertContainsSequence(t, args, "--resume", "id-123", "--prompt-file")
		if contains(args, "--fork-session") {
			t.Fatalf("resume unexpectedly forks: %q", args)
		}
		if got := readFile(t, promptFile); got != "continue" {
			t.Fatalf("prompt file = %q", got)
		}
	})

	t.Run("fork", func(t *testing.T) {
		client, argsFile, _ := fakeClient(t, fixture)
		if _, err := client.Fork(context.Background(), "id-123", "branch"); err != nil {
			t.Fatal(err)
		}
		args := readArgs(t, argsFile)
		assertContainsSequence(t, args, "--resume", "id-123", "--fork-session", "--prompt-file")
	})
}

func TestStreamPassesThroughNDJSON(t *testing.T) {
	fixture := []byte("{\"fixture_event\":\"opaque\"}\n")
	client, argsFile, promptFile := fakeClient(t, fixture)
	var output bytes.Buffer
	if err := client.Stream(context.Background(), "id-stream", true, "stream this", &output); err != nil {
		t.Fatal(err)
	}
	if !bytes.Equal(output.Bytes(), fixture) {
		t.Fatalf("stream output = %q, want %q", output.Bytes(), fixture)
	}
	args := readArgs(t, argsFile)
	assertContainsSequence(t, args, "--output-format", "streaming-json", "--resume", "id-stream", "--fork-session", "--prompt-file")
	if got := readFile(t, promptFile); got != "stream this" {
		t.Fatalf("prompt file = %q", got)
	}
}

func TestListAndInspect(t *testing.T) {
	t.Run("list", func(t *testing.T) {
		fixture := []byte("Recent sessions\n  fixture-session\n")
		client, argsFile, _ := fakeClient(t, fixture)
		got, err := client.List(context.Background(), 7)
		if err != nil {
			t.Fatal(err)
		}
		if !bytes.Equal(got, fixture) {
			t.Fatalf("list = %q, want %q", got, fixture)
		}
		if want := []string{"sessions", "list", "--limit", "7"}; !reflect.DeepEqual(readArgs(t, argsFile), want) {
			t.Fatalf("args = %q, want %q", readArgs(t, argsFile), want)
		}
	})

	t.Run("inspect transcript", func(t *testing.T) {
		fixture := []byte("# Session transcript\n")
		client, argsFile, _ := fakeClient(t, fixture)
		got, err := client.Inspect(context.Background(), "fixture-session")
		if err != nil {
			t.Fatal(err)
		}
		if !bytes.Equal(got, fixture) {
			t.Fatalf("inspect = %q, want %q", got, fixture)
		}
		if want := []string{"export", "fixture-session"}; !reflect.DeepEqual(readArgs(t, argsFile), want) {
			t.Fatalf("args = %q, want %q", readArgs(t, argsFile), want)
		}
	})
}

func TestRefusesMissingIdentifiersAndBadLimits(t *testing.T) {
	client, argsFile, _ := fakeClient(t, []byte("{}\n"))
	if _, err := client.Resume(context.Background(), "", "prompt"); !errors.Is(err, ErrInvalidArgument) {
		t.Fatalf("Resume error = %v", err)
	}
	if _, err := client.Fork(context.Background(), "", "prompt"); !errors.Is(err, ErrInvalidArgument) {
		t.Fatalf("Fork error = %v", err)
	}
	for _, id := range []string{"--last", "latest", "../other"} {
		if _, err := client.Resume(context.Background(), id, "prompt"); !errors.Is(err, ErrInvalidArgument) {
			t.Fatalf("Resume(%q) error = %v", id, err)
		}
	}
	if err := client.Stream(context.Background(), "", true, "prompt", &bytes.Buffer{}); !errors.Is(err, ErrInvalidArgument) {
		t.Fatalf("Stream error = %v", err)
	}
	if _, err := client.List(context.Background(), -1); !errors.Is(err, ErrInvalidArgument) {
		t.Fatalf("List error = %v", err)
	}
	if _, err := client.Inspect(context.Background(), ""); !errors.Is(err, ErrInvalidArgument) {
		t.Fatalf("Inspect error = %v", err)
	}
	if _, err := os.Stat(argsFile); !errors.Is(err, os.ErrNotExist) {
		t.Fatalf("invalid call invoked CLI; args file stat error = %v", err)
	}
}

func TestRejectsJSONWithoutSessionID(t *testing.T) {
	client, _, _ := fakeClient(t, []byte("{\"finalResponse\":\"ready\"}\n"))
	if _, err := client.Start(context.Background(), "say ready"); err == nil || !strings.Contains(err.Error(), "no sessionId") {
		t.Fatalf("Start error = %v", err)
	}
}

func fakeClient(t *testing.T, stdout []byte) (Client, string, string) {
	t.Helper()
	dir := t.TempDir()
	argsFile := filepath.Join(dir, "args.txt")
	promptFile := filepath.Join(dir, "prompt.txt")
	stdoutFile := filepath.Join(dir, "stdout.txt")
	if err := os.WriteFile(stdoutFile, stdout, 0o600); err != nil {
		t.Fatal(err)
	}
	script := `#!/bin/sh
set -eu
: > "$FAKE_ARGS_FILE"
for arg in "$@"; do printf '%s\n' "$arg" >> "$FAKE_ARGS_FILE"; done
previous=
for arg in "$@"; do
  if [ "$previous" = "--prompt-file" ]; then
    cat "$arg" > "$FAKE_PROMPT_FILE"
    break
  fi
  previous=$arg
done
cat "$FAKE_STDOUT_FILE"
`
	binary := filepath.Join(dir, "grok")
	if err := os.WriteFile(binary, []byte(script), 0o700); err != nil {
		t.Fatal(err)
	}
	t.Setenv("FAKE_ARGS_FILE", argsFile)
	t.Setenv("FAKE_PROMPT_FILE", promptFile)
	t.Setenv("FAKE_STDOUT_FILE", stdoutFile)
	return Client{Binary: binary, WorkingDirectory: dir, Stderr: ioDiscard{}}, argsFile, promptFile
}

type ioDiscard struct{}

func (ioDiscard) Write(p []byte) (int, error) { return len(p), nil }

func readArgs(t *testing.T, path string) []string {
	t.Helper()
	data := readFile(t, path)
	if data == "" {
		return nil
	}
	return strings.Split(strings.TrimSuffix(data, "\n"), "\n")
}

func readFile(t *testing.T, path string) string {
	t.Helper()
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	return string(data)
}

func assertContainsSequence(t *testing.T, got []string, want ...string) {
	t.Helper()
	for i := 0; i+len(want) <= len(got); i++ {
		if reflect.DeepEqual(got[i:i+len(want)], want) {
			return
		}
	}
	t.Fatalf("args %q do not contain sequence %q", got, want)
}

func contains(values []string, want string) bool {
	for _, value := range values {
		if value == want {
			return true
		}
	}
	return false
}
