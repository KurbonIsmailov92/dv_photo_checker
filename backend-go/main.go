package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"strings"


	"github.com/gin-gonic/gin"
)

var cvServiceURL string

func main() {
	cvServiceURL = os.Getenv("CV_SERVICE_URL")
	if cvServiceURL == "" {
		cvServiceURL = "http://localhost:8000"
	}
	if strings.HasPrefix(cvServiceURL, "http://localhost") {
		cvServiceURL = strings.Replace(cvServiceURL, "localhost", "127.0.0.1", 1)
	}

	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}

	r := gin.Default()

	r.GET("/ui", func(c *gin.Context) {
		c.Data(http.StatusOK, "text/html; charset=utf-8", []byte(uiHTML))
	})

	r.GET("/", func(c *gin.Context) {
		c.Redirect(http.StatusMovedPermanently, "/ui")
	})

	r.GET("/health", func(c *gin.Context) {
		c.JSON(200, gin.H{"status": "ok"})
	})

	r.POST("/validate", validateHandler)
	r.POST("/auto-fix", autoFixHandler)

	fmt.Printf("✅ Backend running on :%s\n", port)
	fmt.Printf("🔗 CV Service: %s\n", cvServiceURL)

	r.Run(":" + port)
}

const uiHTML = `<!DOCTYPE html>
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
</html>`

func validateHandler(c *gin.Context) {
	forward(c, "/validate")
}

func autoFixHandler(c *gin.Context) {
	forward(c, "/auto-fix")
}

func forward(c *gin.Context, endpoint string) {
	var req map[string]interface{}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	jsonData, _ := json.Marshal(req)
	resp, err := http.Post(cvServiceURL+endpoint, "application/json", bytes.NewReader(jsonData))
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{
			"valid": false,
			"score": 0,
			"status": "ERROR",
			"issues": []string{"CV service unavailable: " + err.Error()},
		})
		return
	}
	defer resp.Body.Close()

	var result interface{}
	json.NewDecoder(resp.Body).Decode(&result)
	c.JSON(resp.StatusCode, result)
}