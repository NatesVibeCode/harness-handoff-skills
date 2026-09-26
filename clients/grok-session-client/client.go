// Package groksession is a dependency-free client for documented Grok Build
// CLI session operations. It delegates authentication and provider traffic to
// the installed grok executable.
package groksession

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"os/exec"
	"strconv"
)

const defaultMaxOutputBytes int64 = 16 << 20

var (
	ErrInvalidArgument = errors.New("grok-session-client: invalid argument")
	ErrOutputTooLarge  = errors.New("grok-session-client: output exceeds configured limit")
)

// Client invokes the installed Grok Build CLI. Authentication remains in the
// CLI's configured session or runtime environment; this type never stores or
// reads credential values.
type Client struct {
	// Binary is the executable path. Empty uses "grok" from PATH.
	Binary string
	// WorkingDirectory selects the workspace and session store context. Empty
	// inherits the caller's current directory.
	WorkingDirectory string
	// Stderr receives CLI diagnostics. A nil writer discards them.
	Stderr io.Writer
	// MaxOutputBytes limits buffered JSON, list, and export output. Values <= 0
	// use the 16 MiB default. Streaming output is passed directly to its writer.
	MaxOutputBytes int64
}

// Result contains the session ID documented in Grok's headless JSON output
// and the complete JSON response for callers that need other fields.
type Result struct {
	SessionID string
	JSON      []byte
}

// Start creates a new session and sends its first prompt.
func (c Client) Start(ctx context.Context, prompt string) (Result, error) {
	return c.runJSON(ctx, prompt, "", false)
}

// Resume continues exactly the supplied session ID and sends a prompt.
func (c Client) Resume(ctx context.Context, sessionID, prompt string) (Result, error) {
	if sessionID == "" {
		return Result{}, fmt.Errorf("%w: session ID is required", ErrInvalidArgument)
	}
	return c.runJSON(ctx, prompt, sessionID, false)
}

// Fork branches the supplied session ID and sends a prompt on the new branch.
func (c Client) Fork(ctx context.Context, sessionID, prompt string) (Result, error) {
	if sessionID == "" {
		return Result{}, fmt.Errorf("%w: session ID is required", ErrInvalidArgument)
	}
	return c.runJSON(ctx, prompt, sessionID, true)
}

// Stream sends a prompt in fresh, resumed, or forked mode and copies Grok's
// native streaming-json NDJSON bytes to dst without interpreting event fields.
func (c Client) Stream(ctx context.Context, sessionID string, fork bool, prompt string, dst io.Writer) error {
	if dst == nil {
		return fmt.Errorf("%w: stream destination is required", ErrInvalidArgument)
	}
	if prompt == "" {
		return fmt.Errorf("%w: prompt is required", ErrInvalidArgument)
	}
	if fork && sessionID == "" {
		return fmt.Errorf("%w: fork requires an explicit session ID", ErrInvalidArgument)
	}
	return c.runPrompt(ctx, prompt, sessionID, fork, "streaming-json", dst)
}

// List returns the CLI's session-list output verbatim. A zero limit uses the
// CLI default. The format is intentionally left in the installed CLI's own
// documented representation.
func (c Client) List(ctx context.Context, limit int) ([]byte, error) {
	if limit < 0 {
		return nil, fmt.Errorf("%w: limit cannot be negative", ErrInvalidArgument)
	}
	args := []string{"sessions", "list"}
	if limit > 0 {
		args = append(args, "--limit", strconv.Itoa(limit))
	}
	return c.capture(ctx, args)
}

// Inspect exports the selected session transcript as Markdown, verbatim.
func (c Client) Inspect(ctx context.Context, sessionID string) ([]byte, error) {
	if sessionID == "" {
		return nil, fmt.Errorf("%w: session ID is required", ErrInvalidArgument)
	}
	return c.capture(ctx, []string{"export", sessionID})
}

func (c Client) runJSON(ctx context.Context, prompt, sessionID string, fork bool) (Result, error) {
	if prompt == "" {
		return Result{}, fmt.Errorf("%w: prompt is required", ErrInvalidArgument)
	}
	if fork && sessionID == "" {
		return Result{}, fmt.Errorf("%w: fork requires an explicit session ID", ErrInvalidArgument)
	}
	var output limitedBuffer
	output.limit = c.outputLimit()
	if err := c.runPrompt(ctx, prompt, sessionID, fork, "json", &output); err != nil {
		if errors.Is(err, ErrOutputTooLarge) {
			return Result{}, err
		}
		return Result{}, err
	}
	var response struct {
		SessionID string `json:"sessionId"`
	}
	if err := json.Unmarshal(output.Bytes(), &response); err != nil {
		return Result{}, fmt.Errorf("grok-session-client: decode headless JSON response: %w", err)
	}
	if response.SessionID == "" {
		return Result{}, errors.New("grok-session-client: headless JSON response has no sessionId")
	}
	return Result{SessionID: response.SessionID, JSON: bytes.Clone(output.Bytes())}, nil
}

func (c Client) runPrompt(ctx context.Context, prompt, sessionID string, fork bool, format string, dst io.Writer) error {
	if prompt == "" {
		return fmt.Errorf("%w: prompt is required", ErrInvalidArgument)
	}
	if fork && sessionID == "" {
		return fmt.Errorf("%w: fork requires an explicit session ID", ErrInvalidArgument)
	}
	promptPath, err := writePromptFile(prompt)
	if err != nil {
		return err
	}
	defer os.Remove(promptPath)

	args := []string{"--output-format", format}
	if sessionID != "" {
		args = append(args, "--resume", sessionID)
	}
	if fork {
		args = append(args, "--fork-session")
	}
	args = append(args, "--prompt-file", promptPath)
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
		binary = "grok"
	}
	cmd := exec.CommandContext(ctx, binary, args...)
	cmd.Dir = c.WorkingDirectory
	cmd.Stdout = stdout
	cmd.Stderr = c.Stderr
	if err := cmd.Run(); err != nil {
		return fmt.Errorf("grok-session-client: grok command failed: %w", err)
	}
	return nil
}

func (c Client) outputLimit() int64 {
	if c.MaxOutputBytes > 0 {
		return c.MaxOutputBytes
	}
	return defaultMaxOutputBytes
}

func writePromptFile(prompt string) (string, error) {
	file, err := os.CreateTemp("", "grok-session-client-*.prompt")
	if err != nil {
		return "", fmt.Errorf("grok-session-client: create temporary prompt file: %w", err)
	}
	path := file.Name()
	if err := file.Chmod(0o600); err != nil {
		_ = file.Close()
		_ = os.Remove(path)
		return "", fmt.Errorf("grok-session-client: protect temporary prompt file: %w", err)
	}
	if _, err := io.WriteString(file, prompt); err != nil {
		_ = file.Close()
		_ = os.Remove(path)
		return "", fmt.Errorf("grok-session-client: write temporary prompt file: %w", err)
	}
	if err := file.Close(); err != nil {
		_ = os.Remove(path)
		return "", fmt.Errorf("grok-session-client: close temporary prompt file: %w", err)
	}
	return path, nil
}

type limitedBuffer struct {
	bytes.Buffer
	limit int64
}

func (b *limitedBuffer) Write(p []byte) (int, error) {
	if int64(b.Len())+int64(len(p)) > b.limit {
		return 0, ErrOutputTooLarge
	}
	return b.Buffer.Write(p)
}
