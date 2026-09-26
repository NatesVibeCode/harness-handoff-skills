package codexsession

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"reflect"
	"strings"
	"testing"
)

const jsonFixture = "{\"type\":\"thread.started\",\"thread_id\":\"thr-1\"}\n" +
	"{\"type\":\"turn.started\"}\n" +
	"{\"type\":\"item.completed\",\"item\":{\"id\":\"item_0\",\"type\":\"agent_message\",\"text\":\"hello there\"}}\n" +
	"{\"type\":\"turn.completed\",\"usage\":{\"input_tokens\":10,\"output_tokens\":3}}\n"

const failFixture = "{\"type\":\"thread.started\",\"thread_id\":\"thr-9\"}\n" +
	"{\"type\":\"turn.failed\",\"message\":\"boom\"}\n"

func TestStartResumeAndFork(t *testing.T) {
	fixture := []byte(jsonFixture)

	t.Run("fresh", func(t *testing.T) {
		client, dir, argsFile, stdinFile := fakeClient(t, fixture)
		result, err := client.Start(context.Background(), "say ready")
		if err != nil {
			t.Fatal(err)
		}
		if result.SessionID != "thr-1" || result.Text != "hello there" || !bytes.Equal(result.JSON, fixture) {
			t.Fatalf("result = %#v", result)
		}
		args := readArgs(t, argsFile)
		assertContainsSequence(t, args, "exec", "-C", dir, "-c", `sandbox_mode="workspace-write"`, "-c", `approval_policy="never"`, "--json", "-")
		if contains(args, "--skip-git-repo-check") {
			t.Fatalf("fresh args bypass Git check by default: %q", args)
		}
		if contains(args, "resume") || contains(args, "fork") {
			t.Fatalf("fresh args unexpectedly resume or fork: %q", args)
		}
		if got := readFile(t, stdinFile); got != "say ready" {
			t.Fatalf("stdin prompt = %q", got)
		}
	})

	t.Run("fresh without workdir omits -C", func(t *testing.T) {
		client, _, argsFile, _ := fakeClient(t, fixture)
		client.WorkingDirectory = ""
		if _, err := client.Start(context.Background(), "x"); err != nil {
			t.Fatal(err)
		}
		if args := readArgs(t, argsFile); contains(args, "-C") {
			t.Fatalf("args unexpectedly carry -C: %q", args)
		}
	})

	t.Run("Git check bypass is explicit", func(t *testing.T) {
		client, _, argsFile, _ := fakeClient(t, fixture)
		client.SkipGitRepoCheck = true
		if _, err := client.Start(context.Background(), "x"); err != nil {
			t.Fatal(err)
		}
		if args := readArgs(t, argsFile); !contains(args, "--skip-git-repo-check") {
			t.Fatalf("opted-in Git check bypass missing: %q", args)
		}
	})

	t.Run("resume exact id", func(t *testing.T) {
		client, _, argsFile, stdinFile := fakeClient(t, fixture)
		if _, err := client.Resume(context.Background(), "id-123", "continue"); err != nil {
			t.Fatal(err)
		}
		args := readArgs(t, argsFile)
		assertContainsSequence(t, args, "exec", "resume", "id-123", "-c", `sandbox_mode="workspace-write"`, "-c", `approval_policy="never"`, "--json", "-")
		if contains(args, "fork") {
			t.Fatalf("resume unexpectedly forks: %q", args)
		}
		if got := readFile(t, stdinFile); got != "continue" {
			t.Fatalf("stdin prompt = %q", got)
		}
	})

	t.Run("fork", func(t *testing.T) {
		client, _, argsFile, _ := fakeClient(t, fixture)
		if _, err := client.Fork(context.Background(), "id-123", "branch"); err != nil {
			t.Fatal(err)
		}
		args := readArgs(t, argsFile)
		assertContainsSequence(t, args, "exec", "fork", "id-123", "-c", `sandbox_mode="workspace-write"`, "-c", `approval_policy="never"`, "--json", "-")
	})
}

func TestStreamPassesThroughJSONL(t *testing.T) {
	fixture := []byte("{\"fixture_event\":\"opaque\"}\n")
	client, _, argsFile, stdinFile := fakeClient(t, fixture)
	var output bytes.Buffer
	if err := client.Stream(context.Background(), "id-stream", true, "stream this", &output); err != nil {
		t.Fatal(err)
	}
	if !bytes.Equal(output.Bytes(), fixture) {
		t.Fatalf("stream output = %q, want %q", output.Bytes(), fixture)
	}
	args := readArgs(t, argsFile)
	assertContainsSequence(t, args, "exec", "fork", "id-stream", "-c", `sandbox_mode="workspace-write"`, "-c", `approval_policy="never"`, "--json", "-")
	if got := readFile(t, stdinFile); got != "stream this" {
		t.Fatalf("stdin prompt = %q", got)
	}
}

func TestListAndInspect(t *testing.T) {
	setupStore := func(t *testing.T) Client {
		t.Helper()
		home := t.TempDir()
		t.Setenv("CODEX_HOME", home)
		work := t.TempDir()
		sess := filepath.Join(home, "sessions", "2026", "09", "25")
		if err := os.MkdirAll(sess, 0o755); err != nil {
			t.Fatal(err)
		}
		write := func(name, id, cwd string, roots []string) {
			meta := `{"type":"session_meta","payload":{"id":"` + id + `","session_id":"` + id +
				`","cwd":"` + cwd + `","runtime_workspace_roots":["` + strings.Join(roots, `","`) + `"]}}` + "\n"
			if err := os.WriteFile(filepath.Join(sess, name), []byte(meta+"{\"type\":\"response_item\"}\n"), 0o600); err != nil {
				t.Fatal(err)
			}
		}
		write("rollout-x-b-id.jsonl", "b-id", work, []string{work})
		write("rollout-x-a-id.jsonl", "a-id", work, []string{work})
		write("rollout-x-r-id.jsonl", "r-id", "/elsewhere", []string{work})
		write("rollout-x-elsewhere.jsonl", "z-id", "/elsewhere", []string{"/elsewhere"})
		if err := os.WriteFile(filepath.Join(sess, "notes.txt"), []byte("ignore me"), 0o600); err != nil {
			t.Fatal(err)
		}
		return Client{WorkingDirectory: work}
	}

	t.Run("list workspace sessions sorted", func(t *testing.T) {
		client := setupStore(t)
		entries, err := client.List(context.Background(), 0)
		if err != nil {
			t.Fatal(err)
		}
		var ids []string
		for _, e := range entries {
			ids = append(ids, e.ID)
		}
		if want := []string{"a-id", "b-id", "r-id"}; !reflect.DeepEqual(ids, want) {
			t.Fatalf("ids = %q, want %q", ids, want)
		}
		if entries[0].Size == 0 || entries[0].Modified == "" || entries[0].Cwd == "" {
			t.Fatalf("entry missing metadata: %#v", entries[0])
		}
	})

	t.Run("list limit", func(t *testing.T) {
		client := setupStore(t)
		entries, err := client.List(context.Background(), 2)
		if err != nil {
			t.Fatal(err)
		}
		if len(entries) != 2 {
			t.Fatalf("entries = %#v", entries)
		}
	})

	t.Run("list missing store", func(t *testing.T) {
		home := t.TempDir()
		t.Setenv("CODEX_HOME", home)
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
		collision := filepath.Join(os.Getenv("CODEX_HOME"), "sessions", "2026", "09", "25", "rollout-x-a-id-0.jsonl")
		if err := os.WriteFile(collision, []byte("{\"type\":\"session_meta\",\"payload\":{\"session_id\":\"wrong-id\"}}\n"), 0o600); err != nil {
			t.Fatal(err)
		}
		got, err := client.Inspect(context.Background(), "a-id")
		if err != nil {
			t.Fatal(err)
		}
		if !strings.Contains(string(got), `"session_id":"a-id"`) {
			t.Fatalf("inspect = %q", got)
		}
	})

	t.Run("inspect rejects bad ids", func(t *testing.T) {
		client := setupStore(t)
		for _, id := range []string{"", "../x", "a/b", strings.Repeat("a", 129)} {
			if _, err := client.Inspect(context.Background(), id); !errors.Is(err, ErrInvalidArgument) {
				t.Fatalf("Inspect(%q) error = %v", id, err)
			}
		}
	})

	t.Run("inspect missing session", func(t *testing.T) {
		client := setupStore(t)
		if _, err := client.Inspect(context.Background(), "nope"); !errors.Is(err, ErrSessionNotFound) {
			t.Fatalf("Inspect error = %v", err)
		}
		if _, err := client.Inspect(context.Background(), "z-id"); !errors.Is(err, ErrSessionNotFound) {
			t.Fatalf("out-of-workspace Inspect error = %v", err)
		}
	})

	t.Run("inspect ignores symlinked transcript", func(t *testing.T) {
		client := setupStore(t)
		outside := filepath.Join(t.TempDir(), "outside.jsonl")
		if err := os.WriteFile(outside, []byte("{\"type\":\"session_meta\",\"payload\":{\"session_id\":\"outside-id\"}}\n"), 0o600); err != nil {
			t.Fatal(err)
		}
		link := filepath.Join(os.Getenv("CODEX_HOME"), "sessions", "2026", "09", "25", "linked.jsonl")
		if err := os.Symlink(outside, link); err != nil {
			t.Fatal(err)
		}
		if _, err := client.Inspect(context.Background(), "outside-id"); !errors.Is(err, ErrSessionNotFound) {
			t.Fatalf("symlinked Inspect error = %v", err)
		}
	})
}

func TestListHasNoImplicitSessionCountCap(t *testing.T) {
	home := t.TempDir()
	t.Setenv("CODEX_HOME", home)
	work := t.TempDir()
	store := filepath.Join(home, "sessions")
	if err := os.MkdirAll(store, 0o700); err != nil {
		t.Fatal(err)
	}
	for i := 0; i < 5001; i++ {
		path := filepath.Join(store, fmt.Sprintf("session-%04d.jsonl", i))
		body := fmt.Sprintf("{\"type\":\"session_meta\",\"payload\":{\"session_id\":\"id-%04d\",\"cwd\":%q}}\n", i, work)
		if err := os.WriteFile(path, []byte(body), 0o600); err != nil {
			t.Fatal(err)
		}
	}
	got, err := (Client{WorkingDirectory: work}).List(context.Background(), 0)
	if err != nil {
		t.Fatal(err)
	}
	if len(got) != 5001 {
		t.Fatalf("got %d sessions, want 5001", len(got))
	}
}

func TestRefusesMissingIdentifiers(t *testing.T) {
	client, _, argsFile, _ := fakeClient(t, []byte("{}\n"))
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
		if _, err := client.Fork(context.Background(), id, "prompt"); !errors.Is(err, ErrInvalidArgument) {
			t.Fatalf("Fork(%q) error = %v", id, err)
		}
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

func TestRejectsFailedAndMissingThreads(t *testing.T) {
	client, _, _, _ := fakeClient(t, []byte(failFixture))
	if _, err := client.Start(context.Background(), "x"); err == nil || !strings.Contains(err.Error(), "turn.failed") {
		t.Fatalf("Start error = %v", err)
	}

	client, _, _, _ = fakeClient(t, []byte("{\"type\":\"turn.started\"}\n"))
	if _, err := client.Start(context.Background(), "x"); !errors.Is(err, ErrNoThread) {
		t.Fatalf("Start error = %v", err)
	}

	client, _, _, _ = fakeClient(t, []byte("not json\n"))
	if _, err := client.Start(context.Background(), "x"); err == nil || !strings.Contains(err.Error(), "decode") {
		t.Fatalf("Start error = %v", err)
	}
}

func fakeClient(t *testing.T, stdout []byte) (Client, string, string, string) {
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
	binary := filepath.Join(dir, "codex")
	if err := os.WriteFile(binary, []byte(script), 0o700); err != nil {
		t.Fatal(err)
	}
	t.Setenv("FAKE_ARGS_FILE", argsFile)
	t.Setenv("FAKE_STDIN_FILE", stdinFile)
	t.Setenv("FAKE_STDOUT_FILE", stdoutFile)
	return Client{Binary: binary, WorkingDirectory: dir, Stderr: ioDiscard{}}, dir, argsFile, stdinFile
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
