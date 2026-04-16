package main

import (
	"bytes"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"log"
	"mime/multipart"
	"net/http"
	"net/textproto"
	"os"
	"path/filepath"
	"strings"
	"time"

	"backend-go/models"

	"github.com/gin-gonic/gin"
)

const (
	defaultCVServiceURL = "http://localhost:8000"
	requestTimeout      = 10 * time.Second
)

func main() {
	filePath := flag.String("validate", "", "Validate an image file path via the CV microservice")
	autoFix := flag.Bool("auto-fix", false, "Auto-fix the image if validation fails")
	serviceURL := flag.String("cv-service", getEnvOrDefault("CV_SERVICE_URL", defaultCVServiceURL), "CV microservice base URL")
	port := flag.String("port", getEnvOrDefault("PORT", "8080"), "HTTP port for the REST service")
	flag.Parse()

	if *filePath != "" {
		response, err := validateLocalFile(*filePath, *serviceURL)
		if err != nil {
			log.Fatalf("validation failed: %v", err)
		}
		printJSON(response)
		return
	}

	router := gin.Default()

	router.GET("/health", healthHandler)

	router.POST("/validate", func(c *gin.Context) {
		uploadHandler(c, *serviceURL, "/validate")
	})

	router.POST("/auto-fix", func(c *gin.Context) {
		autoFixHandler(c, *serviceURL, "/auto-fix")
	})

	router.GET("/", func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{
			"service": "DV Photo Validator Pro Backend",
			"version": "2.1",
		})
	})

	log.Printf("Backend running on :%s", *port)
	log.Fatal(router.Run(":" + *port))
}

func getEnvOrDefault(name, fallback string) string {
	value := strings.TrimSpace(os.Getenv(name))
	if value == "" {
		return fallback
	}
	return value
}

func healthHandler(c *gin.Context) {
	c.JSON(http.StatusOK, gin.H{"status": "ok"})
}

func uploadHandler(c *gin.Context, serviceBaseURL string, path string) {
	file, err := c.FormFile("image")
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "missing image file field 'image'"})
		return
	}

	opened, err := file.Open()
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "cannot open uploaded file"})
		return
	}
	defer opened.Close()

	body, contentType, err := buildMultipartBody(file, opened)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	endpointURL := joinEndpoint(serviceBaseURL, path)

	response, err := sendToCVService(endpointURL, contentType, body)
	if err != nil {
		c.JSON(http.StatusBadGateway, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, response)
}

func autoFixHandler(c *gin.Context, serviceBaseURL string, path string) {
	file, err := c.FormFile("image")
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "missing image file field 'image'"})
		return
	}

	opened, err := file.Open()
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "cannot open uploaded file"})
		return
	}
	defer opened.Close()

	body, contentType, err := buildMultipartBody(file, opened)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	endpointURL := joinEndpoint(serviceBaseURL, path)

	fixedBytes, respContentType, err := sendToCVServiceRaw(endpointURL, contentType, body)
	if err != nil {
		c.JSON(http.StatusBadGateway, gin.H{"error": err.Error()})
		return
	}

	c.Data(http.StatusOK, respContentType, fixedBytes)
}

func validateLocalFile(filePath, serviceBaseURL string) (*models.ValidationResponse, error) {
	file, err := os.Open(filePath)
	if err != nil {
		return nil, err
	}
	defer file.Close()

	body := &bytes.Buffer{}
	writer := multipart.NewWriter(body)

	h := make(textproto.MIMEHeader)
	h.Set("Content-Disposition", fmt.Sprintf(`form-data; name="image"; filename="%s"`, filepath.Base(filePath)))
	h.Set("Content-Type", "image/jpeg")

	part, err := writer.CreatePart(h)
	if err != nil {
		return nil, err
	}

	if _, err := io.Copy(part, file); err != nil {
		return nil, err
	}

	writer.Close()

	endpointURL := joinEndpoint(serviceBaseURL, "/validate")
	return sendToCVService(endpointURL, writer.FormDataContentType(), body)
}

func buildMultipartBody(file *multipart.FileHeader, opened multipart.File) (*bytes.Buffer, string, error) {
	body := &bytes.Buffer{}
	writer := multipart.NewWriter(body)

	h := make(textproto.MIMEHeader)
	h.Set("Content-Disposition", fmt.Sprintf(`form-data; name="image"; filename="%s"`, filepath.Base(file.Filename)))

	contentType := file.Header.Get("Content-Type")
	if contentType == "" {
		contentType = "image/jpeg"
	}
	h.Set("Content-Type", contentType)

	part, err := writer.CreatePart(h)
	if err != nil {
		return nil, "", err
	}

	if _, err := io.Copy(part, opened); err != nil {
		return nil, "", err
	}

	writer.Close()
	return body, writer.FormDataContentType(), nil
}

func sendToCVService(serviceURL string, contentType string, body *bytes.Buffer) (*models.ValidationResponse, error) {
	client := http.Client{Timeout: requestTimeout}

	req, err := http.NewRequest("POST", serviceURL, body)
	if err != nil {
		return nil, err
	}
	req.Header.Set("Content-Type", contentType)

	resp, err := client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("CV microservice request failed: %w", err)
	}
	defer resp.Body.Close()

	payload, _ := io.ReadAll(resp.Body)

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("CV microservice returned %d: %s", resp.StatusCode, string(payload))
	}

	var result models.ValidationResponse
	if err := json.Unmarshal(payload, &result); err != nil {
		return nil, err
	}

	return &result, nil
}

func sendToCVServiceRaw(serviceURL string, contentType string, body *bytes.Buffer) ([]byte, string, error) {
	client := http.Client{Timeout: requestTimeout}

	req, err := http.NewRequest("POST", serviceURL, body)
	if err != nil {
		return nil, "", err
	}
	req.Header.Set("Content-Type", contentType)

	resp, err := client.Do(req)
	if err != nil {
		return nil, "", fmt.Errorf("CV microservice request failed: %w", err)
	}
	defer resp.Body.Close()

	payload, _ := io.ReadAll(resp.Body)

	if resp.StatusCode != http.StatusOK {
		return nil, "", fmt.Errorf("CV microservice returned %d: %s", resp.StatusCode, string(payload))
	}

	respType := resp.Header.Get("Content-Type")
	if respType == "" {
		respType = "application/octet-stream"
	}

	return payload, respType, nil
}

func joinEndpoint(baseURL, path string) string {
	return strings.TrimRight(baseURL, "/") + "/" + strings.TrimLeft(path, "/")
}

func printJSON(response *models.ValidationResponse) {
	output, _ := json.MarshalIndent(response, "", "  ")
	fmt.Println(string(output))
}
