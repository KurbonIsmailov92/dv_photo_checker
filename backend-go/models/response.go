package models

type FaceAngle struct {
	Yaw   float64 `json:"yaw"`
	Pitch float64 `json:"pitch"`
	Roll  float64 `json:"roll"`
}

type ValidationResponse struct {
	Valid           bool                   `json:"valid"`
	Score           int                    `json:"score"`
	PassProbability float64                `json:"pass_probability"`
	Issues          []string               `json:"issues"`
	Metrics         map[string]interface{} `json:"metrics"`
	Detail          map[string]interface{} `json:"detail,omitempty"`
}
