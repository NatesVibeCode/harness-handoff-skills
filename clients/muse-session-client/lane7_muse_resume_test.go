package musesession

import (
	"bytes"
	"context"
	"errors"
	"os"
	"testing"
)

// Resume is refused without invoking the CLI: exec --session-id does not
// resume history and muse resume is interactive-only, so no documented
// headless resume-with-prompt exists.
func TestLane7ResumeIsUnsupported(t *testing.T) {
	client, _, argsFile, _ := fakeClient(t, []byte(jsonFixture), "")
	if _, err := client.Resume(context.Background(), "sess-123", "continue"); !errors.Is(err, ErrUnsupported) {
		t.Fatalf("Resume error = %v", err)
	}
	if _, err := os.Stat(argsFile); !errors.Is(err, os.ErrNotExist) {
		t.Fatalf("refused Resume invoked CLI; args file stat error = %v", err)
	}
}

// Resumed Stream is refused the same way; fresh Stream pins the
// session-id-free argv and passes JSONL through.
func TestLane7StreamFreshOnly(t *testing.T) {
	fixture := []byte(jsonFixture)
	client, dir, argsFile, _ := fakeClient(t, fixture, "")
	if err := client.Stream(context.Background(), "sess-1", "stream this", &bytes.Buffer{}); !errors.Is(err, ErrUnsupported) {
		t.Fatalf("resumed Stream error = %v", err)
	}
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
		t.Fatalf("fresh stream args unexpectedly carry --session-id: %q", args)
	}
}

// Start pins the fresh exec argv: --session-id must never appear.
func TestLane7StartPinsFreshArgv(t *testing.T) {
	client, dir, argsFile, _ := fakeClient(t, []byte(jsonFixture), "")
	if _, err := client.Start(context.Background(), "say ready"); err != nil {
		t.Fatal(err)
	}
	args := readArgs(t, argsFile)
	assertContainsSequence(t, args, "exec", "--json", "--workspace", dir, "--worktree", "off", "--prompt-file")
	if contains(args, "--session-id") {
		t.Fatalf("fresh args unexpectedly carry --session-id: %q", args)
	}
}
