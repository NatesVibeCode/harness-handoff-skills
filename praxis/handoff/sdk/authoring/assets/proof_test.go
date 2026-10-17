package sdkdispatch

import "testing"

// This local check covers the dispatch boundary only. Real SDK behavior is
// observed independently by Forge's printed SDK worker before admission.
func TestSDKDispatchRequiresPrintedRuntime(t *testing.T) {
	for _, inputs := range []map[string]any{nil, {}, {"prompt": "example", "workspace": "/tmp"}} {
		output, err := Run(inputs)
		if err == nil || output != nil {
			t.Fatal("direct dispatch must require the printed SDK runtime")
		}
	}
}
