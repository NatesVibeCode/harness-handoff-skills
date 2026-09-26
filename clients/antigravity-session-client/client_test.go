package antigravitysession

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"reflect"
	"strings"
	"testing"
)

const jsonFixture = "{\"conversation_id\":\"conv-1\",\"status\":\"SUCCESS\"," +
	"\"response\":\"hello there\",\"error\":\"\",\"duration_seconds\":3," +
	"\"num_turns\":1,\"usage\":{}}\n"

const errorFixture = "{\"conversation_id\":\"conv-9\",\"status\":\"ERROR\"," +
	"\"response\":\"\",\"error\":\"tool denied\"}\n"

func TestStartAndResume(t *testing.T) {
	fixture := []byte(jsonFixture)

	t.Run("fresh", func(t *testing.T) {
		client, argsFile, _ := fakeClient(t, fixture)
		result, err := client.Start(context.Background(), "say ready")
		if err != nil {
			t.Fatal(err)
		}
		if result.SessionID != "conv-1" || result.Text != "hello there" || !bytes.Equal(result.JSON, fixture) {
			t.Fatalf("result = %#v", result)
		}
		args := readArgs(t, argsFile)
		assertContainsSequence(t, args, "--output-format", "json", "--print", "say ready")
		if contains(args, "--conversation") {
			t.Fatalf("fresh args unexpectedly resume: %q", args)
		}
	})

	t.Run("resume exact id", func(t *testing.T) {
		client, argsFile, _ := fakeClient(t, fixture)
		if _, err := client.Resume(context.Background(), "conv-123", "continue"); err != nil {
			t.Fatal(err)
		}
		args := readArgs(t, argsFile)
		assertContainsSequence(t, args, "--print", "continue", "--conversation", "conv-123")
	})
}

func TestStreamWritesUserFrame(t *testing.T) {
	fixture := []byte("{\"event\":\"result\"}\n")
	client, argsFile, stdinFile := fakeClient(t, fixture)
	var output bytes.Buffer
	if err := client.Stream(context.Background(), "conv-1", "stream this", &output); err != nil {
		t.Fatal(err)
	}
	if !bytes.Equal(output.Bytes(), fixture) {
		t.Fatalf("stream output = %q, want %q", output.Bytes(), fixture)
	}
	args := readArgs(t, argsFile)
	assertContainsSequence(t, args, "--input-format", "stream-json", "--output-format", "stream-json", "--conversation", "conv-1")
	var frame struct {
		Event   string `json:"event"`
		Message struct {
			Content string `json:"content"`
		} `json:"message"`
	}
	if err := json.Unmarshal([]byte(readFile(t, stdinFile)), &frame); err != nil {
		t.Fatalf("stdin is not a user frame: %v", err)
	}
	if frame.Event != "user" || frame.Message.Content != "stream this" {
		t.Fatalf("frame = %#v", frame)
	}
}

func TestUnsupportedOperations(t *testing.T) {
	client, argsFile, _ := fakeClient(t, []byte("{}\n"))
	if _, err := client.Fork(context.Background(), "x", "y"); !errors.Is(err, ErrUnsupported) {
		t.Fatalf("Fork error = %v", err)
	}
	if _, err := client.List(context.Background()); !errors.Is(err, ErrUnsupported) {
		t.Fatalf("List error = %v", err)
	}
	if _, err := client.Inspect(context.Background(), "x"); !errors.Is(err, ErrUnsupported) {
		t.Fatalf("Inspect error = %v", err)
	}
	if _, err := os.Stat(argsFile); !errors.Is(err, os.ErrNotExist) {
		t.Fatalf("unsupported call invoked CLI; args file stat error = %v", err)
	}
}

func TestRefusesMissingValues(t *testing.T) {
	client, argsFile, _ := fakeClient(t, []byte("{}\n"))
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

func TestRejectsErrorAndMissingConversations(t *testing.T) {
	client, _, _ := fakeClient(t, []byte(errorFixture))
	if _, err := client.Start(context.Background(), "x"); err == nil || !strings.Contains(err.Error(), "ERROR") {
		t.Fatalf("Start error = %v", err)
	}

	client, _, _ = fakeClient(t, []byte("{\"status\":\"SUCCESS\"}\n"))
	if _, err := client.Start(context.Background(), "x"); !errors.Is(err, ErrNoConversation) {
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
	stdinFile := filepath.Join(dir, "stdin.txt")
	stdoutFile := filepath.Join(dir, "stdout.txt")
	if err := os.WriteFile(stdoutFile, stdout, 0o600); err != nil {
		t.Fatal(err)
	}
	script := `#!/bin/sh
set -eu
: > "$FAKE_ARGS_FILE"
for arg in "$@"; do printf '%s\n' "$arg" >> "$FAKE_ARGS_FILE"; done
if [ ! -t 0 ]; then cat > "$FAKE_STDIN_FILE"; fi
cat "$FAKE_STDOUT_FILE"
`
	binary := filepath.Join(dir, "agy")
	if err := os.WriteFile(binary, []byte(script), 0o700); err != nil {
		t.Fatal(err)
	}
	t.Setenv("FAKE_ARGS_FILE", argsFile)
	t.Setenv("FAKE_STDIN_FILE", stdinFile)
	t.Setenv("FAKE_STDOUT_FILE", stdoutFile)
	return Client{Binary: binary, WorkingDirectory: dir, Stderr: ioDiscard{}}, argsFile, stdinFile
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
