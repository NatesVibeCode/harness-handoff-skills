// Package codexsession is a dependency-free client for documented Codex CLI
// session operations (codex exec). It delegates authentication and provider
// traffic to the installed codex executable and reads the documented local
// session store for list/inspect.
package codexsession

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"io/fs"
	"os"
	"os/exec"
	"path/filepath"
	"sort"
	"strings"
)

const defaultMaxOutputBytes int64 = 16 << 20

// maxMetaBytes bounds the first line read from each stored session file.
const maxMetaBytes = 1 << 20

var (
	ErrInvalidArgument = errors.New("codex-session-client: invalid argument")
	ErrOutputTooLarge  = errors.New("codex-session-client: output exceeds configured limit")
	ErrNoThread        = errors.New("codex-session-client: CLI output has no thread.started event")
	ErrSessionNotFound = errors.New("codex-session-client: session not found in local store")
)

// Client invokes the installed Codex CLI. Authentication remains in the
// CLI's configured credentials or runtime environment; this type never
// stores or reads credential values.
type Client struct {
	// Binary is the executable path. Empty uses "codex" from PATH.
	Binary string
	// WorkingDirectory selects the workspace and session store context. Empty
	// inherits the caller's current directory.
	WorkingDirectory string
	// SkipGitRepoCheck allows execution outside a Git repository only when the
	// caller has deliberately selected that exception. The default is false.
	SkipGitRepoCheck bool
	// Stderr receives CLI diagnostics. A nil writer discards them.
	Stderr io.Writer
	// MaxOutputBytes limits buffered JSON, list, and transcript output.
	// Values <= 0 use the 16 MiB default. Streaming output is passed
	// directly to its writer.
	MaxOutputBytes int64
}

// Result contains the thread/session ID from the CLI's JSONL output, the
// final agent message text, and the complete JSONL bytes for callers that
// need other fields.
type Result struct {
	SessionID string
	Text      string
	JSON      []byte
}

// SessionEntry describes one stored session: the session ID, the workspace
// cwd recorded in its metadata, file size, and modification time.
type SessionEntry struct {
	ID       string
	Cwd      string
	Size     int64
	Modified string
}

// Start creates a new session and sends its first prompt via stdin.
func (c Client) Start(ctx context.Context, prompt string) (Result, error) {
	return c.runJSON(ctx, prompt, "", false, false)
}

// Resume continues exactly the supplied session ID and sends a prompt.
// It is outside the fresh-only codex-harness-handoff contract, which
// forbids continuation: handoff lanes must use Start only.
func (c Client) Resume(ctx context.Context, sessionID, prompt string) (Result, error) {
	if !validSessionID(sessionID) {
		return Result{}, fmt.Errorf("%w: an exact session ID is required", ErrInvalidArgument)
	}
	return c.runJSON(ctx, prompt, sessionID, false, true)
}

// Fork branches the supplied session ID and sends a prompt on the new
// thread. The source session history is unchanged. Like Resume, forking is
// outside the fresh-only codex-harness-handoff contract: handoff lanes must
// use Start only.
func (c Client) Fork(ctx context.Context, sessionID, prompt string) (Result, error) {
	if !validSessionID(sessionID) {
		return Result{}, fmt.Errorf("%w: an exact session ID is required", ErrInvalidArgument)
	}
	return c.runJSON(ctx, prompt, sessionID, true, true)
}

// Stream sends a prompt in fresh, resumed, or forked mode and copies the
// CLI's native --json JSONL bytes to dst without interpreting events.
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
	resume := sessionID != ""
	return c.runPrompt(ctx, prompt, sessionID, fork, resume, dst)
}

// List returns the stored sessions for the client's workspace, oldest ID
// first. A zero or negative limit returns all entries.
func (c Client) List(ctx context.Context, limit int) ([]SessionEntry, error) {
	if err := ctx.Err(); err != nil {
		return nil, err
	}
	dir, err := c.sessionsDir()
	if err != nil {
		return nil, err
	}
	keys := c.workspaceKeys()
	var out []SessionEntry
	err = walkSessionFiles(dir, func(path string, fi fs.FileInfo) error {
		if limit > 0 && len(out) >= limit {
			return errStopWalk
		}
		id, cwd, ok := readSessionMeta(path)
		if !ok {
			return nil
		}
		if !matchWorkspace(cwd, keys) {
			if roots := readSessionRoots(path); !matchAnyWorkspace(roots, keys) {
				return nil
			}
		}
		out = append(out, SessionEntry{
			ID:       id,
			Cwd:      cwd,
			Size:     fi.Size(),
			Modified: fi.ModTime().UTC().Format("2006-01-02T15:04:05Z"),
		})
		return nil
	})
	if err != nil {
		return nil, err
	}
	sort.Slice(out, func(i, j int) bool { return out[i].ID < out[j].ID })
	return out, nil
}

// Inspect returns the stored JSONL transcript for an exact session ID in the
// selected workspace, verbatim. The ID must be a plain token (letters, digits,
// hyphen, underscore); anything else is rejected before filesystem access.
func (c Client) Inspect(ctx context.Context, sessionID string) ([]byte, error) {
	if !validSessionID(sessionID) {
		return nil, fmt.Errorf("%w: session ID is required and must be a plain token", ErrInvalidArgument)
	}
	if err := ctx.Err(); err != nil {
		return nil, err
	}
	dir, err := c.sessionsDir()
	if err != nil {
		return nil, err
	}
	var found string
	keys := c.workspaceKeys()
	err = walkSessionFiles(dir, func(path string, _ fs.FileInfo) error {
		if id, cwd, ok := readSessionMeta(path); ok && id == sessionID {
			if matchWorkspace(cwd, keys) || matchAnyWorkspace(readSessionRoots(path), keys) {
				found = path
				return errStopWalk
			}
		}
		return nil
	})
	if err != nil {
		return nil, err
	}
	if found == "" {
		return nil, fmt.Errorf("%w: %s", ErrSessionNotFound, sessionID)
	}
	limit := c.outputLimit()
	f, err := os.Open(found)
	if err != nil {
		return nil, fmt.Errorf("codex-session-client: open transcript: %w", err)
	}
	defer f.Close()
	data, err := io.ReadAll(io.LimitReader(f, limit+1))
	if err != nil {
		return nil, fmt.Errorf("codex-session-client: read transcript: %w", err)
	}
	if int64(len(data)) > limit {
		return nil, ErrOutputTooLarge
	}
	return data, nil
}

func (c Client) runJSON(ctx context.Context, prompt, sessionID string, fork, resume bool) (Result, error) {
	if prompt == "" {
		return Result{}, fmt.Errorf("%w: prompt is required", ErrInvalidArgument)
	}
	if fork && sessionID == "" {
		return Result{}, fmt.Errorf("%w: fork requires an explicit session ID", ErrInvalidArgument)
	}
	var output limitedBuffer
	output.limit = c.outputLimit()
	if err := c.runPrompt(ctx, prompt, sessionID, fork, resume, &output); err != nil {
		if errors.Is(err, ErrOutputTooLarge) {
			return Result{}, err
		}
		return Result{}, err
	}
	return parseEvents(output.Bytes())
}

// parseEvents decodes codex exec --json JSONL: the thread ID comes from
// thread.started and the text from the last agent_message item. Documented
// failure events (turn.failed, error) become errors carrying the raw event.
func parseEvents(data []byte) (Result, error) {
	dec := json.NewDecoder(bytes.NewReader(data))
	var threadID, lastText string
	for {
		var ev execEvent
		if err := dec.Decode(&ev); err != nil {
			if errors.Is(err, io.EOF) {
				break
			}
			return Result{}, fmt.Errorf("codex-session-client: decode exec JSONL: %w", err)
		}
		switch ev.Type {
		case "thread.started":
			if threadID == "" && ev.ThreadID != "" {
				threadID = ev.ThreadID
			}
		case "item.completed":
			if ev.Item != nil && ev.Item.Type == "agent_message" {
				lastText = ev.Item.Text
			}
		case "turn.failed", "error":
			detail := ev.Message
			if detail == "" {
				detail = ev.Error
			}
			return Result{}, fmt.Errorf("codex-session-client: exec reported %s: %s", ev.Type, truncate(detail, 300))
		}
	}
	if threadID == "" {
		return Result{}, ErrNoThread
	}
	return Result{SessionID: threadID, Text: lastText, JSON: bytes.Clone(data)}, nil
}

type execEvent struct {
	Type     string     `json:"type"`
	ThreadID string     `json:"thread_id"`
	Message  string     `json:"message"`
	Error    string     `json:"error"`
	Item     *eventItem `json:"item"`
}

type eventItem struct {
	Type string `json:"type"`
	Text string `json:"text"`
}

func (c Client) runPrompt(ctx context.Context, prompt, sessionID string, fork, resume bool, dst io.Writer) error {
	if prompt == "" {
		return fmt.Errorf("%w: prompt is required", ErrInvalidArgument)
	}
	if (fork || resume) && !validSessionID(sessionID) {
		return fmt.Errorf("%w: resume or fork requires an exact session ID", ErrInvalidArgument)
	}
	args := c.argv(sessionID, fork, resume)
	return c.run(ctx, args, prompt, dst)
}

func (c Client) argv(sessionID string, fork, resume bool) []string {
	var args []string
	switch {
	case fork:
		args = []string{"exec", "fork", sessionID}
	case resume:
		args = []string{"exec", "resume", sessionID}
	default:
		args = []string{"exec"}
		if c.WorkingDirectory != "" {
			args = append(args, "-C", c.WorkingDirectory)
		}
	}
	args = append(args, "-c", `sandbox_mode="workspace-write"`, "-c", `approval_policy="never"`, "--json")
	if c.SkipGitRepoCheck {
		args = append(args, "--skip-git-repo-check")
	}
	return append(args, "-")
}

func (c Client) run(ctx context.Context, args []string, prompt string, stdout io.Writer) error {
	binary := c.Binary
	if binary == "" {
		binary = "codex"
	}
	cmd := exec.CommandContext(ctx, binary, args...)
	cmd.Dir = c.WorkingDirectory
	cmd.Stdin = strings.NewReader(prompt)
	cmd.Stdout = stdout
	cmd.Stderr = c.Stderr
	if err := cmd.Run(); err != nil {
		return fmt.Errorf("codex-session-client: codex command failed: %w", err)
	}
	return nil
}

func (c Client) outputLimit() int64 {
	if c.MaxOutputBytes > 0 {
		return c.MaxOutputBytes
	}
	return defaultMaxOutputBytes
}

// sessionsDir resolves the local session store: $CODEX_HOME/sessions, or
// ~/.codex/sessions when CODEX_HOME is unset.
func (c Client) sessionsDir() (string, error) {
	base := os.Getenv("CODEX_HOME")
	if base == "" {
		home, err := os.UserHomeDir()
		if err != nil {
			return "", fmt.Errorf("codex-session-client: resolve home directory: %w", err)
		}
		base = filepath.Join(home, ".codex")
	}
	return filepath.Join(base, "sessions"), nil
}

// workspaceKeys returns the workspace path in raw and symlink-resolved form
// for matching stored session metadata.
func (c Client) workspaceKeys() []string {
	cwd := c.WorkingDirectory
	if cwd == "" {
		if got, err := os.Getwd(); err == nil {
			cwd = got
		}
	}
	keys := []string{cwd}
	if resolved, err := filepath.EvalSymlinks(cwd); err == nil && resolved != cwd {
		keys = append(keys, resolved)
	}
	return keys
}

var errStopWalk = errors.New("stop walk")

// walkSessionFiles visits *.jsonl files under dir without assuming any
// deeper layout. A missing store yields no files and no error.
func walkSessionFiles(dir string, visit func(path string, fi fs.FileInfo) error) error {
	err := filepath.WalkDir(dir, func(path string, d fs.DirEntry, err error) error {
		if err != nil {
			if os.IsNotExist(err) {
				return nil
			}
			return err
		}
		if d.IsDir() || d.Type()&os.ModeSymlink != 0 || !strings.HasSuffix(d.Name(), ".jsonl") {
			return nil
		}
		fi, err := d.Info()
		if err != nil {
			return nil
		}
		return visit(path, fi)
	})
	if errors.Is(err, errStopWalk) {
		return nil
	}
	if os.IsNotExist(err) {
		return nil
	}
	return err
}

// readSessionMeta returns the session ID and cwd from a stored file's
// leading session_meta line.
func readSessionMeta(path string) (id, cwd string, ok bool) {
	line, ok := firstLine(path)
	if !ok {
		return "", "", false
	}
	var meta struct {
		Type    string `json:"type"`
		Payload struct {
			ID      string `json:"id"`
			Session string `json:"session_id"`
			Cwd     string `json:"cwd"`
		} `json:"payload"`
	}
	if err := json.Unmarshal(line, &meta); err != nil || meta.Type != "session_meta" {
		return "", "", false
	}
	id = meta.Payload.Session
	if id == "" {
		id = meta.Payload.ID
	}
	if id == "" {
		return "", "", false
	}
	return id, meta.Payload.Cwd, true
}

// readSessionRoots returns the runtime workspace roots from a stored file's
// leading session_meta line.
func readSessionRoots(path string) []string {
	line, ok := firstLine(path)
	if !ok {
		return nil
	}
	var meta struct {
		Payload struct {
			Roots []string `json:"runtime_workspace_roots"`
		} `json:"payload"`
	}
	if err := json.Unmarshal(line, &meta); err != nil {
		return nil
	}
	return meta.Payload.Roots
}

func firstLine(path string) ([]byte, bool) {
	f, err := os.Open(path)
	if err != nil {
		return nil, false
	}
	defer f.Close()
	data, err := io.ReadAll(io.LimitReader(f, maxMetaBytes))
	if err != nil || len(data) == 0 {
		return nil, false
	}
	if i := bytes.IndexByte(data, '\n'); i >= 0 {
		data = data[:i]
	}
	return data, true
}

func matchWorkspace(cwd string, keys []string) bool {
	return matchAnyWorkspace([]string{cwd}, keys)
}

func matchAnyWorkspace(values, keys []string) bool {
	for _, v := range values {
		if v == "" {
			continue
		}
		for _, k := range keys {
			if k != "" && v == k {
				return true
			}
		}
	}
	return false
}

func validSessionID(id string) bool {
	if id == "" || len(id) > 128 {
		return false
	}
	if id[0] == '-' || strings.EqualFold(id, "latest") || strings.EqualFold(id, "last") || strings.EqualFold(id, "newest") || strings.EqualFold(id, "continue") {
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
