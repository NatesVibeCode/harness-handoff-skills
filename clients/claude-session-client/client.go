// Package claudesession is a dependency-free client for documented Claude
// Code CLI session operations. It delegates authentication and provider
// traffic to the installed claude executable and reads the documented
// local transcript store for list/inspect.
package claudesession

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"sort"
	"strings"
)

const defaultMaxOutputBytes int64 = 16 << 20

var (
	ErrInvalidArgument = errors.New("claude-session-client: invalid argument")
	ErrOutputTooLarge  = errors.New("claude-session-client: output exceeds configured limit")
	ErrNoResult        = errors.New("claude-session-client: CLI output has no result message")
)

// Client invokes the installed Claude Code CLI. Authentication remains in
// the CLI's configured credentials or runtime environment; this type never
// stores or reads credential values.
type Client struct {
	// Binary is the executable path. Empty uses "claude" from PATH.
	Binary string
	// WorkingDirectory selects the workspace and session store context. Empty
	// inherits the caller's current directory.
	WorkingDirectory string
	// Stderr receives CLI diagnostics. A nil writer discards them.
	Stderr io.Writer
	// MaxOutputBytes limits buffered JSON, list, and transcript output.
	// Values <= 0 use the 16 MiB default. Streaming output is passed
	// directly to its writer.
	MaxOutputBytes int64
}

// Result contains the session ID from the CLI's JSON output, the result
// text, and the complete JSON response for callers that need other fields.
type Result struct {
	SessionID string
	Text      string
	JSON      []byte
}

// SessionEntry describes one stored transcript in the workspace's project
// directory: the session ID (filename without extension), file size, and
// modification time.
type SessionEntry struct {
	ID       string
	Size     int64
	Modified string
}

// Start creates a new session and sends its first prompt via stdin.
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

// Fork branches the supplied session ID and sends a prompt on the new
// branch. The source session history is unchanged.
func (c Client) Fork(ctx context.Context, sessionID, prompt string) (Result, error) {
	if sessionID == "" {
		return Result{}, fmt.Errorf("%w: session ID is required", ErrInvalidArgument)
	}
	return c.runJSON(ctx, prompt, sessionID, true)
}

// Stream sends a prompt in fresh, resumed, or forked mode and copies the
// CLI's native stream-json bytes to dst without interpreting event fields.
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
	return c.runPrompt(ctx, prompt, sessionID, fork, "stream-json", dst)
}

// List returns the stored sessions for the client's workspace, oldest ID
// first. A zero or negative limit returns all entries. The store holds
// every local session including headless runs, which the interactive
// session picker does not show.
func (c Client) List(ctx context.Context, limit int) ([]SessionEntry, error) {
	if err := ctx.Err(); err != nil {
		return nil, err
	}
	dir, err := c.projectDir()
	if err != nil {
		return nil, err
	}
	matches, err := filepath.Glob(filepath.Join(dir, "*.jsonl"))
	if err != nil {
		return nil, fmt.Errorf("claude-session-client: list session store: %w", err)
	}
	sort.Strings(matches)
	var out []SessionEntry
	for _, m := range matches {
		if limit > 0 && len(out) >= limit {
			break
		}
		fi, err := os.Stat(m)
		if err != nil {
			continue
		}
		out = append(out, SessionEntry{
			ID:       strings.TrimSuffix(filepath.Base(m), ".jsonl"),
			Size:     fi.Size(),
			Modified: fi.ModTime().UTC().Format("2006-01-02T15:04:05Z"),
		})
	}
	return out, nil
}

// Inspect returns the stored JSONL transcript for the selected session ID,
// verbatim. The ID must be a plain filename (letters, digits, hyphen,
// underscore); anything else is rejected without touching the filesystem.
func (c Client) Inspect(ctx context.Context, sessionID string) ([]byte, error) {
	if !validSessionID(sessionID) {
		return nil, fmt.Errorf("%w: session ID is required and must be a plain filename", ErrInvalidArgument)
	}
	if err := ctx.Err(); err != nil {
		return nil, err
	}
	dir, err := c.projectDir()
	if err != nil {
		return nil, err
	}
	limit := c.outputLimit()
	f, err := os.Open(filepath.Join(dir, sessionID+".jsonl"))
	if err != nil {
		return nil, fmt.Errorf("claude-session-client: open transcript: %w", err)
	}
	defer f.Close()
	data, err := io.ReadAll(io.LimitReader(f, limit+1))
	if err != nil {
		return nil, fmt.Errorf("claude-session-client: read transcript: %w", err)
	}
	if int64(len(data)) > limit {
		return nil, ErrOutputTooLarge
	}
	return data, nil
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
	return parseResult(output.Bytes())
}

// parseResult decodes the CLI's -p --output-format json array and returns
// the session ID and text of its result message.
func parseResult(data []byte) (Result, error) {
	var messages []struct {
		Type      string `json:"type"`
		Subtype   string `json:"subtype"`
		SessionID string `json:"session_id"`
		IsError   bool   `json:"is_error"`
		Result    string `json:"result"`
	}
	if err := json.Unmarshal(data, &messages); err != nil {
		return Result{}, fmt.Errorf("claude-session-client: decode headless JSON response: %w", err)
	}
	for _, m := range messages {
		if m.Type != "result" {
			continue
		}
		if m.SessionID == "" {
			return Result{}, errors.New("claude-session-client: result message has no session_id")
		}
		if m.IsError {
			return Result{}, fmt.Errorf("claude-session-client: result is error (subtype %q): %s", m.Subtype, truncate(m.Result, 300))
		}
		return Result{SessionID: m.SessionID, Text: m.Result, JSON: bytes.Clone(data)}, nil
	}
	return Result{}, ErrNoResult
}

func (c Client) runPrompt(ctx context.Context, prompt, sessionID string, fork bool, format string, dst io.Writer) error {
	if prompt == "" {
		return fmt.Errorf("%w: prompt is required", ErrInvalidArgument)
	}
	if fork && sessionID == "" {
		return fmt.Errorf("%w: fork requires an explicit session ID", ErrInvalidArgument)
	}
	args := []string{"-p", "--output-format", format}
	if sessionID != "" {
		args = append(args, "--resume", sessionID)
	}
	if fork {
		args = append(args, "--fork-session")
	}
	return c.run(ctx, args, prompt, dst)
}

func (c Client) run(ctx context.Context, args []string, prompt string, stdout io.Writer) error {
	binary := c.Binary
	if binary == "" {
		binary = "claude"
	}
	cmd := exec.CommandContext(ctx, binary, args...)
	cmd.Dir = c.WorkingDirectory
	cmd.Stdin = strings.NewReader(prompt)
	cmd.Stdout = stdout
	cmd.Stderr = c.Stderr
	if err := cmd.Run(); err != nil {
		return fmt.Errorf("claude-session-client: claude command failed: %w", err)
	}
	return nil
}

func (c Client) outputLimit() int64 {
	if c.MaxOutputBytes > 0 {
		return c.MaxOutputBytes
	}
	return defaultMaxOutputBytes
}

// projectDir resolves the workspace's transcript directory:
// $CLAUDE_CONFIG_DIR/projects/<encoded-cwd>/, or
// ~/.claude/projects/<encoded-cwd>/ when unset. The encoding replaces every
// non-alphanumeric byte with '-'; symlinks in the workspace path are
// resolved first because the CLI keys by the resolved cwd.
func (c Client) projectDir() (string, error) {
	base := os.Getenv("CLAUDE_CONFIG_DIR")
	if base == "" {
		home, err := os.UserHomeDir()
		if err != nil {
			return "", fmt.Errorf("claude-session-client: resolve home directory: %w", err)
		}
		base = filepath.Join(home, ".claude")
	}
	cwd := c.WorkingDirectory
	if cwd == "" {
		var err error
		cwd, err = os.Getwd()
		if err != nil {
			return "", fmt.Errorf("claude-session-client: resolve working directory: %w", err)
		}
	}
	if resolved, err := filepath.EvalSymlinks(cwd); err == nil {
		cwd = resolved
	}
	var b strings.Builder
	for i := 0; i < len(cwd); i++ {
		ch := cwd[i]
		if ch >= 'a' && ch <= 'z' || ch >= 'A' && ch <= 'Z' || ch >= '0' && ch <= '9' {
			b.WriteByte(ch)
		} else {
			b.WriteByte('-')
		}
	}
	return filepath.Join(base, "projects", b.String()), nil
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
