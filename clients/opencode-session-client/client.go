// Package opencodesession is a dependency-free client for the documented
// OpenCode CLI session surface (opencode run / session list / export). It
// delegates authentication and provider traffic to the installed opencode
// executable.
package opencodesession

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"io"
	"os/exec"
	"path/filepath"
	"strconv"
)

const defaultMaxOutputBytes int64 = 16 << 20

var (
	ErrInvalidArgument = errors.New("opencode-session-client: invalid argument")
	ErrOutputTooLarge  = errors.New("opencode-session-client: output exceeds configured limit")
)

// Client invokes the installed OpenCode CLI. Authentication remains in the
// CLI's stored provider credentials or runtime environment; this type never
// stores or reads credential values.
type Client struct {
	// Binary is the executable path. Empty uses "opencode" from PATH.
	Binary string
	// WorkingDirectory selects the directory passed via --dir. Empty
	// inherits the caller's current directory.
	WorkingDirectory string
	// Model is passed via --model in provider/model form. Empty omits the
	// flag and the CLI default applies.
	Model string
	// Stderr receives CLI diagnostics. A nil writer discards them.
	Stderr io.Writer
	// MaxOutputBytes limits buffered JSON and export output. Values <= 0
	// use the 16 MiB default. Streaming output is passed directly to its
	// writer.
	MaxOutputBytes int64
}

// Result carries the CLI's --format json event bytes verbatim. Event
// envelope field names are not part of the consulted documentation, so
// callers extract session IDs per the server/SDK reference; this package
// does not guess at them.
type Result struct {
	JSON []byte
}

// Start creates a new session and sends its first prompt. The prompt is
// passed as a trailing argv element (the CLI's documented prompt delivery),
// so it is visible in the process list while the command runs.
func (c Client) Start(ctx context.Context, prompt string) (Result, error) {
	if prompt == "" {
		return Result{}, fmt.Errorf("%w: prompt is required", ErrInvalidArgument)
	}
	var output limitedBuffer
	output.limit = c.outputLimit()
	if err := c.runPrompt(ctx, prompt, "", false, &output); err != nil {
		if errors.Is(err, ErrOutputTooLarge) {
			return Result{}, err
		}
		return Result{}, err
	}
	return Result{JSON: bytes.Clone(output.Bytes())}, nil
}

// Resume continues exactly the supplied session ID and sends a prompt.
func (c Client) Resume(ctx context.Context, sessionID, prompt string) (Result, error) {
	if !validSessionID(sessionID) {
		return Result{}, fmt.Errorf("%w: session ID is required", ErrInvalidArgument)
	}
	if prompt == "" {
		return Result{}, fmt.Errorf("%w: prompt is required", ErrInvalidArgument)
	}
	var output limitedBuffer
	output.limit = c.outputLimit()
	if err := c.runPrompt(ctx, prompt, sessionID, false, &output); err != nil {
		if errors.Is(err, ErrOutputTooLarge) {
			return Result{}, err
		}
		return Result{}, err
	}
	return Result{JSON: bytes.Clone(output.Bytes())}, nil
}

// Fork branches the supplied session ID and sends a prompt on the new
// session. History is copied; the working tree is not isolated.
func (c Client) Fork(ctx context.Context, sessionID, prompt string) (Result, error) {
	if !validSessionID(sessionID) {
		return Result{}, fmt.Errorf("%w: session ID is required", ErrInvalidArgument)
	}
	if prompt == "" {
		return Result{}, fmt.Errorf("%w: prompt is required", ErrInvalidArgument)
	}
	var output limitedBuffer
	output.limit = c.outputLimit()
	if err := c.runPrompt(ctx, prompt, sessionID, true, &output); err != nil {
		if errors.Is(err, ErrOutputTooLarge) {
			return Result{}, err
		}
		return Result{}, err
	}
	return Result{JSON: bytes.Clone(output.Bytes())}, nil
}

// Stream sends a prompt in fresh, resumed, or forked mode and copies the
// CLI's native --format json event bytes to dst without interpreting them.
func (c Client) Stream(ctx context.Context, sessionID string, fork bool, prompt string, dst io.Writer) error {
	if dst == nil {
		return fmt.Errorf("%w: stream destination is required", ErrInvalidArgument)
	}
	if prompt == "" {
		return fmt.Errorf("%w: prompt is required", ErrInvalidArgument)
	}
	if (sessionID != "" || fork) && !validSessionID(sessionID) {
		return fmt.Errorf("%w: exact session ID is required", ErrInvalidArgument)
	}
	if sessionID != "" && !validSessionID(sessionID) {
		return fmt.Errorf("%w: session ID is malformed", ErrInvalidArgument)
	}
	return c.runPrompt(ctx, prompt, sessionID, fork, dst)
}

// List returns `opencode session list --format json` output verbatim,
// limited to the N most recent sessions when limit is positive.
func (c Client) List(ctx context.Context, limit int) ([]byte, error) {
	if limit < 0 {
		return nil, fmt.Errorf("%w: limit cannot be negative", ErrInvalidArgument)
	}
	args := []string{"session", "list", "--format", "json"}
	if limit > 0 {
		args = append(args, "--max-count", strconv.Itoa(limit))
	}
	return c.capture(ctx, args)
}

// Inspect exports the selected session as JSON via `opencode export <id>`
// and returns the bytes verbatim. --sanitize is not passed, so nothing is
// redacted; treat the bytes as sensitive.
func (c Client) Inspect(ctx context.Context, sessionID string) ([]byte, error) {
	if !validSessionID(sessionID) {
		return nil, fmt.Errorf("%w: session ID is required", ErrInvalidArgument)
	}
	return c.capture(ctx, []string{"export", sessionID, "--sanitize"})
}

func (c Client) runPrompt(ctx context.Context, prompt, sessionID string, fork bool, dst io.Writer) error {
	if prompt == "" {
		return fmt.Errorf("%w: prompt is required", ErrInvalidArgument)
	}
	if fork && !validSessionID(sessionID) {
		return fmt.Errorf("%w: fork requires an explicit session ID", ErrInvalidArgument)
	}
	ws, err := c.workspace()
	if err != nil {
		return err
	}
	args := []string{"run", "--dir", ws, "--format", "json"}
	if sessionID != "" {
		args = append(args, "--session", sessionID)
	}
	if fork {
		args = append(args, "--fork")
	}
	if c.Model != "" {
		args = append(args, "--model", c.Model)
	}
	args = append(args, prompt)
	return c.run(ctx, args, dst)
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
		binary = "opencode"
	}
	cmd := exec.CommandContext(ctx, binary, args...)
	cmd.Dir = c.WorkingDirectory
	cmd.Stdout = stdout
	cmd.Stderr = c.Stderr
	if err := cmd.Run(); err != nil {
		return fmt.Errorf("opencode-session-client: opencode command failed: %w", err)
	}
	return nil
}

// workspace resolves the --dir value: the configured directory, or the
// caller's current directory, as an absolute path.
func (c Client) workspace() (string, error) {
	ws := c.WorkingDirectory
	if ws == "" {
		ws = "."
	}
	abs, err := filepath.Abs(ws)
	if err != nil {
		return "", fmt.Errorf("opencode-session-client: resolve workspace: %w", err)
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
