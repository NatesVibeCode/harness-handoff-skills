package opencodesession

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

const jsonFixture = "{\"event\":\"opaque\"}\n{\"event\":\"opaque2\"}\n"

func TestStartResumeAndFork(t *testing.T) {
	fixture := []byte(jsonFixture)

	t.Run("fresh", func(t *testing.T) {
		client, dir, argsFile := fakeClient(t, fixture)
		client.Model = "anthropic/claude-3-5-sonnet-20241022"
		result, err := client.Start(context.Background(), "say ready")
		if err != nil {
			t.Fatal(err)
		}
		if !bytes.Equal(result.JSON, fixture) {
			t.Fatalf("result.JSON = %q", result.JSON)
		}
		args := readArgs(t, argsFile)
		assertContainsSequence(t, args, "run", "--dir", dir, "--format", "json")
		if contains(args, "--session") || contains(args, "--fork") {
			t.Fatalf("fresh args unexpectedly resume or fork: %q", args)
		}
		assertContainsSequence(t, args, "--model", "anthropic/claude-3-5-sonnet-20241022", "say ready")
		if last := args[len(args)-1]; last != "say ready" {
			t.Fatalf("prompt is not argv-last: %q", args)
		}
	})

	t.Run("model omitted when empty", func(t *testing.T) {
		client, _, argsFile := fakeClient(t, fixture)
		if _, err := client.Start(context.Background(), "x"); err != nil {
			t.Fatal(err)
		}
		if args := readArgs(t, argsFile); contains(args, "--model") {
			t.Fatalf("args unexpectedly carry --model: %q", args)
		}
	})

	t.Run("resume exact id", func(t *testing.T) {
		client, _, argsFile := fakeClient(t, fixture)
		if _, err := client.Resume(context.Background(), "ses-123", "continue"); err != nil {
			t.Fatal(err)
		}
		args := readArgs(t, argsFile)
		assertContainsSequence(t, args, "--format", "json", "--session", "ses-123")
		if contains(args, "--fork") || contains(args, "--continue") {
			t.Fatalf("resume unexpectedly forks or continues latest: %q", args)
		}
		if last := args[len(args)-1]; last != "continue" {
			t.Fatalf("prompt is not argv-last: %q", args)
		}
	})

	t.Run("fork", func(t *testing.T) {
		client, _, argsFile := fakeClient(t, fixture)
		if _, err := client.Fork(context.Background(), "ses-123", "branch"); err != nil {
			t.Fatal(err)
		}
		args := readArgs(t, argsFile)
		assertContainsSequence(t, args, "--session", "ses-123", "--fork")
	})
}

func TestStreamPassesThroughEvents(t *testing.T) {
	fixture := []byte(jsonFixture)
	client, _, argsFile := fakeClient(t, fixture)
	var output bytes.Buffer
	if err := client.Stream(context.Background(), "ses-1", true, "stream this", &output); err != nil {
		t.Fatal(err)
	}
	if !bytes.Equal(output.Bytes(), fixture) {
		t.Fatalf("stream output = %q, want %q", output.Bytes(), fixture)
	}
	args := readArgs(t, argsFile)
	assertContainsSequence(t, args, "--format", "json", "--session", "ses-1", "--fork")
	if last := args[len(args)-1]; last != "stream this" {
		t.Fatalf("prompt is not argv-last: %q", args)
	}
}

func TestListAndInspect(t *testing.T) {
	t.Run("list with limit", func(t *testing.T) {
		fixture := []byte("[{\"id\":\"ses-1\"}]\n")
		client, _, argsFile := fakeClient(t, fixture)
		got, err := client.List(context.Background(), 7)
		if err != nil {
			t.Fatal(err)
		}
		if !bytes.Equal(got, fixture) {
			t.Fatalf("list = %q, want %q", got, fixture)
		}
		args := readArgs(t, argsFile)
		assertContainsSequence(t, args, "session", "list", "--format", "json", "--max-count", "7")
	})

	t.Run("list without limit", func(t *testing.T) {
		client, _, argsFile := fakeClient(t, []byte("[]\n"))
		if _, err := client.List(context.Background(), 0); err != nil {
			t.Fatal(err)
		}
		if args := readArgs(t, argsFile); contains(args, "--max-count") {
			t.Fatalf("args unexpectedly limit: %q", args)
		}
	})

	t.Run("inspect export", func(t *testing.T) {
		fixture := []byte("{\"session\":\"ses-1\"}\n")
		client, _, argsFile := fakeClient(t, fixture)
		got, err := client.Inspect(context.Background(), "ses-1")
		if err != nil {
			t.Fatal(err)
		}
		if !bytes.Equal(got, fixture) {
			t.Fatalf("inspect = %q, want %q", got, fixture)
		}
		args := readArgs(t, argsFile)
		assertContainsSequence(t, args, "export", "ses-1", "--sanitize")
	})
}

func TestRefusesMissingValues(t *testing.T) {
	client, _, argsFile := fakeClient(t, []byte("{}\n"))
	if _, err := client.Resume(context.Background(), "", "prompt"); !errors.Is(err, ErrInvalidArgument) {
		t.Fatalf("Resume error = %v", err)
	}
	if _, err := client.Fork(context.Background(), "../x", "prompt"); !errors.Is(err, ErrInvalidArgument) {
		t.Fatalf("Fork bad id error = %v", err)
	}
	for _, id := range []string{"--last", "latest"} {
		if _, err := client.Resume(context.Background(), id, "prompt"); !errors.Is(err, ErrInvalidArgument) {
			t.Fatalf("Resume(%q) error = %v", id, err)
		}
	}
	if err := client.Stream(context.Background(), "", true, "prompt", &bytes.Buffer{}); !errors.Is(err, ErrInvalidArgument) {
		t.Fatalf("Stream error = %v", err)
	}
	if err := client.Stream(context.Background(), "--last", false, "prompt", &bytes.Buffer{}); !errors.Is(err, ErrInvalidArgument) {
		t.Fatalf("Stream option-like ID error = %v", err)
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

func fakeClient(t *testing.T, stdout []byte) (Client, string, string) {
	t.Helper()
	dir := t.TempDir()
	argsFile := filepath.Join(dir, "args.txt")
	stdoutFile := filepath.Join(dir, "stdout.txt")
	if err := os.WriteFile(stdoutFile, stdout, 0o600); err != nil {
		t.Fatal(err)
	}
	script := `#!/bin/sh
set -eu
: > "$FAKE_ARGS_FILE"
for arg in "$@"; do printf '%s\n' "$arg" >> "$FAKE_ARGS_FILE"; done
cat "$FAKE_STDOUT_FILE"
`
	binary := filepath.Join(dir, "opencode")
	if err := os.WriteFile(binary, []byte(script), 0o700); err != nil {
		t.Fatal(err)
	}
	t.Setenv("FAKE_ARGS_FILE", argsFile)
	t.Setenv("FAKE_STDOUT_FILE", stdoutFile)
	ws, err := filepath.Abs(dir)
	if err != nil {
		t.Fatal(err)
	}
	return Client{Binary: binary, WorkingDirectory: dir, Stderr: ioDiscard{}}, ws, argsFile
}

type ioDiscard struct{}

func (ioDiscard) Write(p []byte) (int, error) { return len(p), nil }

func readArgs(t *testing.T, path string) []string {
	t.Helper()
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	if len(data) == 0 {
		return nil
	}
	return strings.Split(strings.TrimSuffix(string(data), "\n"), "\n")
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
