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

	tgbotapi "github.com/go-telegram-bot-api/telegram-bot-api/v5"
)

const backendURL = "https://dv-photo-checker.onrender.com"

func main() {
	token := os.Getenv("BOT_TOKEN")
	if token == "" {
		log.Fatal("BOT_TOKEN is required")
	}

	bot, err := tgbotapi.NewBotAPI(token)
	if err != nil {
		log.Fatal(err)
	}

	log.Printf("Bot authorized: %s", bot.Self.UserName)

	u := tgbotapi.NewUpdate(0)
	u.Timeout = 60

	updates := bot.GetUpdatesChan(u)

	for update := range updates {
		if update.Message == nil {
			continue
		}

		// 👉 если пришло фото
		if len(update.Message.Photo) > 0 {
			go handlePhoto(bot, update.Message)
			continue
		}

		// 👉 если текст
		msg := tgbotapi.NewMessage(update.Message.Chat.ID,
			"📸 Отправь мне фото для проверки DV Lottery")
		bot.Send(msg)
	}
}

func handlePhoto(bot *tgbotapi.BotAPI, message *tgbotapi.Message) {
	chatID := message.Chat.ID

	// Берём самое большое фото
	photo := message.Photo[len(message.Photo)-1]

	// 1. Получаем file path
	fileConfig := tgbotapi.FileConfig{FileID: photo.FileID}
	file, err := bot.GetFile(fileConfig)
	if err != nil {
		sendError(bot, chatID, "Не удалось получить файл")
		return
	}

	// 2. Скачиваем файл
	fileURL := file.Link(bot.Token)

	resp, err := http.Get(fileURL)
	if err != nil {
		sendError(bot, chatID, "Ошибка скачивания файла")
		return
	}
	defer resp.Body.Close()

	fileBytes, err := io.ReadAll(resp.Body)
	if err != nil {
		sendError(bot, chatID, "Ошибка чтения файла")
		return
	}

	// 3. Отправляем в backend
	result, err := sendToBackend(fileBytes)
	if err != nil {
		sendError(bot, chatID, err.Error())
		return
	}

	// 4. Ответ пользователю
	sendResult(bot, chatID, result)
}

func sendToBackend(fileBytes []byte) (map[string]interface{}, error) {
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

	client := &http.Client{}
	resp, err := client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("Ошибка API: %v", err)
	}
	defer resp.Body.Close()

	respBytes, _ := io.ReadAll(resp.Body)

	if resp.StatusCode != 200 {
		return nil, fmt.Errorf("Ошибка сервера: %s", string(respBytes))
	}

	var result map[string]interface{}
	json.Unmarshal(respBytes, &result)

	return result, nil
}

func sendResult(bot *tgbotapi.BotAPI, chatID int64, result map[string]interface{}) {
	valid := result["valid"].(bool)
	score := result["score"]

	text := ""

	if valid {
		text += "✅ Фото ПОДХОДИТ для DV Lottery\n\n"
	} else {
		text += "❌ Фото НЕ подходит\n\n"
	}

	text += fmt.Sprintf("📊 Score: %v\n", score)

	if issues, ok := result["issues"].([]interface{}); ok && len(issues) > 0 {
		text += "\n🔍 Проблемы:\n"
		for _, issue := range issues {
			text += "• " + issue.(string) + "\n"
		}
	}

	msg := tgbotapi.NewMessage(chatID, text)
	bot.Send(msg)
}

func sendError(bot *tgbotapi.BotAPI, chatID int64, errorMsg string) {
	msg := tgbotapi.NewMessage(chatID, "❌ Ошибка: "+errorMsg)
	bot.Send(msg)
}
