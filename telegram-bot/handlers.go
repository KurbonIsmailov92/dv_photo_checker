package main

import (
	"encoding/json"
	"fmt"
	"log"
	"strings"

	tgbotapi "github.com/go-telegram-bot-api/telegram-bot-api/v5"
)

func handleUpdate(bot *tgbotapi.BotAPI, service *PhotoService, update tgbotapi.Update) {
	if update.CallbackQuery != nil {
		handleCallbackQuery(bot, service, update.CallbackQuery)
		return
	}

	message := update.Message
	if message == nil {
		return
	}

	userID := message.From.ID
	log.Printf("telegram update from user_id=%d message=%q", userID, message.Text)

	if message.IsCommand() {
		handleCommand(bot, message)
		return
	}

	if len(message.Photo) > 0 {
		handlePhotoMessage(bot, service, message)
		return
	}

	sendTextPrompt(bot, message.Chat.ID)
}

func handleCommand(bot *tgbotapi.BotAPI, message *tgbotapi.Message) {
	switch message.Command() {
	case "start":
		text := "Welcome to DV Photo Validator Bot 🇺🇸\n\nSend a photo to check DV Lottery requirements."
		msg := tgbotapi.NewMessage(message.Chat.ID, text)
		bot.Send(msg)
	default:
		sendTextPrompt(bot, message.Chat.ID)
	}
}

func sendTextPrompt(bot *tgbotapi.BotAPI, chatID int64) {
	text := "📸 Send me a photo to check DV Lottery requirements"
	msg := tgbotapi.NewMessage(chatID, text)
	bot.Send(msg)
}

func handlePhotoMessage(bot *tgbotapi.BotAPI, service *PhotoService, message *tgbotapi.Message) {
	userID := message.From.ID
	chatID := message.Chat.ID

	if !service.CanUseFreeCheck(userID) {
		msg := tgbotapi.NewMessage(chatID, "⚠️ Free limit reached")
		bot.Send(msg)
		return
	}

	photo := message.Photo[len(message.Photo)-1]
	tempFile, err := service.DownloadTelegramPhoto(bot, photo.FileID, userID)
	if err != nil {
		log.Printf("failed to download image for user %d: %v", userID, err)
		msg := tgbotapi.NewMessage(chatID, "❌ Failed to download image")
		bot.Send(msg)
		return
	}

	validation, err := service.ValidatePhoto(tempFile)
	if err != nil {
		log.Printf("validation error for user %d: %v", userID, err)
		msg := tgbotapi.NewMessage(chatID, "⚠️ Error processing photo. Try again later.")
		bot.Send(msg)
		return
	}

	service.SaveUserPhoto(userID, tempFile)
	service.SaveValidation(userID, validation)
	service.IncrementChecks(userID)

	if validation.Valid {
		msgText := fmt.Sprintf("✅ Photo PASSED\n\nScore: %d\nProbability: %.2f\n\n🎉 Your photo meets DV Lottery requirements!", validation.Score, validation.PassProbability)
		msg := tgbotapi.NewMessage(chatID, msgText)
		bot.Send(msg)
		return
	}

	failureMessage := formatFailureMessage(validation)
	keyboard := tgbotapi.NewInlineKeyboardMarkup(
		tgbotapi.NewInlineKeyboardRow(
			tgbotapi.NewInlineKeyboardButtonData("Fix Photo", "fix"),
			tgbotapi.NewInlineKeyboardButtonData("Why Failed", "why"),
		),
	)
	msg := tgbotapi.NewMessage(chatID, failureMessage)
	msg.ReplyMarkup = keyboard
	bot.Send(msg)
}

func handleCallbackQuery(bot *tgbotapi.BotAPI, service *PhotoService, query *tgbotapi.CallbackQuery) {
	userID := query.From.ID
	chatID := query.Message.Chat.ID
	data := query.Data

	callback := tgbotapi.NewCallback(query.ID, "")
	bot.Request(callback)

	switch strings.ToLower(data) {
	case "fix":
		state, ok := service.GetUserState(userID)
		if !ok || state.LastPhotoPath == "" {
			msg := tgbotapi.NewMessage(chatID, "❌ No recent photo available to fix.")
			bot.Send(msg)
			return
		}

		fixedImage, err := service.AutoFixPhoto(state.LastPhotoPath)
		if err != nil {
			log.Printf("auto-fix failed for user %d: %v", userID, err)
			msg := tgbotapi.NewMessage(chatID, "⚠️ Error processing photo. Try again later.")
			bot.Send(msg)
			return
		}

		photo := tgbotapi.FileBytes{Name: "fixed.jpg", Bytes: fixedImage}
		photoMsg := tgbotapi.NewPhoto(chatID, photo)
		photoMsg.Caption = "✅ Fixed version of your photo"
		bot.Send(photoMsg)

	case "why":
		state, ok := service.GetUserState(userID)
		if !ok || state.LastValidation == nil {
			msg := tgbotapi.NewMessage(chatID, "❌ No validation data found. Please send a photo first.")
			bot.Send(msg)
			return
		}

		explanation := formatWhyFailedMessage(state.LastValidation)
		msg := tgbotapi.NewMessage(chatID, explanation)
		msg.ParseMode = "Markdown"
		bot.Send(msg)

	default:
		msg := tgbotapi.NewMessage(chatID, "⚠️ Unknown action")
		bot.Send(msg)
	}
}

func formatFailureMessage(response *ValidationResponse) string {
	builder := strings.Builder{}
	builder.WriteString("❌ Photo FAILED:\n\n")
	for _, issue := range response.Issues {
		builder.WriteString(fmt.Sprintf("• %s\n", issue))
	}
	builder.WriteString(fmt.Sprintf("\nScore: %d\nProbability: %.2f", response.Score, response.PassProbability))
	return builder.String()
}

func formatWhyFailedMessage(response *ValidationResponse) string {
	builder := strings.Builder{}
	builder.WriteString("🔍 Detailed failure report:\n\n")
	if len(response.Issues) == 0 {
		builder.WriteString("No issues were detected.\n")
	} else {
		builder.WriteString("*Issues:*\n")
		for _, issue := range response.Issues {
			builder.WriteString(fmt.Sprintf("• %s\n", escapeMarkdown(issue)))
		}
		builder.WriteString("\n")
	}

	builder.WriteString("*Metrics:*\n")
	if value, ok := response.Metrics["head_ratio"]; ok {
		builder.WriteString(fmt.Sprintf("• head_ratio: %.1f%%\n", toFloat(value)))
	}
	if value, ok := response.Metrics["eye_level"]; ok {
		builder.WriteString(fmt.Sprintf("• eye_level: %.1f%%\n", toFloat(value)))
	}
	if value, ok := response.Metrics["brightness"]; ok {
		builder.WriteString(fmt.Sprintf("• brightness: %.1f\n", toFloat(value)))
	}
	if value, ok := response.Metrics["blur_score"]; ok {
		builder.WriteString(fmt.Sprintf("• blur_score: %.1f\n", toFloat(value)))
	}
	if value, ok := response.Metrics["face_angle"]; ok {
		if angleMap, ok := value.(map[string]any); ok {
			builder.WriteString("• face_angle:\n")
			if yaw, ok := angleMap["yaw"]; ok {
				builder.WriteString(fmt.Sprintf("  - yaw: %.1f°\n", toFloat(yaw)))
			}
			if pitch, ok := angleMap["pitch"]; ok {
				builder.WriteString(fmt.Sprintf("  - pitch: %.1f°\n", toFloat(pitch)))
			}
			if roll, ok := angleMap["roll"]; ok {
				builder.WriteString(fmt.Sprintf("  - roll: %.1f°\n", toFloat(roll)))
			}
		}
	}
	return builder.String()
}

func toFloat(value any) float64 {
	switch v := value.(type) {
	case float64:
		return v
	case float32:
		return float64(v)
	case int:
		return float64(v)
	case int64:
		return float64(v)
	case json.Number:
		f, _ := v.Float64()
		return f
	default:
		return 0
	}
}

func escapeMarkdown(text string) string {
	replacer := strings.NewReplacer("_", "\\_", "*", "\\*", "[", "\\[", "]", "\\]", "(", "\\(", ")", "\\)", "~", "\\~", "`", "\\`", ">", "\\>", "#", "\\#", "+", "\\+", "-", "\\-", "=", "\\=", "|", "\\|", "{", "\\{", "}", "\\}", ".", "\\.", "!", "\\!")
	return replacer.Replace(text)
}
