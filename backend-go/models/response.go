package models

type FaceAngle struct {
	Yaw   float64 `json:"yaw"`
	Pitch float64 `json:"pitch"`
	Roll  float64 `json:"roll"`
}

type ValidationResponse struct {
	Valid           bool                   `json:"valid"`
	Score           float64                `json:"score"`
	PassProbability float64                `json:"pass_probability"`
	Features        map[string]float64     `json:"features"`
	Issues          []string               `json:"issues"`
	Warnings        []string               `json:"warnings"`
	DecisionReason  string                 `json:"decision_reason"`
	Metrics         map[string]interface{} `json:"metrics"`
	Detail          map[string]interface{} `json:"detail,omitempty"`
}
