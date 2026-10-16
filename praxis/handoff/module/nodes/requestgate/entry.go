package requestgate

import (
	"encoding/json"
	"fmt"
	"strings"
)

type handoffRequest struct {
	Schema          string `json:"schema"`
	IdentityContext struct {
		OperatorIdentity          string `json:"operator_identity"`
		CurrentProductInteraction string `json:"current_product_interaction"`
		CurrentClientOrHarness    string `json:"current_client_or_harness"`
		CurrentChannel            string `json:"current_channel"`
		CurrentInferenceMechanism string `json:"current_inference_mechanism"`
		CurrentExecutionAdapter   string `json:"current_execution_adapter"`
	} `json:"identity_context"`
	Destination struct {
		Product            string `json:"product"`
		Harness            string `json:"harness"`
		ClientOrHarness    string `json:"client_or_harness"`
		Channel            string `json:"channel"`
		InferenceMechanism string `json:"inference_mechanism"`
		ExecutionAdapter   string `json:"execution_adapter"`
		Operation          string `json:"operation"`
		Route              string `json:"route"`
		Workspace          string `json:"workspace"`
		SessionID          string `json:"session_id"`
	} `json:"destination"`
	Task struct {
		DirectInstruction string   `json:"direct_instruction"`
		CurrentState      string   `json:"current_state"`
		NextAction        string   `json:"next_action"`
		Constraints       []string `json:"constraints"`
		Acceptance        []string `json:"acceptance_criteria"`
		EvidenceRefs      []string `json:"evidence_refs"`
	} `json:"task"`
}

func supportedHarness(name string) bool {
	switch name {
	case "amp", "antigravity", "claude", "cline", "codex", "copilot", "cursor", "droid", "gemini", "grok", "junie", "muse", "opencode", "openhands":
		return true
	default:
		return false
	}
}

func Validate(in map[string]any) (map[string]any, error) {
	raw, ok := in["request"]
	if !ok {
		return nil, fmt.Errorf("handoff_request: request is required")
	}
	encoded, err := json.Marshal(raw)
	if err != nil {
		return nil, fmt.Errorf("handoff_request: request cannot be decoded")
	}
	var request handoffRequest
	if err := json.Unmarshal(encoded, &request); err != nil {
		return nil, fmt.Errorf("handoff_request: request has an invalid shape")
	}
	if request.Schema != "harness.handoff_request.v1" {
		return nil, fmt.Errorf("handoff_request: unsupported request schema")
	}
	if !supportedHarness(request.Destination.Harness) {
		return nil, fmt.Errorf("handoff_request: destination harness must be explicit and supported")
	}
	if strings.TrimSpace(request.Task.DirectInstruction) == "" {
		return nil, fmt.Errorf("handoff_request: direct operator instruction is required")
	}
	if strings.TrimSpace(request.Task.NextAction) == "" || len(request.Task.Acceptance) == 0 {
		return nil, fmt.Errorf("handoff_request: next action and acceptance criteria are required")
	}
	if strings.TrimSpace(request.Destination.Product) == "" ||
		strings.TrimSpace(request.Destination.ClientOrHarness) == "" ||
		strings.TrimSpace(request.Destination.Channel) == "" ||
		strings.TrimSpace(request.Destination.InferenceMechanism) == "" ||
		strings.TrimSpace(request.Destination.ExecutionAdapter) == "" {
		return nil, fmt.Errorf("handoff_request: destination product, client, channel, inference mechanism, and execution adapter must be explicit")
	}
	switch request.Destination.Operation {
	case "fresh":
		if request.Destination.Route == "manual" || strings.TrimSpace(request.Destination.Workspace) == "" {
			return nil, fmt.Errorf("handoff_request: fresh execution requires an explicit workspace and cli or sdk route")
		}
	case "continue":
		if request.Destination.Route == "manual" || strings.TrimSpace(request.Destination.SessionID) == "" {
			return nil, fmt.Errorf("handoff_request: continue requires an exact session id and cli or sdk route")
		}
	case "manual":
		if request.Destination.Route != "manual" {
			return nil, fmt.Errorf("handoff_request: manual operation requires the manual route")
		}
	default:
		return nil, fmt.Errorf("handoff_request: operation must be fresh, continue, or manual")
	}
	if request.Destination.Route != "cli" && request.Destination.Route != "sdk" && request.Destination.Route != "manual" {
		return nil, fmt.Errorf("handoff_request: route must be explicit and supported")
	}
	return map[string]any{"request": raw}, nil
}
