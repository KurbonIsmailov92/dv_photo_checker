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

	serviceURL := os.Getenv("CV_SERVICE_URL")
if serviceURL == "" {
    serviceURL = "http://localhost:8000"
}

	log.Println("🔥 USING CV URL:", serviceURL)

	port := flag.String("port", getEnvOrDefault("PORT", "8080"), "HTTP port for the REST service")
	flag.Parse()
	_ = autoFix

	if *filePath != "" {
		response, err := validateLocalFile(*filePath, serviceURL)
		if err != nil {
			log.Fatalf("validation failed: %v", err)
		}
		printJSON(response)
		return
	}

	router := gin.Default()

	router.GET("/health", healthHandler)

	router.POST("/validate", func(c *gin.Context) {
		uploadHandler(c, serviceURL, "/validate")
	})

	router.POST("/auto-fix", func(c *gin.Context) {
		autoFixHandler(c, serviceURL, "/auto-fix")
	})

	router.GET("/", func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{
			"service": "DV Photo Validator Pro Backend",
			"version": "2.1",
		})
	})

	router.GET("/ui", func(c *gin.Context) {
		c.Header("Content-Type", "text/html")

		var htmlPage = `
<!DOCTYPE html>
<html>
<head>
	<title>DV Photo Validator Pro</title>
	<meta charset="UTF-8">
	<style>
		body {
			font-family: Arial;
			background: #0b1220;
			color: white;
			display: flex;
			justify-content: center;
			align-items: center;
			height: 100vh;
		}

		.card {
			background: #111827;
			padding: 25px;
			border-radius: 16px;
			width: 450px;
			text-align: center;
			box-shadow: 0 0 30px rgba(0,0,0,0.5);
		}

		input {
			margin: 15px 0;
		}

		button {
			padding: 10px 14px;
			margin: 5px;
			border: none;
			border-radius: 8px;
			cursor: pointer;
			font-weight: bold;
		}

		.primary { background: #38bdf8; }
		.fix { background: #f59e0b; }

		.result {
			margin-top: 15px;
			padding: 10px;
			border-radius: 10px;
			text-align: left;
			white-space: pre-wrap;
		}

		.pass {
			background: #14532d;
			border: 1px solid #22c55e;
		}

		.fail {
			background: #3f1d1d;
			border: 1px solid #ef4444;
		}

		.image-frame {
			position: relative;
			width: 100%;
			margin-top: 10px;
		}

		.image-frame img {
			width: 100%;
			display: block;
			border-radius: 10px;
		}

		.overlay {
			position: absolute;
			top: 0;
			left: 0;
			width: 100%;
			height: 100%;
			pointer-events: none;
		}

		.small {
			font-size: 13px;
			opacity: 0.8;
		}
	</style>
</head>

<body>

<div class="card">
	<h2>📸 DV Photo Validator Pro</h2>

	<input type="file" id="file" accept="image/*"/>

	<br/>

	<button class="primary" onclick="upload()">Check Photo</button>
	<button class="fix" onclick="autoFix()">Auto-Fix</button>

	<div id="preview"></div>

	<div id="result" class="result"></div>
</div>

<script>

let lastFile = null;
let lastResponse = null;

function showPreview(file) {
	let reader = new FileReader();

	reader.onload = function(e) {
		document.getElementById("preview").innerHTML =
			'<div class="image-frame">' +
			'<img id="previewImage" src="' + e.target.result + '"/>' +
			'<svg id="previewOverlay" class="overlay"></svg>' +
			'</div>';
		lastResponse = null;
	};

	reader.readAsDataURL(file);
}

function drawOverlay(metrics) {
	const img = document.getElementById("previewImage");
	const overlay = document.getElementById("previewOverlay");
	if (!img || !overlay || !metrics) return;

	overlay.innerHTML = "";
	overlay.setAttribute("viewBox", "0 0 600 600");
	
	const createLine = (y, label, color) => {
		const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
		line.setAttribute("x1", 0);
		line.setAttribute("y1", y);
		line.setAttribute("x2", 600);
		line.setAttribute("y2", y);
		line.setAttribute("stroke", color);
		line.setAttribute("stroke-width", 4);
		line.setAttribute("stroke-dasharray", "10 8");
		overlay.appendChild(line);

		const text = document.createElementNS("http://www.w3.org/2000/svg", "text");
		text.setAttribute("x", 14);
		text.setAttribute("y", y - 8);
		text.setAttribute("fill", color);
		text.setAttribute("font-size", "22");
		text.setAttribute("font-family", "Arial, sans-serif");
		text.setAttribute("font-weight", "bold");
		text.textContent = label;
		overlay.appendChild(text);
	};

	const createCorridor = (y1, y2, label, value, isValid) => {
		const color = isValid ? "#10b98133" : "#ff6b6b33"; // semi-transparent green or red
		const rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
		rect.setAttribute("x", 0);
		rect.setAttribute("y", Math.min(y1, y2));
		rect.setAttribute("width", 600);
		rect.setAttribute("height", Math.abs(y2 - y1));
		rect.setAttribute("fill", color);
		rect.setAttribute("pointer-events", "none");
		overlay.appendChild(rect);

		// Top line
		const line1 = document.createElementNS("http://www.w3.org/2000/svg", "line");
		line1.setAttribute("x1", 0);
		line1.setAttribute("y1", Math.min(y1, y2));
		line1.setAttribute("x2", 600);
		line1.setAttribute("y2", Math.min(y1, y2));
		line1.setAttribute("stroke", isValid ? "#10b981" : "#ff6b6b");
		line1.setAttribute("stroke-width", 3);
		overlay.appendChild(line1);

		// Bottom line
		const line2 = document.createElementNS("http://www.w3.org/2000/svg", "line");
		line2.setAttribute("x1", 0);
		line2.setAttribute("y1", Math.max(y1, y2));
		line2.setAttribute("x2", 600);
		line2.setAttribute("y2", Math.max(y1, y2));
		line2.setAttribute("stroke", isValid ? "#10b981" : "#ff6b6b");
		line2.setAttribute("stroke-width", 3);
		overlay.appendChild(line2);

		// Label
		const text = document.createElementNS("http://www.w3.org/2000/svg", "text");
		text.setAttribute("x", 14);
		text.setAttribute("y", (Math.min(y1, y2) + Math.max(y1, y2)) / 2 - 8);
		text.setAttribute("fill", isValid ? "#10b981" : "#ff6b6b");
		text.setAttribute("font-size", "20");
		text.setAttribute("font-family", "Arial, sans-serif");
		text.setAttribute("font-weight", "bold");
		text.textContent = label + ": " + value.toFixed(1) + "%";
		overlay.appendChild(text);
	};

	// Show anatomical points
	if (metrics.face_top_y !== undefined) {
		createLine(metrics.face_top_y, "Макушка", "#38bdf8");
	}
	if (metrics.face_chin_y !== undefined) {
		createLine(metrics.face_chin_y, "Подбородок", "#f59e0b");
	}
	
	// Show eye level as a fixed corridor (range)
	const eyeMin = 600 * (1 - 70 / 100);  // 70% from bottom
	const eyeMax = 600 * (1 - 49 / 100);  // 49% from bottom
	const isEyeValid = metrics.eye_level >= 49 && metrics.eye_level <= 70;
	createCorridor(eyeMin, eyeMax, "Глаза", metrics.eye_level || 0, isEyeValid);
	
	// Vertical center line
	const centerLine = document.createElementNS("http://www.w3.org/2000/svg", "line");
	centerLine.setAttribute("x1", 300);
	centerLine.setAttribute("y1", 0);
	centerLine.setAttribute("x2", 300);
	centerLine.setAttribute("y2", 600);
	centerLine.setAttribute("stroke", "#ffffff");
	centerLine.setAttribute("stroke-width", 2);
	centerLine.setAttribute("stroke-dasharray", "5 5");
	overlay.appendChild(centerLine);
}

async function upload() {
	let file = document.getElementById("file").files[0];
	if (!file) return alert("Выбери фото");

	lastFile = file;
	showPreview(file);

	let form = new FormData();
	form.append("image", file);

	let res = await fetch("/validate", {
		method: "POST",
		body: form
	});

	let data = await res.json();
	lastResponse = data;
	renderResult(data);
	drawOverlay(data.metrics);
}

async function autoFix() {
	if (!lastFile) return alert("Сначала загрузи фото");

	let form = new FormData();
	form.append("image", lastFile);

	let res = await fetch("/auto-fix", {
		method: "POST",
		body: form
	});

	let blob = await res.blob();
	let url = URL.createObjectURL(blob);
	document.getElementById("preview").innerHTML =
		'<div class="image-frame">' +
		'<img id="previewImage" src="' + url + '"/>' +
		'<svg id="previewOverlay" class="overlay"></svg>' +
		'</div>';

	document.getElementById("result").innerHTML =
		"🛠 Фото автоматически исправлено";
	document.getElementById("result").className = "result pass";
}

function renderResult(data) {
	let box = document.getElementById("result");
	let ok = data.valid;
	box.className = "result " + (ok ? "pass" : "fail");

	let text = ok ? "✅ PASS\n\n" : "❌ FAIL\n\n";
	text += "Score: " + data.score + "\n\n";

	if (data.issues && data.issues.length) {
		text += "Issues:\n";
		data.issues.forEach(i => text += "- " + i + "\n");
	}

	if (data.warnings && data.warnings.length) {
		text += "\nWarnings:\n";
		data.warnings.forEach(i => text += "- " + i + "\n");
	}

	text += "\n💡 How to fix:\n";
	if (!ok) {
		text += "- Lower your head position\n";
		text += "- Use natural daylight\n";
		text += "- Avoid compression (no Telegram)\n";
		text += "- Increase sharpness\n";
	}

	box.innerText = text;
}

</script>

</body>
</html>
`
		c.String(200, htmlPage)
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
		// Return a fallback response when CV service is unavailable
		fallback := &models.ValidationResponse{
			Valid:          false,
			Score:          0.0,
			Issues:         []string{"CV service unavailable: " + err.Error()},
			Warnings:       []string{},
			DecisionReason: "Service Error",
			Metrics:        map[string]interface{}{},
			Features:       map[string]float64{},
		}
		c.JSON(http.StatusOK, fallback)
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
		// Return the original image when CV service is unavailable
		opened.Seek(0, 0) // Reset to beginning
		originalBytes, _ := io.ReadAll(opened)
		c.Data(http.StatusOK, "image/jpeg", originalBytes) // Assume JPEG, but could detect
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
