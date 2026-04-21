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

// Встроенный HTML для /ui
const uiHTML = `<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>DV Photo Checker</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <style>body{font-family:system-ui,sans-serif}</style>
</head>
<body class="bg-gray-100">
  <div class="max-w-4xl mx-auto p-6">
    <h1 class="text-4xl font-bold text-center mb-8">DV Photo Checker</h1>
    
    <div class="bg-white rounded-3xl shadow-2xl p-10">
      <div id="dropzone" class="border-2 border-dashed border-gray-400 rounded-2xl p-16 text-center cursor-pointer hover:border-blue-500">
        <input type="file" id="file" accept="image/*" class="hidden">
        <p class="text-2xl mb-2">📸</p>
        <p class="text-xl font-medium">Загрузите фото</p>
      </div>

      <div class="flex gap-4 justify-center mt-8">
        <button onclick="validate()" class="px-10 py-4 bg-blue-600 text-white rounded-2xl font-semibold">Проверить фото</button>
        <button onclick="autofix()" class="px-10 py-4 bg-emerald-600 text-white rounded-2xl font-semibold">Автофикс</button>
      </div>

      <div id="result" class="hidden mt-10"></div>
    </div>
  </div>

  <script>
    let base64 = "";
    document.getElementById('dropzone').addEventListener('click', () => document.getElementById('file').click());
    document.getElementById('file').addEventListener('change', e => {
      const file = e.target.files[0];
      const reader = new FileReader();
      reader.onload = ev => {
        base64 = ev.target.result;
        document.getElementById('dropzone').innerHTML = `<img src="${base64}" class="max-h-96 mx-auto rounded-2xl">`;
      };
      reader.readAsDataURL(file);
    });

    async function send(endpoint) {
      if (!base64) return alert("Сначала загрузите фото");
      const res = await fetch(endpoint, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({image: base64, mode: "balanced"})
      });
      const data = await res.json();
      document.getElementById('result').innerHTML = `<pre class="bg-gray-900 text-white p-6 rounded-2xl overflow-auto">${JSON.stringify(data, null, 2)}</pre>`;
      document.getElementById('result').classList.remove('hidden');
    }

    function validate() { send('/validate'); }
    function autofix() { send('/auto-fix'); }
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
	fmt.Printf("🌐 UI: /ui\n")
	fmt.Printf("🔗 CV Service: %s\n", cvServiceURL)

	r.Run(":" + port)
}

func validateHandler(c *gin.Context) {
	forward(c, "/validate")
}

func autoFixHandler(c *gin.Context) {
	forward(c, "/auto-fix")
}

func forward(c *gin.Context, endpoint string) {
	var req map[string]interface{}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(400, gin.H{"error": err.Error()})
		return
	}

	resp, err := http.Post(cvServiceURL+endpoint, "application/json", bytes.NewReader([]byte(c.Request.Body.(io.Reader).Read)))
	if err != nil {
		c.JSON(500, gin.H{"error": "CV service unavailable"})
		return
	}
	defer resp.Body.Close()

	var result interface{}
	json.NewDecoder(resp.Body).Decode(&result)
	c.JSON(resp.StatusCode, result)
}