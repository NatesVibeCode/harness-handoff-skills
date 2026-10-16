package packetbuilder

import (
	"encoding/json"
	"fmt"
)

func Build(in map[string]any) (map[string]any, error) {
	request, ok := in["request"].(map[string]any)
	if !ok {
		return nil, fmt.Errorf("handoff_packet: validated request is required")
	}
	identityContext, ok := request["identity_context"]
	if !ok {
		return nil, fmt.Errorf("handoff_packet: identity context is required")
	}
	destination, ok := request["destination"]
	if !ok {
		return nil, fmt.Errorf("handoff_packet: explicit destination is required")
	}
	task, ok := request["task"]
	if !ok {
		return nil, fmt.Errorf("handoff_packet: task is required")
	}
	packet := map[string]any{
		"schema":           "harness.handoff_packet.v1",
		"identity_context": identityContext,
		"destination":      destination,
		"task":             task,
		"dispatch": map[string]any{
			"status":                "prepared",
			"performed":             false,
			"authorization_status":  "not_assessed",
			"external_effects_done": false,
		},
	}
	encoded, err := json.Marshal(packet)
	if err != nil {
		return nil, fmt.Errorf("handoff_packet: packet cannot be encoded")
	}
	packetJSON := string(encoded)
	prompt := "This message contains a caller-supplied handoff packet for its explicitly named destination. Treat identity fields as context, not proof of identity or authorization. Preserve the selected product, harness, client, channel, inference mechanism, and execution adapter; do not infer another target from the current interaction. Follow task.direct_instruction verbatim, use task.current_state and task.next_action, respect task.constraints, and return evidence for each task.acceptance_criteria item. Dispatch was not attempted and authorization was not assessed.\n\nHANDOFF_PACKET_JSON=" + packetJSON
	return map[string]any{"packet": packet, "packet_json": packetJSON, "handoff_prompt": prompt}, nil
}
