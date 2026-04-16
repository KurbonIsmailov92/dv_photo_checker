package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"mime/multipart"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"time"

	tgbotapi "github.com/go-telegram-bot-api/telegram-bot-api/v5"
)

type ValidationResponse struct {
	Valid           bool           `json:"valid"`
	Score           float64        `json:"score"`
	PassProbability float64        `json:"pass_probability"`
	Issues          []string       `json:"issues"`
	Metrics         map[string]any `json:"metrics"`
	Detail          map[string]any `json:"detail,omitempty"`
}

type UserState struct {
	LastPhotoPath  string
	LastValidation *ValidationResponse
	Checks         int
}

type StateStore struct {
	mu    sync.RWMutex
	users map[int64]*UserState
}

type PhotoService struct {
	client     *http.Client
	backendURL string
	store      *StateStore
}

func NewPhotoService(backendURL string) *PhotoService {
	return &PhotoService{
		client:     &http.Client{Timeout: 5 * time.Second},
		backendURL: strings.TrimRight(backendURL, "/"),
		store:      &StateStore{users: make(map[int64]*UserState)},
	}
}

func (s *PhotoService) EnsureUserState(userID int64) *UserState {
	s.store.mu.Lock()
	defer s.store.mu.Unlock()
	state, ok := s.store.users[userID]
	if !ok {
		state = &UserState{}
		s.store.users[userID] = state
	}
	return state
}

func (s *PhotoService) CanUseFreeCheck(userID int64) bool {
	s.store.mu.RLock()
	defer s.store.mu.RUnlock()
	state, ok := s.store.users[userID]
	if !ok {
		return true
	}
	return state.Checks < 3
}

func (s *PhotoService) IncrementChecks(userID int64) int {
	state := s.EnsureUserState(userID)
	state.Checks++
	return state.Checks
}

func (s *PhotoService) SaveUserPhoto(userID int64, path string) {
	state := s.EnsureUserState(userID)
	state.LastPhotoPath = path
}

func (s *PhotoService) SaveValidation(userID int64, response *ValidationResponse) {
	state := s.EnsureUserState(userID)
	state.LastValidation = response
}

func (s *PhotoService) GetUserState(userID int64) (*UserState, bool) {
	s.store.mu.RLock()
	defer s.store.mu.RUnlock()
	state, ok := s.store.users[userID]
	return state, ok
}

func (s *PhotoService) DownloadTelegramPhoto(bot *tgbotapi.BotAPI, fileID string, userID int64) (string, error) {
	fileConfig := tgbotapi.FileConfig{FileID: fileID}
	file, err := bot.GetFile(fileConfig)
	if err != nil {
		return "", err
	}

	url := file.Link(bot.Token)
	resp, err := s.client.Get(url)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return "", fmt.Errorf("download failed with status %d", resp.StatusCode)
	}

	tempDir := os.TempDir()
	path := filepath.Join(tempDir, fmt.Sprintf("dvphoto_%d_%d.jpg", userID, time.Now().UnixNano()))
	out, err := os.Create(path)
	if err != nil {
		return "", err
	}
	defer out.Close()

	_, err = io.Copy(out, resp.Body)
	if err != nil {
		return "", err
	}

	return path, nil
}

func (s *PhotoService) ValidatePhoto(path string) (*ValidationResponse, error) {
	body, contentType, err := createMultipartBody("image", path)
	if err != nil {
		return nil, err
	}

	requestURL := fmt.Sprintf("%s/validate", s.backendURL)
	req, err := http.NewRequest(http.MethodPost, requestURL, body)
	if err != nil {
		return nil, err
	}
	req.Header.Set("Content-Type", contentType)

	resp, err := s.client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	payload, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, err
	}
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("backend returned %d: %s", resp.StatusCode, string(payload))
	}

	var result ValidationResponse
	if err := json.Unmarshal(payload, &result); err != nil {
		return nil, err
	}
	return &result, nil
}

func (s *PhotoService) AutoFixPhoto(path string) ([]byte, error) {
	body, contentType, err := createMultipartBody("image", path)
	if err != nil {
		return nil, err
	}

	requestURL := fmt.Sprintf("%s/auto-fix", s.backendURL)
	req, err := http.NewRequest(http.MethodPost, requestURL, body)
	if err != nil {
		return nil, err
	}
	req.Header.Set("Content-Type", contentType)

	resp, err := s.client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		payload, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("backend returned %d: %s", resp.StatusCode, string(payload))
	}

	return io.ReadAll(resp.Body)
}

func createMultipartBody(fieldName, path string) (*bytes.Buffer, string, error) {
	file, err := os.Open(path)
	if err != nil {
		return nil, "", err
	}
	defer file.Close()

	body := &bytes.Buffer{}
	writer := multipart.NewWriter(body)
	part, err := writer.CreateFormFile(fieldName, filepath.Base(path))
	if err != nil {
		return nil, "", err
	}
	if _, err := io.Copy(part, file); err != nil {
		return nil, "", err
	}
	writer.Close()
	return body, writer.FormDataContentType(), nil
}
