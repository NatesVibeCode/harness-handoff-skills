package main

import (
	"encoding/json"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
)

const goHelpFixture = `Usage of fake:
  -api-key-env string
    	environment variable holding the API key (default "X")
  -budget int
    	context budget in bytes (0 = kernel default)
  -stream
    	emit frames on stdout while running
  -model string
    	provider model name
`

const gnuHelpFixture = `Usage: fake [OPTIONS]
  --model MODEL        provider model name
  --max-turns COUNT    model turns per submit
  --stream             emit frames
  --format[=FMT]       output format
`

func TestExtractGoFlags(t *testing.T) {
	got := extractFlags(goHelpFixture)
	want := []flagDef{
		{Flag: "api-key-env", Style: "go", Type: "string"},
		{Flag: "budget", Style: "go", Type: "int"},
		{Flag: "stream", Style: "go"},
		{Flag: "model", Style: "go", Type: "string"},
	}
	if len(got) != len(want) {
		t.Fatalf("got %v", got)
	}
	for i := range want {
		if got[i] != want[i] {
			t.Fatalf("flag %d: got %+v want %+v", i, got[i], want[i])
		}
	}
}

func TestExtractGnuFlags(t *testing.T) {
	got := extractFlags(gnuHelpFixture)
	if len(got) != 4 || got[0].Flag != "model" || got[0].Style != "gnu" {
		t.Fatalf("got %v", got)
	}
	if got[0].Type != "MODEL" || got[1].Type != "COUNT" || got[2].Type != "" || got[3].Type != "FMT" || got[3].Flag != "format[]" {
		t.Fatalf("optional-value flag: %v", got[3])
	}
}

func TestExtractEmpty(t *testing.T) {
	if got := extractFlags("no flags here\n  indented prose\n"); len(got) != 0 {
		t.Fatalf("got %v", got)
	}
}

func TestEmitDeterministicAndAccepted(t *testing.T) {
	c := contractDoc{
		Harness: "demo", Binary: "demo", PromptDelivery: "stdin", Parser: "text",
		OneshotArgv: []string{"demo", "<prompt-file>"}, Interactivity: "non_interactive",
		CredentialChannel: "env", CredentialAuth: "env",
		Evidence: evidenceRef{HelpSHA256: strings.Repeat("a", 64)},
	}
	a, err := emitContract(c)
	if err != nil {
		t.Fatal(err)
	}
	b, err := emitContract(c)
	if err != nil {
		t.Fatal(err)
	}
	if string(a) != string(b) {
		t.Fatal("emission unstable")
	}
	var spec contractDoc
	if err := json.Unmarshal(a, &spec); err != nil {
		t.Fatal(err)
	}
	if err := validateCandidate(spec); err != nil {
		t.Fatal(err)
	}
	if spec.Harness != "demo" || spec.Parser != "text" || len(spec.OneshotArgv) != 2 {
		t.Fatalf("parsed %+v", spec)
	}
}

func fakeBinary(t *testing.T, body string) string {
	t.Helper()
	dir := t.TempDir()
	p := filepath.Join(dir, "fakeharness")
	if err := os.WriteFile(p, []byte("#!/bin/sh\n"+body+"\n"), 0o755); err != nil {
		t.Fatal(err)
	}
	return p
}

func TestCLIRefusesWithoutOneshot(t *testing.T) {
	bin := fakeBinary(t, "cat <<'EOF'\n"+goHelpFixture+"EOF")
	dir := t.TempDir()
	out := filepath.Join(dir, "contract.json")
	code := runCLI([]string{"-harness", "demo", "-binary", bin, "-out", out,
		"-parser", "text", "-delivery", "stdin", "-interactivity", "non_interactive",
		"-credential-channel", "env", "-credential-auth", "env"})
	if code != 1 {
		t.Fatalf("exit %d, want refusal", code)
	}
	if _, err := os.Stat(out); !os.IsNotExist(err) {
		t.Fatal("contract written despite missing oneshot")
	}
	evRaw, err := os.ReadFile(out + ".evidence.json")
	if err != nil {
		t.Fatalf("evidence not kept: %v", err)
	}
	var ev evidenceDoc
	if err := json.Unmarshal(evRaw, &ev); err != nil {
		t.Fatal(err)
	}
	if ev.Slots["oneshot_argv"].Status != "missing" {
		t.Fatalf("oneshot slot: %+v", ev.Slots["oneshot_argv"])
	}
	if len(ev.Vocab) != 4 {
		t.Fatalf("vocab: %v", ev.Vocab)
	}
}

func TestCLIFullContract(t *testing.T) {
	bin := fakeBinary(t, "cat <<'EOF'\n"+goHelpFixture+"EOF")
	dir := t.TempDir()
	out := filepath.Join(dir, "contract.json")
	code := runCLI([]string{"-harness", "demo", "-binary", bin, "-out", out,
		"-parser", "text", "-delivery", "stdin", "-interactivity", "non_interactive",
		"-credential-channel", "env", "-credential-auth", "env",
		"-oneshot", "demo", "-oneshot", "<prompt-file>"})
	if code != 0 {
		t.Fatalf("exit %d", code)
	}
	raw, err := os.ReadFile(out)
	if err != nil {
		t.Fatal(err)
	}
	var c contractDoc
	if err := json.Unmarshal(raw, &c); err != nil {
		t.Fatal(err)
	}
	if err := validateCandidate(c); err != nil {
		t.Fatal(err)
	}
}

func TestCLIRefusesBadParser(t *testing.T) {
	bin := fakeBinary(t, "echo hi")
	dir := t.TempDir()
	code := runCLI([]string{"-harness", "demo", "-binary", bin,
		"-out", filepath.Join(dir, "c.json"), "-parser", "telepathy",
		"-delivery", "stdin", "-interactivity", "non_interactive",
		"-credential-channel", "env", "-credential-auth", "env",
		"-oneshot", "demo"})
	if code != 1 {
		t.Fatalf("exit %d, want refusal", code)
	}
}

func TestCLIMissingBinary(t *testing.T) {
	dir := t.TempDir()
	code := runCLI([]string{"-harness", "demo", "-binary", filepath.Join(dir, "absent"),
		"-out", filepath.Join(dir, "c.json")})
	if code != 1 {
		t.Fatalf("exit %d, want refusal", code)
	}
}

func TestSDKPinHermetic(t *testing.T) {
	if _, err := exec.LookPath("git"); err != nil {
		t.Skip("git absent")
	}
	if _, err := exec.LookPath("go"); err != nil {
		t.Skip("go absent")
	}
	dir := t.TempDir()
	git := func(args ...string) {
		t.Helper()
		cmd := exec.Command("git", args...)
		cmd.Dir = dir
		cmd.Env = append(os.Environ(), "GIT_CONFIG_NOSYSTEM=1", "GIT_AUTHOR_NAME=t", "GIT_AUTHOR_EMAIL=t@t", "GIT_COMMITTER_NAME=t", "GIT_COMMITTER_EMAIL=t@t")
		if out, err := cmd.CombinedOutput(); err != nil {
			t.Fatalf("git %v: %v\n%s", args, err, out)
		}
	}
	if err := os.WriteFile(filepath.Join(dir, "go.mod"), []byte("module example.test/pin\n\ngo 1.21\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(dir, "pin.go"), []byte("package pin\n\n// Submit sends one message.\nfunc Submit() {}\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	git("init", "-q")
	git("add", ".")
	git("commit", "-qm", "init")
	out := filepath.Join(dir, "sdk.json")
	code := runSDK([]string{"-module", "example.test/pin", "-package", "pin", "-symbol", "Submit", "-repo", dir, "-out", out})
	if code != 0 {
		t.Fatalf("exit %d", code)
	}
	raw, err := os.ReadFile(out)
	if err != nil {
		t.Fatal(err)
	}
	var ev evidenceDoc
	if err := json.Unmarshal(raw, &ev); err != nil {
		t.Fatal(err)
	}
	if ev.SDK["symbol"] != "Submit" || len(ev.SDK["repo_rev"]) != 40 || len(ev.SDK["godoc_sha256"]) != 64 {
		t.Fatalf("sdk pin: %v", ev.SDK)
	}
}
