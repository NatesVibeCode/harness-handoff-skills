package cursorsession

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

const jsonFixture = "{\"type\":\"result\",\"subtype\":\"success\",\"is_error\":false," +
	"\"duration_ms\":12,\"duration_api_ms\":12,\"result\":\"hello there\"," +
	"\"session_id\":\"sess-1\",\"request_id\":\"req-1\"}\n"

const errorFixture = "{\"type\":\"result\",\"subtype\":\"failure\",\"is_error\":true," +
	"\"result\":\"bad run\",\"session_id\":\"sess-9\"}\n"

func TestStartAndResume(t *testing.T) {
	fixture := []byte(jsonFixture)

	t.Run("fresh", func(t *testing.T) {
		client, dir, argsFile := fakeClient(t, fixture)
		client.Model = "composer-2.5"
		result, err := client.Start(context.Background(), "say ready")
		if err != nil {
			t.Fatal(err)
		}
		if result.SessionID != "sess-1" || result.Text != "hello there" || !bytes.Equal(result.JSON, fixture) {
			t.Fatalf("result = %#v", result)
		}
		args := readArgs(t, argsFile)
		assertContainsSequence(t, args, "--workspace", dir, "--sandbox", "enabled", "--print", "--output-format", "json")
		if contains(args, "--resume") {
			t.Fatalf("fresh args unexpectedly resume: %q", args)
		}
		assertContainsSequence(t, args, "--model", "composer-2.5", "say ready")
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
		if _, err := client.Resume(context.Background(), "chat-123", "continue"); err != nil {
			t.Fatal(err)
		}
		args := readArgs(t, argsFile)
		assertContainsSequence(t, args, "--print", "--output-format", "json", "--resume", "chat-123")
		if contains(args, "--continue") {
			t.Fatalf("resume unexpectedly continues latest: %q", args)
		}
		if last := args[len(args)-1]; last != "continue" {
			t.Fatalf("prompt is not argv-last: %q", args)
		}
	})
}

func TestStreamPassesThroughNDJSON(t *testing.T) {
	fixture := []byte("{\"fixture_event\":\"opaque\"}\n")
	client, _, argsFile := fakeClient(t, fixture)
	client.PartialOutput = true
	var output bytes.Buffer
	if err := client.Stream(context.Background(), "chat-1", "stream this", &output); err != nil {
		t.Fatal(err)
	}
	if !bytes.Equal(output.Bytes(), fixture) {
		t.Fatalf("stream output = %q, want %q", output.Bytes(), fixture)
	}
	args := readArgs(t, argsFile)
	assertContainsSequence(t, args, "--output-format", "stream-json", "--resume", "chat-1", "--stream-partial-output")
	if last := args[len(args)-1]; last != "stream this" {
		t.Fatalf("prompt is not argv-last: %q", args)
	}
}

func TestListPassesThrough(t *testing.T) {
	fixture := []byte("chat-1 recent task\n")
	client, _, argsFile := fakeClient(t, fixture)
	got, err := client.List(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if !bytes.Equal(got, fixture) {
		t.Fatalf("list = %q, want %q", got, fixture)
	}
	args := readArgs(t, argsFile)
	if len(args) != 3 || args[0] != "--workspace" || !filepath.IsAbs(args[1]) || args[2] != "ls" {
		t.Fatalf("args = %q, want [--workspace <absdir> ls]", args)
	}
}

func TestUnsupportedOperations(t *testing.T) {
	client, _, argsFile := fakeClient(t, []byte("{}\n"))
	if _, err := client.Fork(context.Background(), "x", "y"); !errors.Is(err, ErrUnsupported) {
		t.Fatalf("Fork error = %v", err)
	}
	if _, err := client.Inspect(context.Background(), "x"); !errors.Is(err, ErrUnsupported) {
		t.Fatalf("Inspect error = %v", err)
	}
	if _, err := os.Stat(argsFile); !errors.Is(err, os.ErrNotExist) {
		t.Fatalf("unsupported call invoked CLI; args file stat error = %v", err)
	}
}

func TestRefusesMissingValues(t *testing.T) {
	client, _, argsFile := fakeClient(t, []byte("{}\n"))
	if _, err := client.Resume(context.Background(), "", "prompt"); !errors.Is(err, ErrInvalidArgument) {
		t.Fatalf("Resume error = %v", err)
	}
	for _, id := range []string{"--last", "latest", "../other"} {
		if _, err := client.Resume(context.Background(), id, "prompt"); !errors.Is(err, ErrInvalidArgument) {
			t.Fatalf("Resume(%q) error = %v", id, err)
		}
	}
	if _, err := client.Start(context.Background(), ""); !errors.Is(err, ErrInvalidArgument) {
		t.Fatalf("Start error = %v", err)
	}
	if err := client.Stream(context.Background(), "", "prompt", nil); !errors.Is(err, ErrInvalidArgument) {
		t.Fatalf("Stream nil writer error = %v", err)
	}
	if _, err := os.Stat(argsFile); !errors.Is(err, os.ErrNotExist) {
		t.Fatalf("invalid call invoked CLI; args file stat error = %v", err)
	}
}

func TestRejectsErrorAndMalformedResults(t *testing.T) {
	client, _, _ := fakeClient(t, []byte(errorFixture))
	if _, err := client.Start(context.Background(), "x"); err == nil || !strings.Contains(err.Error(), "failure") {
		t.Fatalf("Start error = %v", err)
	}

	client, _, _ = fakeClient(t, []byte("{\"type\":\"system\"}\n"))
	if _, err := client.Start(context.Background(), "x"); !errors.Is(err, ErrNoResult) {
		t.Fatalf("Start error = %v", err)
	}

	client, _, _ = fakeClient(t, []byte("not json\n"))
	if _, err := client.Start(context.Background(), "x"); err == nil || !strings.Contains(err.Error(), "decode") {
		t.Fatalf("Start error = %v", err)
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
	binary := filepath.Join(dir, "cursor-agent")
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
