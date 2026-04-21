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

// ==================== ВСТРОЕННЫЙ UI ====================
const uiHTML = `<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>DV Photo Checker</title>
  <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-50">
  <div class="max-w-4xl mx-auto p-8">
    <h1 class="text-4xl font-bold text-center mb-8">DV Photo Checker</h1>
    
    <div class="bg-white rounded-3xl shadow-2xl p-10">
      <div id="dropzone" class="border-4 border-dashed border-gray-300 rounded-2xl p-16 text-center cursor-pointer hover:border-blue-500">
        <input type="file" id="fileInput" accept="image/*" class="hidden">
        <p class="text-5xl mb-4">📸</p>
        <p class="text-xl font-medium">Перетащите фото или нажмите для выбора</p>
      </div>

      <div class="flex justify-center gap-4 mt-8">
        <button onclick="validatePhoto()" class="px-10 py-4 bg-blue-600 text-white rounded-2xl font-semibold">Проверить фото</button>
        <button onclick="autoFixPhoto()" class="px-10 py-4 bg-emerald-600 text-white rounded-2xl font-semibold">Автофикс</button>
      </div>

      <div id="result" class="hidden mt-10 p-6 bg-gray-900 text-white rounded-2xl overflow-auto"></div>
    </div>
  </div>

  <script>
    let base64 = "";

    document.getElementById('dropzone').onclick = () => document.getElementById('fileInput').click();
    
    document.getElementById('fileInput').onchange = e => {
      const file = e.target.files[0];
      const reader = new FileReader();
      reader.onload = ev => {
        base64 = ev.target.result;
        document.getElementById('dropzone').innerHTML = 
          '<img src="' + base64 + '" class="max-h-96 mx-auto rounded-2xl shadow-md">';
      };
      reader.readAsDataURL(file);
    };

    async function send(endpoint) {
      if (!base64) return alert("Сначала загрузите фото!");
      
      const res = await fetch(endpoint, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({image: base64, mode: "balanced"})
      });
      
      const data = await res.json();
      document.getElementById('result').innerHTML = '<pre class="text-sm">' + JSON.stringify(data, null, 2) + '</pre>';
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
			"valid":  false,
			"score":  0,
			"status": "ERROR",
			"issues": []string{"CV service unavailable"},
		})
		return
	}
	defer resp.Body.Close()

	var result interface{}
	json.NewDecoder(resp.Body).Decode(&result)
	c.JSON(resp.StatusCode, result)
}
