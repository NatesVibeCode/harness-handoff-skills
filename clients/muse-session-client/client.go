// Package musesession is a dependency-free client for the documented Muse
// Code CLI session surface (muse exec / muse export). It delegates
// authentication and provider traffic to the installed muse executable.
package musesession

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
)

const defaultMaxOutputBytes int64 = 16 << 20

var (
	ErrInvalidArgument = errors.New("muse-session-client: invalid argument")
	ErrOutputTooLarge  = errors.New("muse-session-client: output exceeds configured limit")
	ErrUnsupported     = errors.New("muse-session-client: unsupported by the documented CLI surface")
)

// Client invokes the installed Muse Code CLI. Authentication remains in
// the CLI's stored credentials or runtime environment (META_API_KEY); this
// type never stores or reads credential values.
type Client struct {
	// Binary is the executable path. Empty uses "muse" from PATH.
	Binary string
	// WorkingDirectory selects the workspace passed via --workspace. Empty
	// inherits the caller's current directory.
	WorkingDirectory string
	// Stderr receives CLI diagnostics. A nil writer discards them.
	Stderr io.Writer
	// MaxOutputBytes limits buffered JSONL and export output. Values <= 0
	// use the 16 MiB default. Streaming output is passed directly to its
	// writer.
	MaxOutputBytes int64
}

// Result carries the CLI's --json JSONL bytes verbatim. Event envelope
// field names are not part of the consulted documentation, so callers
// extract session IDs and text per the MSP wire reference; this package
// does not guess at them.
type Result struct {
	JSON []byte
}

// Start creates a new session and sends its first prompt via a mode-0600
// prompt file, which is removed after the CLI exits.
func (c Client) Start(ctx context.Context, prompt string) (Result, error) {
	if prompt == "" {
		return Result{}, fmt.Errorf("%w: prompt is required", ErrInvalidArgument)
	}
	var output limitedBuffer
	output.limit = c.outputLimit()
	if err := c.runPrompt(ctx, prompt, &output); err != nil {
		if errors.Is(err, ErrOutputTooLarge) {
			return Result{}, err
		}
		return Result{}, err
	}
	return Result{JSON: bytes.Clone(output.Bytes())}, nil
}

// Resume is unsupported: no documented headless CLI resume-with-prompt
// exists. The checked CLI's `exec --session-id` only selects an identity
// for a new exec run and does not resume history, while `muse resume` is
// interactive-only. Resume a retained session interactively with
// `muse --workspace <dir> resume <session-id>`, or continue a live
// session with native messaging; this method never invokes the CLI.
func (c Client) Resume(_ context.Context, sessionID, prompt string) (Result, error) {
	if !validSessionID(sessionID) {
		return Result{}, fmt.Errorf("%w: session ID is required", ErrInvalidArgument)
	}
	if prompt == "" {
		return Result{}, fmt.Errorf("%w: prompt is required", ErrInvalidArgument)
	}
	return Result{}, fmt.Errorf("%w: no documented headless CLI resume-with-prompt; use interactive `muse resume`", ErrUnsupported)
}

// Fork is unsupported: forking exists on the MSP protocol (session/fork)
// and the interactive UI (/fork), but no headless CLI fork is documented.
func (c Client) Fork(_ context.Context, _, _ string) (Result, error) {
	return Result{}, fmt.Errorf("%w: no documented headless CLI fork", ErrUnsupported)
}

// Stream sends a fresh prompt and copies the CLI's native --json JSONL
// bytes to dst without interpreting events. A non-empty sessionID is
// refused like Resume: no documented headless CLI resume-with-prompt
// exists.
func (c Client) Stream(ctx context.Context, sessionID string, prompt string, dst io.Writer) error {
	if dst == nil {
		return fmt.Errorf("%w: stream destination is required", ErrInvalidArgument)
	}
	if prompt == "" {
		return fmt.Errorf("%w: prompt is required", ErrInvalidArgument)
	}
	if sessionID != "" {
		if !validSessionID(sessionID) {
			return fmt.Errorf("%w: session ID is malformed", ErrInvalidArgument)
		}
		return fmt.Errorf("%w: no documented headless CLI resume-with-prompt; use interactive `muse resume`", ErrUnsupported)
	}
	return c.runPrompt(ctx, prompt, dst)
}

// List is unsupported: session listing exists on the MSP protocol
// (session/list), but no CLI list command is documented, and the on-disk
// session index is explicitly not an official API.
func (c Client) List(_ context.Context) ([]byte, error) {
	return nil, fmt.Errorf("%w: no documented CLI list command", ErrUnsupported)
}

// Inspect exports the selected session's self-contained document via
// `muse export --session <id> --out <tmp> --redacted` and returns the file
// bytes verbatim. The temporary file is removed afterwards.
func (c Client) Inspect(ctx context.Context, sessionID string) ([]byte, error) {
	if !validSessionID(sessionID) {
		return nil, fmt.Errorf("%w: session ID is required", ErrInvalidArgument)
	}
	out, err := os.CreateTemp("", "muse-session-client-*.export.json")
	if err != nil {
		return nil, fmt.Errorf("muse-session-client: create temporary export file: %w", err)
	}
	outPath := out.Name()
	_ = out.Close()
	defer os.Remove(outPath)
	var stderr bytes.Buffer
	binary := c.Binary
	if binary == "" {
		binary = "muse"
	}
	cmd := exec.CommandContext(ctx, binary, "export", "--session", sessionID, "--out", outPath, "--redacted")
	cmd.Dir = c.WorkingDirectory
	cmd.Stderr = &stderr
	if c.Stderr != nil {
		cmd.Stderr = io.MultiWriter(c.Stderr, &stderr)
	}
	if err := cmd.Run(); err != nil {
		return nil, fmt.Errorf("muse-session-client: muse export failed: %w: %s", err, truncate(stderr.String(), 300))
	}
	limit := c.outputLimit()
	data, err := os.ReadFile(outPath)
	if err != nil {
		return nil, fmt.Errorf("muse-session-client: read export file: %w", err)
	}
	if int64(len(data)) > limit {
		return nil, ErrOutputTooLarge
	}
	return data, nil
}

func (c Client) runPrompt(ctx context.Context, prompt string, dst io.Writer) error {
	if prompt == "" {
		return fmt.Errorf("%w: prompt is required", ErrInvalidArgument)
	}
	ws, err := c.workspace()
	if err != nil {
		return err
	}
	promptPath, err := writePromptFile(prompt)
	if err != nil {
		return err
	}
	defer os.Remove(promptPath)
	// Fresh exec only. --session-id is deliberately never passed: the
	// checked CLI documents it as an identity for a new run, not a
	// history-preserving continuation.
	args := []string{"exec", "--json", "--workspace", ws, "--worktree", "off", "--prompt-file", promptPath}
	return c.run(ctx, args, dst)
}

func (c Client) run(ctx context.Context, args []string, stdout io.Writer) error {
	binary := c.Binary
	if binary == "" {
		binary = "muse"
	}
	cmd := exec.CommandContext(ctx, binary, args...)
	cmd.Dir = c.WorkingDirectory
	cmd.Stdout = stdout
	cmd.Stderr = c.Stderr
	if err := cmd.Run(); err != nil {
		return fmt.Errorf("muse-session-client: muse command failed: %w", err)
	}
	return nil
}

// workspace resolves the --workspace value: the configured directory, or
// the caller's current directory, as an absolute path.
func (c Client) workspace() (string, error) {
	ws := c.WorkingDirectory
	if ws == "" {
		ws = "."
	}
	abs, err := filepath.Abs(ws)
	if err != nil {
		return "", fmt.Errorf("muse-session-client: resolve workspace: %w", err)
	}
	return abs, nil
}

func (c Client) outputLimit() int64 {
	if c.MaxOutputBytes > 0 {
		return c.MaxOutputBytes
	}
	return defaultMaxOutputBytes
}

func validSessionID(id string) bool {
	if id == "" || len(id) > 128 {
		return false
	}
	if id[0] == '-' || id == "latest" || id == "last" || id == "newest" || id == "continue" {
		return false
	}
	for i := 0; i < len(id); i++ {
		ch := id[i]
		if ch >= 'a' && ch <= 'z' || ch >= 'A' && ch <= 'Z' || ch >= '0' && ch <= '9' || ch == '-' || ch == '_' {
			continue
		}
		return false
	}
	return true
}

func truncate(s string, n int) string {
	if len(s) <= n {
		return s
	}
	return s[:n] + "…"
}

func writePromptFile(prompt string) (string, error) {
	file, err := os.CreateTemp("", "muse-session-client-*.prompt")
	if err != nil {
		return "", fmt.Errorf("muse-session-client: create temporary prompt file: %w", err)
	}
	path := file.Name()
	if err := file.Chmod(0o600); err != nil {
		_ = file.Close()
		_ = os.Remove(path)
		return "", fmt.Errorf("muse-session-client: protect temporary prompt file: %w", err)
	}
	if _, err := file.WriteString(prompt); err != nil {
		_ = file.Close()
		_ = os.Remove(path)
		return "", fmt.Errorf("muse-session-client: write temporary prompt file: %w", err)
	}
	if err := file.Close(); err != nil {
		_ = os.Remove(path)
		return "", fmt.Errorf("muse-session-client: close temporary prompt file: %w", err)
	}
	return path, nil
}

type limitedBuffer struct {
	buf   bytes.Buffer
	limit int64
}

func (b *limitedBuffer) Write(p []byte) (int, error) {
	if int64(b.buf.Len()+len(p)) > b.limit {
		return 0, ErrOutputTooLarge
	}
	return b.buf.Write(p)
}

func (b *limitedBuffer) Bytes() []byte {
	return b.buf.Bytes()
}
