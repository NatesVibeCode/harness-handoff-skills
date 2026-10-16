package fingerprint

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
)

func Fingerprint(in map[string]any) (map[string]any, error) {
	packetJSON, ok := in["packet_json"].(string)
	if !ok || !json.Valid([]byte(packetJSON)) {
		return nil, fmt.Errorf("handoff_fingerprint: compact packet JSON is required")
	}
	digest := sha256.Sum256([]byte(packetJSON))
	return map[string]any{"sha256": hex.EncodeToString(digest[:])}, nil
}
