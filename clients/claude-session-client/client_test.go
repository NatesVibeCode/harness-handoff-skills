package claudesession

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

const jsonFixture = `[{"type":"system","subtype":"init","session_id":"sess-1"},` +
	`{"type":"assistant","session_id":"sess-1"},` +
	`{"type":"result","subtype":"success","session_id":"sess-1","is_error":false,"result":"hello there"}]`

const errorFixture = `[{"type":"system","subtype":"init","session_id":"sess-9"},` +
	`{"type":"result","subtype":"error_max_turns","session_id":"sess-9","is_error":true,"result":"too many turns"}]`

func TestStartResumeAndFork(t *testing.T) {
	fixture := []byte(jsonFixture + "\n")

	t.Run("fresh", func(t *testing.T) {
		client, argsFile, stdinFile := fakeClient(t, fixture)
		result, err := client.Start(context.Background(), "say ready")
		if err != nil {
			t.Fatal(err)
		}
		if result.SessionID != "sess-1" || result.Text != "hello there" || !bytes.Equal(result.JSON, fixture) {
			t.Fatalf("result = %#v", result)
		}
		args := readArgs(t, argsFile)
		assertContainsSequence(t, args, "-p", "--output-format", "json")
		if contains(args, "--resume") || contains(args, "--fork-session") {
			t.Fatalf("fresh args unexpectedly resume or fork: %q", args)
		}
		if got := readFile(t, stdinFile); got != "say ready" {
			t.Fatalf("stdin prompt = %q", got)
		}
	})

	t.Run("resume exact id", func(t *testing.T) {
		client, argsFile, stdinFile := fakeClient(t, fixture)
		if _, err := client.Resume(context.Background(), "id-123", "continue"); err != nil {
			t.Fatal(err)
		}
		args := readArgs(t, argsFile)
		assertContainsSequence(t, args, "--resume", "id-123")
		if contains(args, "--fork-session") {
			t.Fatalf("resume unexpectedly forks: %q", args)
		}
		if got := readFile(t, stdinFile); got != "continue" {
			t.Fatalf("stdin prompt = %q", got)
		}
	})

	t.Run("fork", func(t *testing.T) {
		client, argsFile, _ := fakeClient(t, fixture)
		if _, err := client.Fork(context.Background(), "id-123", "branch"); err != nil {
			t.Fatal(err)
		}
		args := readArgs(t, argsFile)
		assertContainsSequence(t, args, "--resume", "id-123", "--fork-session")
	})
}

func TestStreamPassesThroughNDJSON(t *testing.T) {
	fixture := []byte("{\"fixture_event\":\"opaque\"}\n")
	client, argsFile, stdinFile := fakeClient(t, fixture)
	var output bytes.Buffer
	if err := client.Stream(context.Background(), "id-stream", true, "stream this", &output); err != nil {
		t.Fatal(err)
	}
	if !bytes.Equal(output.Bytes(), fixture) {
		t.Fatalf("stream output = %q, want %q", output.Bytes(), fixture)
	}
	args := readArgs(t, argsFile)
	assertContainsSequence(t, args, "--output-format", "stream-json", "--resume", "id-stream", "--fork-session")
	if got := readFile(t, stdinFile); got != "stream this" {
		t.Fatalf("stdin prompt = %q", got)
	}
}

func TestListAndInspect(t *testing.T) {
	setupStore := func(t *testing.T) Client {
		t.Helper()
		cfg := t.TempDir()
		t.Setenv("CLAUDE_CONFIG_DIR", cfg)
		work := t.TempDir()
		proj := filepath.Join(cfg, "projects", encodeForTest(t, work))
		if err := os.MkdirAll(proj, 0o755); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(filepath.Join(proj, "b-id.jsonl"), []byte("{\"b\":1}\n"), 0o600); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(filepath.Join(proj, "a-id.jsonl"), []byte("{\"a\":1}\n{\"a\":2}\n"), 0o600); err != nil {
			t.Fatal(err)
		}
		return Client{WorkingDirectory: work}
	}

	t.Run("list sorted by id", func(t *testing.T) {
		client := setupStore(t)
		entries, err := client.List(context.Background(), 0)
		if err != nil {
			t.Fatal(err)
		}
		if len(entries) != 2 || entries[0].ID != "a-id" || entries[1].ID != "b-id" {
			t.Fatalf("entries = %#v", entries)
		}
		if entries[0].Size == 0 || entries[0].Modified == "" {
			t.Fatalf("entry missing metadata: %#v", entries[0])
		}
	})

	t.Run("list limit", func(t *testing.T) {
		client := setupStore(t)
		entries, err := client.List(context.Background(), 1)
		if err != nil {
			t.Fatal(err)
		}
		if len(entries) != 1 || entries[0].ID != "a-id" {
			t.Fatalf("entries = %#v", entries)
		}
	})

	t.Run("list empty store", func(t *testing.T) {
		cfg := t.TempDir()
		t.Setenv("CLAUDE_CONFIG_DIR", cfg)
		client := Client{WorkingDirectory: t.TempDir()}
		entries, err := client.List(context.Background(), 0)
		if err != nil {
			t.Fatal(err)
		}
		if len(entries) != 0 {
			t.Fatalf("entries = %#v", entries)
		}
	})

	t.Run("inspect transcript", func(t *testing.T) {
		client := setupStore(t)
		got, err := client.Inspect(context.Background(), "a-id")
		if err != nil {
			t.Fatal(err)
		}
		if want := "{\"a\":1}\n{\"a\":2}\n"; string(got) != want {
			t.Fatalf("inspect = %q, want %q", got, want)
		}
	})

	t.Run("inspect rejects bad ids", func(t *testing.T) {
		client := setupStore(t)
		for _, id := range []string{"", "../x", "a/b", "a.jsonl", strings.Repeat("a", 129)} {
			if _, err := client.Inspect(context.Background(), id); !errors.Is(err, ErrInvalidArgument) {
				t.Fatalf("Inspect(%q) error = %v", id, err)
			}
		}
	})

	t.Run("inspect missing file", func(t *testing.T) {
		client := setupStore(t)
		if _, err := client.Inspect(context.Background(), "nope"); err == nil {
			t.Fatal("expected error for missing transcript")
		}
	})
}

func TestProjectDirEncoding(t *testing.T) {
	cfg := t.TempDir()
	t.Setenv("CLAUDE_CONFIG_DIR", cfg)
	client := Client{WorkingDirectory: string([]byte("/x y/z"))}
	dir, err := client.projectDir()
	if err != nil {
		t.Fatal(err)
	}
	if want := filepath.Join(cfg, "projects", "-x-y-z"); dir != want {
		t.Fatalf("projectDir = %q, want %q", dir, want)
	}
}

func TestProjectDirResolvesSymlinks(t *testing.T) {
	cfg := t.TempDir()
	t.Setenv("CLAUDE_CONFIG_DIR", cfg)
	real := t.TempDir()
	link := filepath.Join(t.TempDir(), "link")
	if err := os.Symlink(real, link); err != nil {
		t.Fatal(err)
	}
	a, err := Client{WorkingDirectory: real}.projectDir()
	if err != nil {
		t.Fatal(err)
	}
	b, err := Client{WorkingDirectory: link}.projectDir()
	if err != nil {
		t.Fatal(err)
	}
	if a != b {
		t.Fatalf("symlinked workdir resolves differently: %q vs %q", a, b)
	}
}

func TestRefusesMissingIdentifiers(t *testing.T) {
	client, argsFile, _ := fakeClient(t, []byte("{}\n"))
	if _, err := client.Resume(context.Background(), "", "prompt"); !errors.Is(err, ErrInvalidArgument) {
		t.Fatalf("Resume error = %v", err)
	}
	if _, err := client.Fork(context.Background(), "", "prompt"); !errors.Is(err, ErrInvalidArgument) {
		t.Fatalf("Fork error = %v", err)
	}
	if err := client.Stream(context.Background(), "", true, "prompt", &bytes.Buffer{}); !errors.Is(err, ErrInvalidArgument) {
		t.Fatalf("Stream error = %v", err)
	}
	if err := client.Stream(context.Background(), "", false, "prompt", nil); !errors.Is(err, ErrInvalidArgument) {
		t.Fatalf("Stream nil writer error = %v", err)
	}
	if _, err := client.Start(context.Background(), ""); !errors.Is(err, ErrInvalidArgument) {
		t.Fatalf("Start error = %v", err)
	}
	if _, err := os.Stat(argsFile); !errors.Is(err, os.ErrNotExist) {
		t.Fatalf("invalid call invoked CLI; args file stat error = %v", err)
	}
}

func TestRejectsErrorAndMissingResults(t *testing.T) {
	client, _, _ := fakeClient(t, []byte(errorFixture+"\n"))
	if _, err := client.Start(context.Background(), "x"); err == nil || !strings.Contains(err.Error(), "error_max_turns") {
		t.Fatalf("Start error = %v", err)
	}

	client, _, _ = fakeClient(t, []byte("[{\"type\":\"system\",\"subtype\":\"init\"}]\n"))
	if _, err := client.Start(context.Background(), "x"); !errors.Is(err, ErrNoResult) {
		t.Fatalf("Start error = %v", err)
	}

	client, _, _ = fakeClient(t, []byte("not json\n"))
	if _, err := client.Start(context.Background(), "x"); err == nil || !strings.Contains(err.Error(), "decode") {
		t.Fatalf("Start error = %v", err)
	}
}

func encodeForTest(t *testing.T, work string) string {
	t.Helper()
	resolved, err := filepath.EvalSymlinks(work)
	if err != nil {
		t.Fatal(err)
	}
	var b strings.Builder
	for i := 0; i < len(resolved); i++ {
		ch := resolved[i]
		if ch >= 'a' && ch <= 'z' || ch >= 'A' && ch <= 'Z' || ch >= '0' && ch <= '9' {
			b.WriteByte(ch)
		} else {
			b.WriteByte('-')
		}
	}
	return b.String()
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
cat > "$FAKE_STDIN_FILE"
cat "$FAKE_STDOUT_FILE"
`
	binary := filepath.Join(dir, "claude")
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
