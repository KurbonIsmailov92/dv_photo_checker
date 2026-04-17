package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"mime/multipart"
	"net/http"
	"os"
	"time"

	tgbotapi "github.com/go-telegram-bot-api/telegram-bot-api/v5"
)

var backendURL = getEnvOrDefault("BACKEND_URL", "http://localhost:8081")

func main() {
	token := os.Getenv("BOT_TOKEN")
	if token == "" {
		log.Fatal("BOT_TOKEN is required")
	}

	bot, err := tgbotapi.NewBotAPI(token)
	if err != nil {
		log.Fatal(err)
	}

	bot.Debug = true // 🔥 важно для диагностики

	log.Printf("Bot authorized as @%s", bot.Self.UserName)

	u := tgbotapi.NewUpdate(0)
	u.Timeout = 60

	updates := bot.GetUpdatesChan(u)

	for update := range updates {

		if update.Message == nil {
			continue
		}

		log.Println("📩 update received")

		chatID := update.Message.Chat.ID

		// =====================
		// COMMANDS
		// =====================
		if update.Message.IsCommand() {
			switch update.Message.Command() {

			case "start":
				send(bot, chatID,
					"👋 Привет!\n\n📸 Отправь фото — я проверю его по правилам DV Lottery")

			case "help":
				send(bot, chatID,
					"📸 Просто отправь фото.\n\nЯ проверю:\n- размер\n- лицо\n- фон\n- освещение")

			default:
				send(bot, chatID, "❓ Неизвестная команда")
			}

			continue
		}

		// =====================
		// PHOTO HANDLING
		// =====================
		if len(update.Message.Photo) > 0 {
			go handlePhoto(bot, update.Message)
			continue
		}

		// fallback
		send(bot, chatID, "📸 Отправь фото для проверки")
	}
}

// =====================
// PHOTO HANDLER
// =====================
func handlePhoto(bot *tgbotapi.BotAPI, msg *tgbotapi.Message) {

	chatID := msg.Chat.ID

	photo := msg.Photo[len(msg.Photo)-1]

	file, err := bot.GetFile(tgbotapi.FileConfig{
		FileID: photo.FileID,
	})
	if err != nil {
		send(bot, chatID, "❌ Не удалось получить файл")
		return
	}

	fileURL := file.Link(bot.Token)

	resp, err := http.Get(fileURL)
	if err != nil {
		send(bot, chatID, "❌ Ошибка скачивания фото")
		return
	}
	defer resp.Body.Close()

	fileBytes, err := io.ReadAll(resp.Body)
	if err != nil {
		send(bot, chatID, "❌ Ошибка чтения файла")
		return
	}

	result, err := sendToAPI(fileBytes)
	if err != nil {
		send(bot, chatID, "❌ API ошибка: "+err.Error())
		return
	}

	sendResult(bot, chatID, result)
}

// =====================
// SEND TO BACKEND
// =====================
func sendToAPI(fileBytes []byte) (map[string]interface{}, error) {

	body := &bytes.Buffer{}
	writer := multipart.NewWriter(body)

	part, err := writer.CreateFormFile("image", "photo.jpg")
	if err != nil {
		return nil, err
	}

	_, err = part.Write(fileBytes)
	if err != nil {
		return nil, err
	}

	writer.Close()

	req, err := http.NewRequest("POST", backendURL+"/validate", body)
	if err != nil {
		return nil, err
	}

	req.Header.Set("Content-Type", writer.FormDataContentType())

	client := &http.Client{Timeout: 15 * time.Second}

	resp, err := client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	respBytes, _ := io.ReadAll(resp.Body)

	if resp.StatusCode != 200 {
		return nil, fmt.Errorf("backend error [%d]: %s", resp.StatusCode, string(respBytes))
	}

	var result map[string]interface{}
	json.Unmarshal(respBytes, &result)

	return result, nil
}

// =====================
// SEND RESULT
// =====================
func sendResult(bot *tgbotapi.BotAPI, chatID int64, result map[string]interface{}) {

	valid := result["valid"].(bool)
	score := result["score"]

	text := ""

	if valid {
		text += "✅ Фото ПОДХОДИТ\n\n"
	} else {
		text += "❌ Фото НЕ подходит\n\n"
	}

	text += fmt.Sprintf("📊 Score: %v\n", score)

	if issues, ok := result["issues"].([]interface{}); ok {
		if len(issues) > 0 {
			text += "\n🔍 Проблемы:\n"
			for _, i := range issues {
				text += "• " + i.(string) + "\n"
			}
		}
	}

	send(bot, chatID, text)
}

// =====================
// SAFE SEND
// =====================
func getEnvOrDefault(name, fallback string) string {
	value := os.Getenv(name)
	if value == "" {
		return fallback
	}
	return value
}

func send(bot *tgbotapi.BotAPI, chatID int64, text string) {
	msg := tgbotapi.NewMessage(chatID, text)
	bot.Send(msg)
}
