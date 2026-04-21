package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"strings"
	"time"

	"github.com/gin-gonic/gin"
)

type ValidateRequest struct {
	Image string `json:"image"`
	Mode  string `json:"mode,omitempty"`
}

type CVResponse struct {
	Valid          bool     `json:"valid"`
	Score          float64  `json:"score"`
	Status         string   `json:"status"`
	Issues         []string `json:"issues"`
	Warnings       []string `json:"warnings"`
	DecisionReason string   `json:"decision_reason"`
	Metrics        any      `json:"metrics,omitempty"`
	Detail         any      `json:"detail,omitempty"`
}

var cvServiceURL string

func main() {
	// ==================== CONFIG ====================
	cvServiceURL = os.Getenv("CV_SERVICE_URL")
	if cvServiceURL == "" {
		cvServiceURL = "http://localhost:8000"
	}

	// Убираем возможный IPv6 localhost
	if strings.HasPrefix(cvServiceURL, "http://localhost") {
		cvServiceURL = strings.Replace(cvServiceURL, "localhost", "127.0.0.1", 1)
	}

	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}

	// ==================== GIN SETUP ====================
	gin.SetMode(gin.ReleaseMode) // для продакшена
	r := gin.Default()

	// Middleware
	r.Use(gin.Recovery())

	// Health check
	r.GET("/health", func(c *gin.Context) {
		c.JSON(200, gin.H{"status": "ok", "service": "dv-photo-checker"})
	})

	// UI страница
	r.GET("/ui", func(c *gin.Context) {
		c.File("./static/index.html") // если есть папка static
	})

	// Главный endpoint
	r.POST("/validate", validateHandler)
	r.POST("/auto-fix", autoFixHandler)
	r.GET("/", func(c *gin.Context) {
		c.JSON(200, gin.H{"message": "DV Photo Checker API is running"})
	})

	fmt.Printf("Backend running on :%s\n", port)
	fmt.Printf("CV Service URL: %s\n", cvServiceURL)

	r.Run(":" + port)
}

// ==================== HANDLERS ====================

func validateHandler(c *gin.Context) {
	var req ValidateRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid request"})
		return
	}

	if req.Image == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Image is required"})
		return
	}

	// Пересылаем запрос в Python CV Service
	resp, err := forwardToCVService("/validate", req)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{
			"valid":  false,
			"score":  0,
			"status": "ERROR",
			"issues": []string{"CV service unavailable: " + err.Error()},
		})
		return
	}

	c.JSON(http.StatusOK, resp)
}

func autoFixHandler(c *gin.Context) {
	var req ValidateRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid request"})
		return
	}

	resp, err := forwardToCVService("/auto-fix", req)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, resp)
}

// ==================== HELPER ====================

func forwardToCVService(endpoint string, payload interface{}) (interface{}, error) {
	jsonData, _ := json.Marshal(payload)

	client := &http.Client{Timeout: 25 * time.Second}

	resp, err := client.Post(cvServiceURL+endpoint, "application/json", bytes.NewBuffer(jsonData))
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	body, _ := io.ReadAll(resp.Body)

	var result interface{}
	json.Unmarshal(body, &result)

	return result, nil
}