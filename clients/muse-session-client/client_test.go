package musesession

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

func TestStartAndResume(t *testing.T) {
	fixture := []byte(jsonFixture)

	t.Run("fresh", func(t *testing.T) {
		client, dir, argsFile, promptFile := fakeClient(t, fixture, "")
		result, err := client.Start(context.Background(), "say ready")
		if err != nil {
			t.Fatal(err)
		}
		if !bytes.Equal(result.JSON, fixture) {
			t.Fatalf("result.JSON = %q", result.JSON)
		}
		args := readArgs(t, argsFile)
		assertContainsSequence(t, args, "exec", "--json", "--workspace", dir, "--worktree", "off", "--prompt-file")
		if contains(args, "--session-id") {
			t.Fatalf("fresh args unexpectedly resume: %q", args)
		}
		if got := readFile(t, promptFile); got != "say ready" {
			t.Fatalf("prompt file = %q", got)
		}
	})

	t.Run("resume refused", func(t *testing.T) {
		client, _, argsFile, _ := fakeClient(t, fixture, "")
		if _, err := client.Resume(context.Background(), "sess-123", "continue"); !errors.Is(err, ErrUnsupported) {
			t.Fatalf("Resume error = %v, want ErrUnsupported", err)
		}
		if _, err := os.Stat(argsFile); !errors.Is(err, os.ErrNotExist) {
			t.Fatalf("refused resume invoked CLI; args file stat error = %v", err)
		}
	})
}

func TestStreamPassesThroughJSONL(t *testing.T) {
	fixture := []byte(jsonFixture)
	client, dir, argsFile, _ := fakeClient(t, fixture, "")
	var output bytes.Buffer
	if err := client.Stream(context.Background(), "", "stream this", &output); err != nil {
		t.Fatal(err)
	}
	if !bytes.Equal(output.Bytes(), fixture) {
		t.Fatalf("stream output = %q, want %q", output.Bytes(), fixture)
	}
	args := readArgs(t, argsFile)
	assertContainsSequence(t, args, "exec", "--json", "--workspace", dir, "--worktree", "off", "--prompt-file")
	if contains(args, "--session-id") {
		t.Fatalf("fresh stream unexpectedly resumes: %q", args)
	}
}

func TestStreamRefusesSessionID(t *testing.T) {
	client, _, argsFile, _ := fakeClient(t, []byte(jsonFixture), "")
	var output bytes.Buffer
	if err := client.Stream(context.Background(), "sess-1", "stream this", &output); !errors.Is(err, ErrUnsupported) {
		t.Fatalf("Stream error = %v, want ErrUnsupported", err)
	}
	if _, err := os.Stat(argsFile); !errors.Is(err, os.ErrNotExist) {
		t.Fatalf("refused stream invoked CLI; args file stat error = %v", err)
	}
}

func TestInspectReadsExportFile(t *testing.T) {
	export := []byte("{\"export\":\"document\"}\n")
	client, _, argsFile, _ := fakeClient(t, nil, string(export))
	got, err := client.Inspect(context.Background(), "sess-1")
	if err != nil {
		t.Fatal(err)
	}
	if !bytes.Equal(got, export) {
		t.Fatalf("inspect = %q, want %q", got, export)
	}
	args := readArgs(t, argsFile)
	assertContainsSequence(t, args, "export", "--session", "sess-1", "--out")
	if !contains(args, "--redacted") {
		t.Fatalf("export args miss --redacted: %q", args)
	}
	// the temporary export path must be cleaned up
	idx := indexOf(args, "--out")
	if idx < 0 || idx+1 >= len(args) {
		t.Fatalf("no --out path in args: %q", args)
	}
	if _, err := os.Stat(args[idx+1]); !errors.Is(err, os.ErrNotExist) {
		t.Fatalf("export file not removed; stat error = %v", err)
	}
}

func TestUnsupportedOperations(t *testing.T) {
	client, _, argsFile, _ := fakeClient(t, []byte("{}\n"), "")
	if _, err := client.Fork(context.Background(), "x", "y"); !errors.Is(err, ErrUnsupported) {
		t.Fatalf("Fork error = %v", err)
	}
	if _, err := client.List(context.Background()); !errors.Is(err, ErrUnsupported) {
		t.Fatalf("List error = %v", err)
	}
	if _, err := os.Stat(argsFile); !errors.Is(err, os.ErrNotExist) {
		t.Fatalf("unsupported call invoked CLI; args file stat error = %v", err)
	}
}

func TestRefusesMissingValues(t *testing.T) {
	client, _, argsFile, _ := fakeClient(t, []byte("{}\n"), "")
	if _, err := client.Resume(context.Background(), "", "prompt"); !errors.Is(err, ErrInvalidArgument) {
		t.Fatalf("Resume error = %v", err)
	}
	if _, err := client.Resume(context.Background(), "../x", "prompt"); !errors.Is(err, ErrInvalidArgument) {
		t.Fatalf("Resume bad id error = %v", err)
	}
	for _, id := range []string{"--last", "latest"} {
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
	if _, err := client.Inspect(context.Background(), ""); !errors.Is(err, ErrInvalidArgument) {
		t.Fatalf("Inspect error = %v", err)
	}
	if _, err := os.Stat(argsFile); !errors.Is(err, os.ErrNotExist) {
		t.Fatalf("invalid call invoked CLI; args file stat error = %v", err)
	}
}

// fakeClient installs a fake muse binary. stdout is served for exec calls;
// exportBody, when non-empty, is written to the --out path for export calls.
func fakeClient(t *testing.T, stdout []byte, exportBody string) (Client, string, string, string) {
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
  if [ "$previous" = "--out" ]; then
    printf '%s' "$FAKE_EXPORT_BODY" > "$arg"
  fi
  previous=$arg
done
cat "$FAKE_STDOUT_FILE"
`
	binary := filepath.Join(dir, "muse")
	if err := os.WriteFile(binary, []byte(script), 0o700); err != nil {
		t.Fatal(err)
	}
	t.Setenv("FAKE_ARGS_FILE", argsFile)
	t.Setenv("FAKE_PROMPT_FILE", promptFile)
	t.Setenv("FAKE_STDOUT_FILE", stdoutFile)
	t.Setenv("FAKE_EXPORT_BODY", exportBody)
	ws, err := filepath.Abs(dir)
	if err != nil {
		t.Fatal(err)
	}
	return Client{Binary: binary, WorkingDirectory: dir, Stderr: ioDiscard{}}, ws, argsFile, promptFile
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

func indexOf(values []string, want string) int {
	for i, value := range values {
		if value == want {
			return i
		}
	}
	return -1
}
