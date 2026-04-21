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

var cvServiceURL string

// Встроенный красивый UI
const uiHTML = `<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>DV Photo Checker</title>
  <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-50">
  <div class="max-w-3xl mx-auto p-6">
    <h1 class="text-4xl font-bold text-center mb-8 text-gray-800">DV Photo Checker</h1>
    
    <div id="dropzone" class="border-2 border-dashed border-gray-400 rounded-3xl p-16 text-center cursor-pointer hover:border-blue-500 transition">
      <input type="file" id="fileInput" accept="image/*" class="hidden">
      <p class="text-6xl mb-4">📸</p>
      <p class="text-xl font-medium">Нажмите или перетащите фото</p>
    </div>

    <div class="flex gap-4 justify-center mt-8">
      <button onclick="validatePhoto()" class="px-8 py-4 bg-blue-600 hover:bg-blue-700 text-white font-semibold rounded-2xl">Проверить</button>
      <button onclick="autoFixPhoto()" class="px-8 py-4 bg-emerald-600 hover:bg-emerald-700 text-white font-semibold rounded-2xl">Автофикс</button>
    </div>

    <div id="result" class="hidden mt-10 p-6 bg-white rounded-3xl shadow"></div>
  </div>

  <script>
    let base64 = "";
    document.getElementById('dropzone').onclick = () => document.getElementById('fileInput').click();
    document.getElementById('fileInput').onchange = e => {
      const file = e.target.files[0];
      const reader = new FileReader();
      reader.onload = ev => {
        base64 = ev.target.result;
        document.getElementById('dropzone').innerHTML = `<img src="${base64}" class="max-h-96 mx-auto rounded-2xl">`;
      };
      reader.readAsDataURL(file);
    };

    async function send(endpoint) {
      if (!base64) return alert("Загрузите фото сначала");
      const res = await fetch(endpoint, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({image: base64, mode: "balanced"})
      });
      const data = await res.json();
      document.getElementById('result').innerHTML = `<pre class="bg-gray-900 text-green-400 p-6 rounded-2xl overflow-auto text-sm">${JSON.stringify(data, null, 2)}</pre>`;
      document.getElementById('result').classList.remove('hidden');
    }

    function validatePhoto() { send('/validate'); }
    function autoFixPhoto() { send('/auto-fix'); }
  </script>
</body>
</html>`

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
	fmt.Printf("🌐 UI: http://localhost:%s/ui\n", port)

	r.Run(":" + port)
}

func validateHandler(c *gin.Context) {
	forwardRequest(c, "/validate")
}

func autoFixHandler(c *gin.Context) {
	forwardRequest(c, "/auto-fix")
}

func forwardRequest(c *gin.Context, endpoint string) {
	var payload map[string]interface{}
	if err := c.ShouldBindJSON(&payload); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	resp, err := http.Post(cvServiceURL+endpoint, "application/json", bytes.NewReader(func() []byte {
		b, _ := json.Marshal(payload)
		return b
	}()))
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "CV service unavailable"})
		return
	}
	defer resp.Body.Close()

	var result interface{}
	json.NewDecoder(resp.Body).Decode(&result)
	c.JSON(resp.StatusCode, result)
}