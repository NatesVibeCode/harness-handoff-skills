// Package cursorsession is a dependency-free client for the documented
// Cursor Agent CLI session surface. It delegates authentication and provider
// traffic to the installed cursor-agent executable.
package cursorsession

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os/exec"
	"path/filepath"
)

const defaultMaxOutputBytes int64 = 16 << 20

var (
	ErrInvalidArgument = errors.New("cursor-session-client: invalid argument")
	ErrOutputTooLarge  = errors.New("cursor-session-client: output exceeds configured limit")
	ErrNoResult        = errors.New("cursor-session-client: CLI output has no result object")
	ErrUnsupported     = errors.New("cursor-session-client: unsupported by the documented CLI surface")
)

// Client invokes the installed Cursor Agent CLI. Authentication remains in
// the CLI's native login session or runtime environment (CURSOR_API_KEY);
// this type never stores or reads credential values.
type Client struct {
	// Binary is the executable path. Empty uses "cursor-agent" from PATH.
	Binary string
	// WorkingDirectory selects the workspace passed via --workspace. Empty
	// inherits the caller's current directory.
	WorkingDirectory string
	// Model is passed via --model. Empty omits the flag and the CLI default
	// applies; discover values with the CLI's --list-models option.
	Model string
	// PartialOutput adds --stream-partial-output to Stream calls for
	// character-level deltas instead of one line per message.
	PartialOutput bool
	// Stderr receives CLI diagnostics. A nil writer discards them.
	Stderr io.Writer
	// MaxOutputBytes limits buffered JSON and list output. Values <= 0 use
	// the 16 MiB default. Streaming output is passed directly to its writer.
	MaxOutputBytes int64
}

// Result contains the session ID from the CLI's JSON output, the result
// text, and the complete JSON bytes for callers that need other fields.
type Result struct {
	SessionID string
	Text      string
	JSON      []byte
}

// Start creates a new session and sends its first prompt. The prompt is
// passed as the final argv element (the CLI's documented prompt delivery),
// so it is visible in the process list while the command runs.
func (c Client) Start(ctx context.Context, prompt string) (Result, error) {
	if prompt == "" {
		return Result{}, fmt.Errorf("%w: prompt is required", ErrInvalidArgument)
	}
	var output limitedBuffer
	output.limit = c.outputLimit()
	if err := c.runPrompt(ctx, prompt, "", "json", &output); err != nil {
		if errors.Is(err, ErrOutputTooLarge) {
			return Result{}, err
		}
		return Result{}, err
	}
	return parseResult(output.Bytes())
}

// Resume continues exactly the supplied chat ID and sends a prompt.
func (c Client) Resume(ctx context.Context, sessionID, prompt string) (Result, error) {
	if !validSessionID(sessionID) {
		return Result{}, fmt.Errorf("%w: exact session ID is required", ErrInvalidArgument)
	}
	if prompt == "" {
		return Result{}, fmt.Errorf("%w: prompt is required", ErrInvalidArgument)
	}
	var output limitedBuffer
	output.limit = c.outputLimit()
	if err := c.runPrompt(ctx, prompt, sessionID, "json", &output); err != nil {
		if errors.Is(err, ErrOutputTooLarge) {
			return Result{}, err
		}
		return Result{}, err
	}
	return parseResult(output.Bytes())
}

// Fork is unsupported: the documented CLI surface exposes no fork operation.
func (c Client) Fork(_ context.Context, _, _ string) (Result, error) {
	return Result{}, fmt.Errorf("%w: no documented fork flag or command", ErrUnsupported)
}

// Stream sends a prompt in fresh or resumed mode and copies the CLI's
// native stream-json NDJSON bytes to dst without interpreting events.
func (c Client) Stream(ctx context.Context, sessionID string, prompt string, dst io.Writer) error {
	if dst == nil {
		return fmt.Errorf("%w: stream destination is required", ErrInvalidArgument)
	}
	if prompt == "" {
		return fmt.Errorf("%w: prompt is required", ErrInvalidArgument)
	}
	return c.runPrompt(ctx, prompt, sessionID, "stream-json", dst)
}

// List returns the CLI's `ls` output verbatim. The documented shape of that
// output is a session listing for interactive resume; no machine-readable
// contract is documented, so callers must interpret the bytes themselves.
func (c Client) List(ctx context.Context) ([]byte, error) {
	ws, err := c.workspace()
	if err != nil {
		return nil, err
	}
	return c.capture(ctx, []string{"--workspace", ws, "ls"})
}

// Inspect is unsupported: the documented CLI surface exposes no passive
// transcript read (local history lives in undocumented SQLite/editor
// stores, and resume starts a turn rather than inspecting).
func (c Client) Inspect(_ context.Context, _ string) ([]byte, error) {
	return nil, fmt.Errorf("%w: no documented transcript export or passive read", ErrUnsupported)
}

// parseResult decodes the CLI's --print --output-format json object.
func parseResult(data []byte) (Result, error) {
	var response struct {
		Type      string `json:"type"`
		Subtype   string `json:"subtype"`
		IsError   bool   `json:"is_error"`
		Result    string `json:"result"`
		SessionID string `json:"session_id"`
	}
	if err := json.Unmarshal(bytes.TrimSpace(data), &response); err != nil {
		return Result{}, fmt.Errorf("cursor-session-client: decode print JSON response: %w", err)
	}
	if response.Type != "result" {
		return Result{}, fmt.Errorf("%w: top-level type %q", ErrNoResult, response.Type)
	}
	if response.SessionID == "" {
		return Result{}, errors.New("cursor-session-client: result object has no session_id")
	}
	if response.IsError {
		return Result{}, fmt.Errorf("cursor-session-client: result is error (subtype %q): %s", response.Subtype, truncate(response.Result, 300))
	}
	return Result{SessionID: response.SessionID, Text: response.Result, JSON: bytes.Clone(data)}, nil
}

func (c Client) runPrompt(ctx context.Context, prompt, sessionID, format string, dst io.Writer) error {
	if prompt == "" {
		return fmt.Errorf("%w: prompt is required", ErrInvalidArgument)
	}
	if sessionID != "" && !validSessionID(sessionID) {
		return fmt.Errorf("%w: exact session ID is required", ErrInvalidArgument)
	}
	ws, err := c.workspace()
	if err != nil {
		return err
	}
	args := []string{"--workspace", ws, "--sandbox", "enabled", "--print", "--output-format", format}
	if sessionID != "" {
		args = append(args, "--resume", sessionID)
	}
	if format == "stream-json" && c.PartialOutput {
		args = append(args, "--stream-partial-output")
	}
	if c.Model != "" {
		args = append(args, "--model", c.Model)
	}
	args = append(args, prompt)
	return c.run(ctx, args, dst)
}

func validSessionID(id string) bool {
	if id == "" || len(id) > 128 || id[0] == '-' || id == "latest" || id == "last" || id == "newest" || id == "continue" {
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

func (c Client) capture(ctx context.Context, args []string) ([]byte, error) {
	var output limitedBuffer
	output.limit = c.outputLimit()
	if err := c.run(ctx, args, &output); err != nil {
		if errors.Is(err, ErrOutputTooLarge) {
			return nil, err
		}
		return nil, err
	}
	return bytes.Clone(output.Bytes()), nil
}

func (c Client) run(ctx context.Context, args []string, stdout io.Writer) error {
	binary := c.Binary
	if binary == "" {
		binary = "cursor-agent"
	}
	cmd := exec.CommandContext(ctx, binary, args...)
	cmd.Dir = c.WorkingDirectory
	cmd.Stdout = stdout
	cmd.Stderr = c.Stderr
	if err := cmd.Run(); err != nil {
		return fmt.Errorf("cursor-session-client: cursor-agent command failed: %w", err)
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
		return "", fmt.Errorf("cursor-session-client: resolve workspace: %w", err)
	}
	return abs, nil
}

func (c Client) outputLimit() int64 {
	if c.MaxOutputBytes > 0 {
		return c.MaxOutputBytes
	}
	return defaultMaxOutputBytes
}

func truncate(s string, n int) string {
	if len(s) <= n {
		return s
	}
	return s[:n] + "…"
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
