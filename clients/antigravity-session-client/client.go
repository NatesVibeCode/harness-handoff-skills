// Package antigravitysession is a dependency-free client for the documented
// Antigravity CLI session surface (agy --print). It delegates
// authentication and provider traffic to the installed agy executable.
package antigravitysession

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os/exec"
)

const defaultMaxOutputBytes int64 = 16 << 20

var (
	ErrInvalidArgument = errors.New("antigravity-session-client: invalid argument")
	ErrOutputTooLarge  = errors.New("antigravity-session-client: output exceeds configured limit")
	ErrNoConversation  = errors.New("antigravity-session-client: CLI output has no conversation_id")
	ErrUnsupported     = errors.New("antigravity-session-client: unsupported by the documented CLI surface")
)

// Client invokes the installed Antigravity CLI. Authentication remains in
// the CLI's native session (keyring/OAuth) or runtime environment; this
// type never stores or reads credential values.
type Client struct {
	// Binary is the executable path. Empty uses "agy" from PATH.
	Binary string
	// WorkingDirectory selects the checkout the CLI is launched from.
	// History is workspace-scoped, so resume requires the same checkout.
	// Empty inherits the caller's current directory.
	WorkingDirectory string
	// Stderr receives CLI diagnostics. A nil writer discards them.
	Stderr io.Writer
	// MaxOutputBytes limits buffered JSON output. Values <= 0 use the 16
	// MiB default. Streaming output is passed directly to its writer.
	MaxOutputBytes int64
}

// Result contains the conversation ID from the CLI's JSON envelope, the
// response text, and the complete JSON bytes for callers that need other
// fields (status, usage, num_turns, duration).
type Result struct {
	SessionID string
	Text      string
	JSON      []byte
}

// Start creates a new session and sends its first prompt. The prompt is
// passed as an argv element (the CLI's documented prompt delivery), so it
// is visible in the process list while the command runs.
func (c Client) Start(ctx context.Context, prompt string) (Result, error) {
	if prompt == "" {
		return Result{}, fmt.Errorf("%w: prompt is required", ErrInvalidArgument)
	}
	var output limitedBuffer
	output.limit = c.outputLimit()
	args := []string{"--output-format", "json", "--print", prompt}
	if err := c.run(ctx, args, nil, &output); err != nil {
		if errors.Is(err, ErrOutputTooLarge) {
			return Result{}, err
		}
		return Result{}, err
	}
	return parseResult(output.Bytes())
}

// Resume continues exactly the supplied conversation ID and sends a
// prompt. The client must run from the checkout that owns the history.
func (c Client) Resume(ctx context.Context, sessionID, prompt string) (Result, error) {
	if !validSessionID(sessionID) {
		return Result{}, fmt.Errorf("%w: session ID is required", ErrInvalidArgument)
	}
	if prompt == "" {
		return Result{}, fmt.Errorf("%w: prompt is required", ErrInvalidArgument)
	}
	var output limitedBuffer
	output.limit = c.outputLimit()
	args := []string{"--output-format", "json", "--print", prompt, "--conversation", sessionID}
	if err := c.run(ctx, args, nil, &output); err != nil {
		if errors.Is(err, ErrOutputTooLarge) {
			return Result{}, err
		}
		return Result{}, err
	}
	return parseResult(output.Bytes())
}

// Fork is unsupported: forking exists in the IDE (/fork) only; no CLI fork
// flag or command is documented.
func (c Client) Fork(_ context.Context, _, _ string) (Result, error) {
	return Result{}, fmt.Errorf("%w: no documented CLI fork", ErrUnsupported)
}

// Stream opens a streaming session: it spawns the CLI with
// --input-format/--output-format stream-json, writes one documented user
// frame carrying the prompt, closes stdin, and copies the CLI's bytes to
// dst without interpreting them. With a session ID it also passes
// --conversation (docs-composed combination; see conformance notes).
func (c Client) Stream(ctx context.Context, sessionID string, prompt string, dst io.Writer) error {
	if dst == nil {
		return fmt.Errorf("%w: stream destination is required", ErrInvalidArgument)
	}
	if prompt == "" {
		return fmt.Errorf("%w: prompt is required", ErrInvalidArgument)
	}
	if sessionID != "" && !validSessionID(sessionID) {
		return fmt.Errorf("%w: session ID is malformed", ErrInvalidArgument)
	}
	args := []string{"--input-format", "stream-json", "--output-format", "stream-json"}
	if sessionID != "" {
		args = append(args, "--conversation", sessionID)
	}
	frame, err := json.Marshal(streamUserFrame{Event: "user", Message: streamMessage{Content: prompt}})
	if err != nil {
		return fmt.Errorf("antigravity-session-client: encode stream frame: %w", err)
	}
	frame = append(frame, '\n')
	return c.run(ctx, args, bytes.NewReader(frame), dst)
}

// List is unsupported: checked CLI help exposes no session-list command,
// and the local SQLite/transcript paths are explicitly not an API.
func (c Client) List(_ context.Context) ([]byte, error) {
	return nil, fmt.Errorf("%w: no documented list command or store API", ErrUnsupported)
}

// Inspect is unsupported: checked CLI help exposes no export command, and
// the local transcript paths are explicitly not an API.
func (c Client) Inspect(_ context.Context, _ string) ([]byte, error) {
	return nil, fmt.Errorf("%w: no documented export command or transcript API", ErrUnsupported)
}

type streamUserFrame struct {
	Event   string        `json:"event"`
	Message streamMessage `json:"message"`
}

type streamMessage struct {
	Content string `json:"content"`
}

// parseResult decodes the CLI's --print --output-format json envelope.
func parseResult(data []byte) (Result, error) {
	var response struct {
		ConversationID string `json:"conversation_id"`
		Status         string `json:"status"`
		Response       string `json:"response"`
		Error          string `json:"error"`
	}
	if err := json.Unmarshal(bytes.TrimSpace(data), &response); err != nil {
		return Result{}, fmt.Errorf("antigravity-session-client: decode print JSON envelope: %w", err)
	}
	if response.ConversationID == "" {
		return Result{}, ErrNoConversation
	}
	if response.Status != "" && response.Status != "SUCCESS" {
		return Result{}, fmt.Errorf("antigravity-session-client: run status %s: %s", response.Status, truncate(response.Error, 300))
	}
	return Result{SessionID: response.ConversationID, Text: response.Response, JSON: bytes.Clone(data)}, nil
}

func (c Client) run(ctx context.Context, args []string, stdin io.Reader, stdout io.Writer) error {
	binary := c.Binary
	if binary == "" {
		binary = "agy"
	}
	cmd := exec.CommandContext(ctx, binary, args...)
	cmd.Dir = c.WorkingDirectory
	cmd.Stdin = stdin
	cmd.Stdout = stdout
	cmd.Stderr = c.Stderr
	if err := cmd.Run(); err != nil {
		return fmt.Errorf("antigravity-session-client: agy command failed: %w", err)
	}
	return nil
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
