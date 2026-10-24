package sdkdispatch

import "errors"

// Run exists only to satisfy Forge's sealed dispatch package. The printed
// worker binds harness Nodes to its pinned SDK runtime before execution.
func Run(map[string]any) (map[string]any, error) {
	return nil, errors.New("harness SDK Node requires the printed SDK runtime")
}
