package main

import (
	"bytes"
	"fmt"
	"io"
	"mime/multipart"
	"net/http"
	"net/textproto"
	"os"
	"strings"
	"time"

	"github.com/gin-gonic/gin"
)

var cvServiceURL string
var proxyClient = &http.Client{Timeout: 120 * time.Second}

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
	r.GET("/favicon.ico", func(c *gin.Context) {
		c.Status(http.StatusNoContent)
	})

	r.POST("/validate", validateHandler)
	r.POST("/auto-fix", autoFixHandler)

	fmt.Printf("вњ… Backend running on :%s\n", port)
	fmt.Printf("рџ”— CV Service: %s\n", cvServiceURL)

	if err := r.Run(":" + port); err != nil {
		panic(err)
	}
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
	<h2>рџ“ё DV Photo Validator Pro</h2>

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
		drawOverlay({});
	};

	reader.readAsDataURL(file);
}

function drawOverlay(metrics) {
	const img = document.getElementById("previewImage");
	const overlay = document.getElementById("previewOverlay");
	if (!img || !overlay) return;
	metrics = metrics || {};
	overlay.innerHTML = "";
	overlay.setAttribute("viewBox", "0 0 600 600");
	const viewSize = 600;
	const rangeDash = "\u2013";
	const eyeLabel = "Eye Level (56%" + rangeDash + "69%)";
	const headLabel = "Head Size (50%" + rangeDash + "69%)";
	const eyeMinPct = 56;
	const eyeMaxPct = 69;
	const headMinPct = 50;
	const headMaxPct = 69;
	const centerX = viewSize / 2;
	const noseZoneHalfWidth = viewSize * 0.05;
	const eyeZoneTopY = viewSize * (1 - eyeMaxPct / 100);
	const eyeZoneBottomY = viewSize * (1 - eyeMinPct / 100);
	const headMinPx = viewSize * (headMinPct / 100);
	const headMaxPx = viewSize * (headMaxPct / 100);
	const faceTopY = typeof metrics.face_top_y === "number" ? metrics.face_top_y : null;
	const faceChinY = typeof metrics.face_chin_y === "number" ? metrics.face_chin_y : null;
	const eyeLevel = typeof metrics.eye_level === "number" ? metrics.eye_level : null;
	const faceRect = metrics.face_rect && typeof metrics.face_rect === "object" ? metrics.face_rect : null;
	const faceBoxX = faceRect && typeof faceRect.x === "number" ? faceRect.x : null;
	const faceBoxWidth = faceRect && typeof faceRect.w === "number" ? faceRect.w : null;
	const noseX = faceRect && typeof faceRect.x === "number" && typeof faceRect.w === "number"
		? faceRect.x + faceRect.w / 2
		: null;
	const zoneColor = (isValid) => isValid === false ? "#ef4444" : "#10b981";
	const zoneFill = (isValid) => isValid === false ? "#ef444433" : "#10b98133";
	const createText = (x, y, label, color, anchor) => {
		const text = document.createElementNS("http://www.w3.org/2000/svg", "text");
		text.setAttribute("x", x);
		text.setAttribute("y", y);
		text.setAttribute("fill", color);
		text.setAttribute("font-size", "18");
		text.setAttribute("font-family", "Arial, sans-serif");
		text.setAttribute("font-weight", "bold");
		text.setAttribute("text-anchor", anchor || "start");
		text.textContent = label;
		overlay.appendChild(text);
	};
	const createLine = (y, label, color) => {
		const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
		line.setAttribute("x1", 0);
		line.setAttribute("y1", y);
		line.setAttribute("x2", viewSize);
		line.setAttribute("y2", y);
		line.setAttribute("stroke", color);
		line.setAttribute("stroke-width", "3");
		line.setAttribute("stroke-dasharray", "10 8");
		overlay.appendChild(line);
		createText(14, Math.max(18, y - 8), label, color);
	};
	const createCorridor = (y1, y2, label, isValid) => {
		const stroke = zoneColor(isValid);
		const rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
		rect.setAttribute("x", 0);
		rect.setAttribute("y", Math.min(y1, y2));
		rect.setAttribute("width", viewSize);
		rect.setAttribute("height", Math.abs(y2 - y1));
		rect.setAttribute("fill", zoneFill(isValid));
		rect.setAttribute("pointer-events", "none");
		overlay.appendChild(rect);
		const line1 = document.createElementNS("http://www.w3.org/2000/svg", "line");
		line1.setAttribute("x1", 0);
		line1.setAttribute("y1", Math.min(y1, y2));
		line1.setAttribute("x2", viewSize);
		line1.setAttribute("y2", Math.min(y1, y2));
		line1.setAttribute("stroke", stroke);
		line1.setAttribute("stroke-width", "3");
		line1.setAttribute("stroke-dasharray", "10 8");
		overlay.appendChild(line1);
		const line2 = document.createElementNS("http://www.w3.org/2000/svg", "line");
		line2.setAttribute("x1", 0);
		line2.setAttribute("y1", Math.max(y1, y2));
		line2.setAttribute("x2", viewSize);
		line2.setAttribute("y2", Math.max(y1, y2));
		line2.setAttribute("stroke", stroke);
		line2.setAttribute("stroke-width", "3");
		line2.setAttribute("stroke-dasharray", "10 8");
		overlay.appendChild(line2);
		createText(14, Math.max(20, Math.min(y1, y2) - 10), label, stroke);
	};
	const createVerticalZone = (x1, x2, label, isValid) => {
		const stroke = zoneColor(isValid);
		const rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
		rect.setAttribute("x", Math.min(x1, x2));
		rect.setAttribute("y", 0);
		rect.setAttribute("width", Math.abs(x2 - x1));
		rect.setAttribute("height", viewSize);
		rect.setAttribute("fill", zoneFill(isValid));
		rect.setAttribute("pointer-events", "none");
		overlay.appendChild(rect);
		const line1 = document.createElementNS("http://www.w3.org/2000/svg", "line");
		line1.setAttribute("x1", Math.min(x1, x2));
		line1.setAttribute("y1", 0);
		line1.setAttribute("x2", Math.min(x1, x2));
		line1.setAttribute("y2", viewSize);
		line1.setAttribute("stroke", stroke);
		line1.setAttribute("stroke-width", "2");
		line1.setAttribute("stroke-dasharray", "10 8");
		overlay.appendChild(line1);
		const line2 = document.createElementNS("http://www.w3.org/2000/svg", "line");
		line2.setAttribute("x1", Math.max(x1, x2));
		line2.setAttribute("y1", 0);
		line2.setAttribute("x2", Math.max(x1, x2));
		line2.setAttribute("y2", viewSize);
		line2.setAttribute("stroke", stroke);
		line2.setAttribute("stroke-width", "2");
		line2.setAttribute("stroke-dasharray", "10 8");
		overlay.appendChild(line2);
		createText(centerX, 32, label, stroke, "middle");
	};
	const createVerticalLine = (x, label, color) => {
		const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
		line.setAttribute("x1", x);
		line.setAttribute("y1", 0);
		line.setAttribute("x2", x);
		line.setAttribute("y2", viewSize);
		line.setAttribute("stroke", color);
		line.setAttribute("stroke-width", "2");
		line.setAttribute("stroke-dasharray", "6 6");
		overlay.appendChild(line);
		createText(x + 8, 54, label, color);
	};
	const createHeadBox = (x, yTop, width, yBottom, isValid) => {
		if (x === null || width === null || yTop === null || yBottom === null) return;
		const stroke = zoneColor(isValid);
		const rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
		rect.setAttribute("x", x);
		rect.setAttribute("y", Math.min(yTop, yBottom));
		rect.setAttribute("width", width);
		rect.setAttribute("height", Math.abs(yBottom - yTop));
		rect.setAttribute("fill", isValid === false ? "#ef444420" : "#38bdf820");
		rect.setAttribute("stroke", stroke);
		rect.setAttribute("stroke-width", "2");
		rect.setAttribute("stroke-dasharray", "8 6");
		overlay.appendChild(rect);
		createText(x + width + 8, Math.max(20, Math.min(yTop, yBottom) + 22), "Detected Head", stroke);
	};
	const createHeadReference = () => {
		const x = 540;
		const width = 34;
		const outerY = (viewSize - headMaxPx) / 2;
		const innerY = (viewSize - headMinPx) / 2;
		const outer = document.createElementNS("http://www.w3.org/2000/svg", "rect");
		outer.setAttribute("x", x);
		outer.setAttribute("y", outerY);
		outer.setAttribute("width", width);
		outer.setAttribute("height", headMaxPx);
		outer.setAttribute("fill", "#10b98112");
		outer.setAttribute("stroke", "#10b981");
		outer.setAttribute("stroke-width", "2");
		outer.setAttribute("stroke-dasharray", "10 8");
		overlay.appendChild(outer);
		const inner = document.createElementNS("http://www.w3.org/2000/svg", "rect");
		inner.setAttribute("x", x + 6);
		inner.setAttribute("y", innerY);
		inner.setAttribute("width", width - 12);
		inner.setAttribute("height", headMinPx);
		inner.setAttribute("fill", "#10b98122");
		inner.setAttribute("stroke", "#10b981");
		inner.setAttribute("stroke-width", "2");
		inner.setAttribute("stroke-dasharray", "8 6");
		overlay.appendChild(inner);
		createText(viewSize - 12, Math.max(18, outerY - 10), headLabel, "#10b981", "end");
	};
	const eyeValid = eyeLevel === null ? null : eyeLevel >= eyeMinPct && eyeLevel <= eyeMaxPct;
	createCorridor(eyeZoneTopY, eyeZoneBottomY, eyeLabel, eyeValid);
	if (eyeLevel !== null) {
		const eyeY = viewSize * (1 - eyeLevel / 100);
		createLine(eyeY, "Actual Eyes: " + eyeLevel.toFixed(1) + "%", zoneColor(eyeValid));
	}
	const noseValid = noseX === null ? null : Math.abs(noseX - centerX) <= noseZoneHalfWidth;
	createVerticalZone(centerX - noseZoneHalfWidth, centerX + noseZoneHalfWidth, "Nose should be centered", noseValid);
	createVerticalLine(centerX, "Center", "#ffffff");
	if (noseX !== null) {
		createVerticalLine(noseX, "Approx. Nose", zoneColor(noseValid));
	}
	if (faceTopY !== null && faceChinY !== null) {
		const headHeightPct = ((faceChinY - faceTopY) / viewSize) * 100;
		const headValid = headHeightPct >= headMinPct && headHeightPct <= headMaxPct;
		const allowedTopMin = Math.max(0, faceChinY - headMaxPx);
		const allowedTopMax = Math.min(viewSize, faceChinY - headMinPx);
		createCorridor(allowedTopMin, allowedTopMax, headLabel, headValid);
		createLine(faceTopY, "Top of Head", headValid ? "#38bdf8" : "#ef4444");
		createLine(faceChinY, "Chin", headValid ? "#f59e0b" : "#ef4444");
		createHeadBox(faceBoxX, faceTopY, faceBoxWidth, faceChinY, headValid);
		createText(viewSize - 14, Math.max(20, faceChinY - 10), "Actual: " + headHeightPct.toFixed(1) + "%", zoneColor(headValid), "end");
	} else if (faceChinY !== null) {
		createCorridor(
			Math.max(0, faceChinY - headMaxPx),
			Math.min(viewSize, faceChinY - headMinPx),
			headLabel,
			null
		);
		createLine(faceChinY, "Chin", "#f59e0b");
	} else if (faceTopY !== null) {
		createCorridor(
			Math.max(0, faceTopY + headMinPx),
			Math.min(viewSize, faceTopY + headMaxPx),
			headLabel,
			null
		);
		createLine(faceTopY, "Top of Head", "#38bdf8");
	} else {
		createHeadReference();
	}
}

async function upload() {
	let file = document.getElementById("file").files[0];
	if (!file) return alert("Р’С‹Р±РµСЂРё С„РѕС‚Рѕ");

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
	if (!lastFile) return alert("РЎРЅР°С‡Р°Р»Р° Р·Р°РіСЂСѓР·Рё С„РѕС‚Рѕ");

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
	drawOverlay({});

	document.getElementById("result").innerHTML =
		"рџ›  Р¤РѕС‚Рѕ Р°РІС‚РѕРјР°С‚РёС‡РµСЃРєРё РёСЃРїСЂР°РІР»РµРЅРѕ";
	document.getElementById("result").className = "result pass";
}

function renderResult(data) {
	let box = document.getElementById("result");
	let ok = data.valid;
	let score = Number(data && data.score);
	if (!Number.isFinite(score)) score = 0;
	let status = data && data.status ? data.status : (ok ? "PASS" : "FAIL");
	box.className = "result " + (ok ? "pass" : "fail");

	let text = ok ? "PASS: " + status + "\n\n" : "FAIL: " + status + "\n\n";
	text += "Score: " + score.toFixed(1) + "\n\n";

	if (data.issues && data.issues.length) {
		text += "Issues:\n";
		data.issues.forEach(i => text += "- " + i + "\n");
	}

	if (data.warnings && data.warnings.length) {
		text += "\nWarnings:\n";
		data.warnings.forEach(i => text += "- " + i + "\n");
	}

	text += "\nрџ’Ў How to fix:\n";
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

func buildJSONUpstreamRequest(c *gin.Context, endpoint string) (*http.Request, int, error) {
	body, err := io.ReadAll(c.Request.Body)
	if err != nil {
		return nil, http.StatusBadRequest, err
	}
	if len(bytes.TrimSpace(body)) == 0 {
		return nil, http.StatusBadRequest, fmt.Errorf("request body is required")
	}

	req, err := http.NewRequestWithContext(c.Request.Context(), http.MethodPost, cvServiceURL+endpoint, bytes.NewReader(body))
	if err != nil {
		return nil, http.StatusInternalServerError, err
	}

	req.Header.Set("Content-Type", "application/json")
	return req, http.StatusOK, nil
}

func buildMultipartUpstreamRequest(c *gin.Context, endpoint string) (*http.Request, int, error) {
	file, header, err := c.Request.FormFile("image")
	if err != nil {
		return nil, http.StatusBadRequest, fmt.Errorf("image file is required")
	}
	defer file.Close()

	var buf bytes.Buffer
	writer := multipart.NewWriter(&buf)

	partHeader := make(textproto.MIMEHeader)
	partHeader.Set("Content-Disposition", fmt.Sprintf(`form-data; name="image"; filename="%s"`, header.Filename))
	contentType := header.Header.Get("Content-Type")
	if contentType == "" {
		contentType = "application/octet-stream"
	}
	partHeader.Set("Content-Type", contentType)

	part, err := writer.CreatePart(partHeader)
	if err != nil {
		return nil, http.StatusInternalServerError, err
	}

	_, err = io.Copy(part, file)
	if err != nil {
		return nil, http.StatusInternalServerError, err
	}

	mode := c.PostForm("mode")
	if mode != "" {
		if err := writer.WriteField("mode", mode); err != nil {
			return nil, http.StatusInternalServerError, err
		}
	}

	if err := writer.Close(); err != nil {
		return nil, http.StatusInternalServerError, err
	}

	req, err := http.NewRequestWithContext(c.Request.Context(), http.MethodPost, cvServiceURL+endpoint, &buf)
	if err != nil {
		return nil, http.StatusInternalServerError, err
	}

	req.Header.Set("Content-Type", writer.FormDataContentType())
	return req, http.StatusOK, nil
}

func buildUpstreamRequest(c *gin.Context, endpoint string) (*http.Request, int, error) {
	contentType := c.GetHeader("Content-Type")
	if strings.HasPrefix(contentType, "application/json") {
		return buildJSONUpstreamRequest(c, endpoint)
	}

	return buildMultipartUpstreamRequest(c, endpoint)
}

func writeUpstreamResponse(c *gin.Context, resp *http.Response) {
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		c.JSON(http.StatusBadGateway, gin.H{
			"valid":  false,
			"score":  0,
			"status": "ERROR",
			"issues": []string{"Failed to read CV service response: " + err.Error()},
		})
		return
	}

	contentType := resp.Header.Get("Content-Type")
	if contentType == "" {
		contentType = "application/octet-stream"
	}

	c.Data(resp.StatusCode, contentType, body)
}

func forward(c *gin.Context, endpoint string) {
	req, statusCode, err := buildUpstreamRequest(c, endpoint)
	if err != nil {
		c.JSON(statusCode, gin.H{
			"valid":  false,
			"score":  0,
			"status": "ERROR",
			"issues": []string{err.Error()},
		})
		return
	}

	resp, err := proxyClient.Do(req)
	if err != nil {
		c.JSON(http.StatusBadGateway, gin.H{
			"valid":  false,
			"score":  0,
			"status": "ERROR",
			"issues": []string{"CV service unavailable: " + err.Error()},
		})
		return
	}

	writeUpstreamResponse(c, resp)
}
