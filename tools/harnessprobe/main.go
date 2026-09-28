// Command harnessprobe mechanically derives harness contract evidence:
// it resolves a harness binary, captures version and help bytes, extracts
// the flag vocabulary with an explicit grammar, and records every contract
// slot as probed, declared, or missing. It writes a contract.json only when
// all required slots are filled; otherwise it keeps the evidence file and
// refuses, naming what is missing. The sdk mode pins a Go SDK entry symbol
// (module, repo revision, godoc digest) the same way.
//
// Nothing is inferred: operator-declared deltas arrive as flags and are
// recorded as declared. Deterministic: same inputs, same bytes.
package main

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
	"time"
)

// Probe candidate vocabulary. Adoption goes through skills-src/contracts.json
// and scripts/build_skills.py; consumers independently validate admission.
var (
	validParsers       = map[string]bool{"json_object": true, "codex_jsonl": true, "muse_jsonl": true, "opencode_jsonl": true, "plain": true, "text": true}
	validDeliveries    = map[string]bool{"argv": true, "argv_last": true, "stdin": true, "file_flag": true}
	validInteractivity = map[string]bool{"prompts": true, "non_interactive": true}
	validCredChannels  = map[string]bool{"env": true, "stdin": true, "file": true, "keychain": true, "native-session": true}
)

type flagDef struct {
	Flag  string `json:"flag"`
	Style string `json:"style"`
	Type  string `json:"type,omitempty"`
}

var (
	goFlagRe  = regexp.MustCompile(`^  -([A-Za-z0-9][A-Za-z0-9_-]*)((?:\s+(?:int|string|bool|uint\w*|float\w*|duration))?)\s*$`)
	gnuFlagRe = regexp.MustCompile(`^[ \t]{2}--([A-Za-z0-9][A-Za-z0-9_-]*)(?:\[=([^]\s]+)\]|(?:=|[ \t])([^\s]+))?(?:[ \t]{2,}.*)?[ \t]*$`)
)

// extractFlags parses flag definitions from --help text with two explicit
// grammars: Go single-dash (`  -name type`) and GNU double-dash
// (`  --name[=TYPE]`). Description continuation lines are ignored. Order
// preserved, first occurrence wins.
func extractFlags(help string) []flagDef {
	var out []flagDef
	seen := map[string]bool{}
	for _, line := range strings.Split(help, "\n") {
		if m := goFlagRe.FindStringSubmatch(line); m != nil {
			if !seen[m[1]] {
				seen[m[1]] = true
				out = append(out, flagDef{Flag: m[1], Style: "go", Type: strings.TrimSpace(m[2])})
			}
			continue
		}
		if m := gnuFlagRe.FindStringSubmatch(line); m != nil {
			name := m[1]
			if m[2] != "" {
				name += "[]"
			}
			if !seen[name] {
				seen[name] = true
				valueType := m[3]
				if m[2] != "" {
					valueType = m[2]
				}
				out = append(out, flagDef{Flag: name, Style: "gnu", Type: valueType})
			}
		}
	}
	return out
}

func sha256Hex(raw []byte) string {
	sum := sha256.Sum256(raw)
	return hex.EncodeToString(sum[:])
}

func runCapture(timeout time.Duration, dir, name string, args ...string) ([]byte, int, error) {
	ctx, cancel := context.WithTimeout(context.Background(), timeout)
	defer cancel()
	cmd := exec.CommandContext(ctx, name, args...)
	if dir != "" {
		cmd.Dir = dir
	}
	var buf bytes.Buffer
	cmd.Stdout = &buf
	cmd.Stderr = &buf
	err := cmd.Run()
	code := 0
	if err != nil {
		if ee, ok := err.(*exec.ExitError); ok {
			code = ee.ExitCode()
		} else {
			return nil, -1, err
		}
	}
	return buf.Bytes(), code, nil
}

// ---- evidence model ----

type slotProvenance struct {
	Status string `json:"status"`
	Value  any    `json:"value,omitempty"`
	Note   string `json:"note,omitempty"`
}

type evidenceDoc struct {
	Schema   string                    `json:"schema"`
	Harness  string                    `json:"harness"`
	Mode     string                    `json:"mode"`
	Binary   string                    `json:"binary,omitempty"`
	Resolved string                    `json:"resolved_path,omitempty"`
	Version  map[string]string         `json:"version,omitempty"`
	Help     map[string]string         `json:"help,omitempty"`
	Vocab    []flagDef                 `json:"advisory_vocabulary,omitempty"`
	SDK      map[string]string         `json:"sdk,omitempty"`
	Slots    map[string]slotProvenance `json:"slots,omitempty"`
	Refused  []string                  `json:"refused_contract_missing,omitempty"`
}

// ---- contract emission (fixed field order, byte-stable) ----

type contractDoc struct {
	Harness            string      `json:"harness"`
	Skill              string      `json:"skill,omitempty"`
	Binary             string      `json:"binary"`
	PromptDelivery     string      `json:"prompt_delivery"`
	PromptFileFlag     string      `json:"prompt_file_flag,omitempty"`
	Parser             string      `json:"parser"`
	ModelFromRoute     bool        `json:"model_from_route,omitempty"`
	CallWorkdir        bool        `json:"call_workdir,omitempty"`
	TaskConfigStrategy string      `json:"task_config_strategy,omitempty"`
	OneshotArgv        []string    `json:"oneshot_argv"`
	Interactivity      string      `json:"interactivity"`
	CredentialChannel  string      `json:"credential_channel"`
	CredentialAuth     string      `json:"credential_auth"`
	Evidence           evidenceRef `json:"evidence"`
}

type evidenceRef struct {
	HelpSHA256    string `json:"help_sha256"`
	VersionSHA256 string `json:"version_sha256,omitempty"`
}

// validateCandidate checks this probe's typed candidate. It grants no admission
// and does not replace the generator's validation or a consumer's own checks.
func validateCandidate(c contractDoc) error {
	if strings.TrimSpace(c.Harness) == "" {
		return errors.New("harness name required")
	}
	if strings.TrimSpace(c.Binary) == "" || strings.ContainsAny(c.Binary, " \t\r\n") {
		return errors.New("binary name required without whitespace")
	}
	if !validParsers[c.Parser] || !validDeliveries[c.PromptDelivery] || !validInteractivity[c.Interactivity] || !validCredChannels[c.CredentialChannel] || !validCredChannels[c.CredentialAuth] {
		return errors.New("invalid launch vocabulary")
	}
	if c.PromptDelivery == "file_flag" && strings.TrimSpace(c.PromptFileFlag) == "" {
		return errors.New("file_flag delivery requires prompt_file_flag")
	}
	if len(c.OneshotArgv) == 0 {
		return errors.New("oneshot_argv required")
	}
	for _, arg := range c.OneshotArgv {
		if strings.TrimSpace(arg) == "" {
			return errors.New("empty oneshot_argv entry")
		}
	}
	return nil
}

func emitContract(c contractDoc) ([]byte, error) {
	raw, err := json.MarshalIndent(c, "", "  ")
	if err != nil {
		return nil, err
	}
	return append(raw, '\n'), nil
}

func writeFile(path string, raw []byte) error {
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return err
	}
	return os.WriteFile(path, raw, 0o644)
}

type oneshotList []string

func (o *oneshotList) String() string     { return strings.Join(*o, " ") }
func (o *oneshotList) Set(v string) error { *o = append(*o, v); return nil }

// ---- cli mode ----

func runCLI(args []string) int {
	fs := flag.NewFlagSet("cli", flag.ExitOnError)
	harness := fs.String("harness", "", "harness name, no spaces (required)")
	binary := fs.String("binary", "", "binary path or name; defaults to PATH resolve of -harness")
	versionArgs := fs.String("version-args", "version,--version,-version", "comma-separated version probes tried in order")
	helpArg := fs.String("help-arg", "--help", "help probe argument")
	timeout := fs.Duration("timeout", 30*time.Second, "per-probe timeout")
	out := fs.String("out", "", "candidate JSON output path outside generated skill trees (required)")
	evidenceOut := fs.String("evidence-out", "", "evidence output path (defaults to <out>.evidence.json)")
	parser := fs.String("parser", "", "DECLARED output parser")
	delivery := fs.String("delivery", "", "DECLARED prompt delivery")
	promptFileFlag := fs.String("prompt-file-flag", "", "DECLARED prompt file flag (delivery=file_flag)")
	interactivity := fs.String("interactivity", "", "DECLARED interactivity")
	credChannel := fs.String("credential-channel", "", "DECLARED credential channel")
	credAuth := fs.String("credential-auth", "", "DECLARED credential auth")
	modelFromRoute := fs.Bool("model-from-route", false, "DECLARED model from route")
	callWorkdir := fs.Bool("call-workdir", false, "DECLARED call workdir")
	skill := fs.String("skill", "", "DECLARED skill name")
	taskStrategy := fs.String("task-config-strategy", "", "DECLARED task config strategy")
	var oneshot oneshotList
	fs.Var(&oneshot, "oneshot", "DECLARED oneshot argv element (repeatable, order kept)")
	fs.Parse(args)
	if strings.TrimSpace(*harness) == "" || strings.Contains(*harness, " ") || *out == "" {
		fmt.Fprintln(os.Stderr, "harnessprobe cli: -harness (no spaces) and -out are required")
		return 2
	}
	if *evidenceOut == "" {
		*evidenceOut = *out + ".evidence.json"
	}
	bin := *binary
	if bin == "" {
		bin = *harness
	}
	resolved, err := exec.LookPath(bin)
	if err != nil {
		abs, aerr := filepath.Abs(bin)
		if aerr != nil {
			fmt.Fprintln(os.Stderr, "harnessprobe: binary unresolvable: "+bin)
			return 1
		}
		resolved = abs
		if _, serr := os.Stat(resolved); serr != nil {
			fmt.Fprintln(os.Stderr, "harnessprobe: binary absent: "+resolved)
			return 1
		}
	}
	ev := evidenceDoc{Schema: "harnessprobe.evidence.v1", Harness: *harness, Mode: "cli",
		Binary: filepath.Base(resolved), Resolved: resolved, Slots: map[string]slotProvenance{}}
	ev.Slots["binary"] = slotProvenance{Status: "probed", Value: filepath.Base(resolved), Note: "PATH resolution: " + resolved}
	var versionBytes []byte
	versionArgUsed := ""
	for _, va := range strings.Split(*versionArgs, ",") {
		va = strings.TrimSpace(va)
		if va == "" {
			continue
		}
		raw, code, err := runCapture(*timeout, "", resolved, va)
		if err == nil && code == 0 {
			versionBytes, versionArgUsed = raw, va
			break
		}
	}
	ev.Version = map[string]string{"arg": versionArgUsed, "sha256": sha256Hex(versionBytes), "present": fmt.Sprint(len(versionBytes) > 0)}
	ev.Slots["version"] = slotProvenance{Status: "probed", Value: map[string]string{"arg": versionArgUsed, "sha256": sha256Hex(versionBytes)}}
	helpBytes, code, err := runCapture(*timeout, "", resolved, *helpArg)
	if err != nil || code != 0 {
		fmt.Fprintf(os.Stderr, "harnessprobe: help probe refused (exit %d): %v\n", code, err)
		return 1
	}
	ev.Help = map[string]string{"arg": *helpArg, "sha256": sha256Hex(helpBytes), "bytes": fmt.Sprint(len(helpBytes))}
	ev.Vocab = extractFlags(string(helpBytes))
	declare := func(name, value string, valid map[string]bool) {
		if value == "" {
			ev.Slots[name] = slotProvenance{Status: "missing"}
			return
		}
		if valid != nil && !valid[value] {
			ev.Slots[name] = slotProvenance{Status: "refused", Value: value, Note: "outside bound vocabulary"}
			return
		}
		ev.Slots[name] = slotProvenance{Status: "declared", Value: value}
	}
	declare("parser", *parser, validParsers)
	declare("prompt_delivery", *delivery, validDeliveries)
	declare("interactivity", *interactivity, validInteractivity)
	declare("credential_channel", *credChannel, validCredChannels)
	declare("credential_auth", *credAuth, validCredChannels)
	if *promptFileFlag != "" {
		ev.Slots["prompt_file_flag"] = slotProvenance{Status: "declared", Value: *promptFileFlag}
	}
	if len(oneshot) > 0 {
		ev.Slots["oneshot_argv"] = slotProvenance{Status: "declared", Value: []string(oneshot)}
	} else {
		ev.Slots["oneshot_argv"] = slotProvenance{Status: "missing", Note: "no verified one-shot invocation; refusing rather than inventing one"}
	}
	evRaw, err := json.MarshalIndent(ev, "", "  ")
	if err != nil {
		fmt.Fprintln(os.Stderr, "harnessprobe: "+err.Error())
		return 1
	}
	evRaw = append(evRaw, '\n')
	if err := writeFile(*evidenceOut, evRaw); err != nil {
		fmt.Fprintln(os.Stderr, "harnessprobe: "+err.Error())
		return 1
	}
	var missing, refused []string
	for _, name := range []string{"parser", "prompt_delivery", "interactivity", "credential_channel", "credential_auth", "oneshot_argv"} {
		switch ev.Slots[name].Status {
		case "missing":
			missing = append(missing, name)
		case "refused":
			refused = append(refused, name)
		}
	}
	if *delivery == "file_flag" && *promptFileFlag == "" {
		missing = append(missing, "prompt_file_flag")
	}
	if len(missing) > 0 || len(refused) > 0 {
		sort.Strings(missing)
		sort.Strings(refused)
		fmt.Fprintf(os.Stderr, "harnessprobe: contract refused (missing=%v refused=%v); evidence kept at %s\n", missing, refused, *evidenceOut)
		return 1
	}
	c := contractDoc{
		Harness: *harness, Skill: *skill, Binary: filepath.Base(resolved),
		PromptDelivery: *delivery, PromptFileFlag: *promptFileFlag, Parser: *parser,
		ModelFromRoute: *modelFromRoute, CallWorkdir: *callWorkdir,
		TaskConfigStrategy: *taskStrategy, OneshotArgv: []string(oneshot),
		Interactivity: *interactivity, CredentialChannel: *credChannel, CredentialAuth: *credAuth,
		Evidence: evidenceRef{HelpSHA256: sha256Hex(helpBytes), VersionSHA256: sha256Hex(versionBytes)},
	}
	raw, err := emitContract(c)
	if err != nil {
		fmt.Fprintln(os.Stderr, "harnessprobe: "+err.Error())
		return 1
	}
	again, err := emitContract(c)
	if err != nil || !bytes.Equal(raw, again) {
		fmt.Fprintln(os.Stderr, "harnessprobe: emission unstable")
		return 1
	}
	if err := validateCandidate(c); err != nil {
		fmt.Fprintf(os.Stderr, "harnessprobe: candidate refused: %v\n", err)
		return 1
	}
	if err := writeFile(*out, raw); err != nil {
		fmt.Fprintln(os.Stderr, "harnessprobe: "+err.Error())
		return 1
	}
	fmt.Printf("candidate %s written to %s; evidence %s\n", *harness, *out, *evidenceOut)
	return 0
}

// ---- sdk mode ----

func runSDK(args []string) int {
	fs := flag.NewFlagSet("sdk", flag.ExitOnError)
	module := fs.String("module", "", "Go module path (required)")
	pkg := fs.String("package", "", "package path within module (required)")
	symbol := fs.String("symbol", "", "entry symbol, e.g. Session.Submit (required)")
	repo := fs.String("repo", "", "module checkout dir for revision + godoc (required)")
	timeout := fs.Duration("timeout", 60*time.Second, "godoc timeout")
	out := fs.String("out", "", "sdk evidence output path (required)")
	fs.Parse(args)
	if *module == "" || *pkg == "" || *symbol == "" || *repo == "" || *out == "" {
		fmt.Fprintln(os.Stderr, "harnessprobe sdk: -module, -package, -symbol, -repo, -out are required")
		return 2
	}
	revBytes, code, err := runCapture(*timeout, "", "git", "-C", *repo, "rev-parse", "HEAD")
	if err != nil || code != 0 {
		fmt.Fprintln(os.Stderr, "harnessprobe: repo revision unavailable")
		return 1
	}
	rev := strings.TrimSpace(string(revBytes))
	docBytes, code, err := runCapture(*timeout, *repo, "go", "doc", *pkg+"."+*symbol)
	if err != nil || code != 0 {
		fmt.Fprintln(os.Stderr, "harnessprobe: godoc unavailable for "+*pkg+"."+*symbol)
		return 1
	}
	ev := evidenceDoc{Schema: "harnessprobe.evidence.v1", Mode: "sdk",
		SDK: map[string]string{"module": *module, "package": *pkg, "symbol": *symbol, "repo_rev": rev, "godoc_sha256": sha256Hex(docBytes)},
		Slots: map[string]slotProvenance{
			"entry": {Status: "probed", Value: *pkg + "." + *symbol, Note: "godoc digest binds the entry signature"},
		}}
	evRaw, err := json.MarshalIndent(ev, "", "  ")
	if err != nil {
		fmt.Fprintln(os.Stderr, "harnessprobe: "+err.Error())
		return 1
	}
	evRaw = append(evRaw, '\n')
	if err := writeFile(*out, evRaw); err != nil {
		fmt.Fprintln(os.Stderr, "harnessprobe: "+err.Error())
		return 1
	}
	fmt.Printf("sdk pin %s.%s rev %s godoc %s\n", *pkg, *symbol, rev[:12], sha256Hex(docBytes)[:12])
	return 0
}

func main() {
	if len(os.Args) < 2 {
		fmt.Fprintln(os.Stderr, "usage: harnessprobe <cli|sdk> [flags]")
		os.Exit(2)
	}
	switch os.Args[1] {
	case "cli":
		os.Exit(runCLI(os.Args[2:]))
	case "sdk":
		os.Exit(runSDK(os.Args[2:]))
	default:
		fmt.Fprintln(os.Stderr, "usage: harnessprobe <cli|sdk> [flags]")
		os.Exit(2)
	}
}
