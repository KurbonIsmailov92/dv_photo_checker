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
    "os"
    "path/filepath"
    "time"

    "backend-go/models"
    "github.com/gin-gonic/gin"
)

const defaultCVServiceURL = "http://localhost:8000/validate"

func main() {
    filePath := flag.String("validate", "", "Validate an image file path via the CV microservice")
    autoFix := flag.Bool("auto-fix", false, "Auto-fix the image if validation fails")
    serviceURL := flag.String("cv-service", defaultCVServiceURL, "CV microservice URL")
    port := flag.String("port", "8080", "HTTP port for the REST service")
    flag.Parse()

    if *filePath != "" {
        response, err := validateLocalFile(*filePath, *serviceURL, *autoFix)
        if err != nil {
            log.Fatalf("validation failed: %v", err)
        }
        printJSON(response)
        return
    }

    router := gin.Default()
    router.GET("/health", healthHandler)
    router.POST("/validate", func(c *gin.Context) {
        uploadHandler(c, *serviceURL)
    })
    router.GET("/", func(c *gin.Context) {
        c.JSON(http.StatusOK, gin.H{"service": "DV Photo Validator Pro Backend", "version": "2.0"})
    })

    log.Printf("Backend running on http://localhost:%s", *port)
    log.Fatal(router.Run(fmt.Sprintf(":%s", *port)))
}

func healthHandler(c *gin.Context) {
    c.JSON(http.StatusOK, gin.H{"status": "ok"})
}

func uploadHandler(c *gin.Context, serviceURL string) {
    file, err := c.FormFile("image")
    if err != nil {
        c.JSON(http.StatusBadRequest, gin.H{"error": "missing image file field 'image'"})
        return
    }

    autoFix := c.DefaultPostForm("auto_fix", "false") == "true"

    opened, err := file.Open()
    if err != nil {
        c.JSON(http.StatusInternalServerError, gin.H{"error": "cannot open uploaded file"})
        return
    }
    defer opened.Close()

    body := &bytes.Buffer{}
    writer := multipart.NewWriter(body)
    writer.WriteField("auto_fix", fmt.Sprintf("%t", autoFix))
    part, err := writer.CreateFormFile("image", filepath.Base(file.Filename))
    if err != nil {
        c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to create multipart body"})
        return
    }
    if _, err := io.Copy(part, opened); err != nil {
        c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to copy file"})
        return
    }
    writer.Close()

    response, err := sendToCVService(serviceURL, writer.FormDataContentType(), body)
    if err != nil {
        c.JSON(http.StatusBadGateway, gin.H{"error": err.Error()})
        return
    }
    c.JSON(http.StatusOK, response)
}

func validateLocalFile(filePath, serviceURL string, autoFix bool) (*models.ValidationResponse, error) {
    file, err := os.Open(filePath)
    if err != nil {
        return nil, err
    }
    defer file.Close()

    body := &bytes.Buffer{}
    writer := multipart.NewWriter(body)
    writer.WriteField("auto_fix", fmt.Sprintf("%t", autoFix))
    part, err := writer.CreateFormFile("image", filepath.Base(filePath))
    if err != nil {
        return nil, err
    }
    if _, err := io.Copy(part, file); err != nil {
        return nil, err
    }
    writer.Close()

    return sendToCVService(serviceURL, writer.FormDataContentType(), body)
}

func sendToCVService(serviceURL string, contentType string, body *bytes.Buffer) (*models.ValidationResponse, error) {
    client := http.Client{Timeout: 30 * time.Second}
    resp, err := client.Post(serviceURL, contentType, body)
    if err != nil {
        return nil, fmt.Errorf("CV microservice request failed: %w", err)
    }
    defer resp.Body.Close()

    payload, err := io.ReadAll(resp.Body)
    if err != nil {
        return nil, err
    }

    if resp.StatusCode != http.StatusOK {
        return nil, fmt.Errorf("CV microservice returned %d: %s", resp.StatusCode, string(payload))
    }

    var result models.ValidationResponse
    if err := json.Unmarshal(payload, &result); err != nil {
        return nil, err
    }
    return &result, nil
}

func printJSON(response *models.ValidationResponse) {
    output, err := json.MarshalIndent(response, "", "  ")
    if err != nil {
        log.Fatalf("failed to format JSON: %v", err)
    }
    fmt.Println(string(output))
}
