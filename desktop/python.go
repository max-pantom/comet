package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"strconv"
	"strings"

	wailsruntime "github.com/wailsapp/wails/v2/pkg/runtime"
)

type Post struct {
	PostID       string  `json:"post_id"`
	Username     string  `json:"username"`
	Caption      string  `json:"caption"`
	CreateTime   *string `json:"create_time"`
	ViewCount    int64   `json:"view_count"`
	LikeCount    int64   `json:"like_count"`
	CommentCount int64   `json:"comment_count"`
	ShareCount   int64   `json:"share_count"`
	IsSlideshow  bool    `json:"is_slideshow"`
	ImageCount   int     `json:"image_count"`
	URL          string  `json:"url"`
}

type SearchResult struct {
	OK      bool   `json:"ok"`
	Command string `json:"command"`
	Cached  *int   `json:"cached"`
	Count   int    `json:"count"`
	Posts   []Post `json:"posts"`
}

type LoginResult struct {
	OK          bool     `json:"ok"`
	Saved       bool     `json:"saved"`
	SessionPath string   `json:"session_path"`
	AuthCookies []string `json:"auth_cookies"`
}

type cliEnvelope struct {
	OK    bool   `json:"ok"`
	Error string `json:"error"`
}

func (a *App) LoginSession() (LoginResult, error) {
	settings := a.settingsSnapshot()
	x, y := wailsruntime.WindowGetPosition(a.ctx)
	width, height := wailsruntime.WindowGetSize(a.ctx)
	browserWidth := width / 3
	if browserWidth < 420 {
		browserWidth = 420
	}
	var result LoginResult
	err := a.runScrapeCLI(&result,
		"login-session",
		"--session-path", settings.SessionPath,
		"--timeout", "300",
		"--window-x", strconv.Itoa(x+width+8),
		"--window-y", strconv.Itoa(y),
		"--window-width", strconv.Itoa(browserWidth),
		"--window-height", strconv.Itoa(height),
	)
	return result, err
}

func (a *App) SearchFormat(keyword string, maxResults int) (SearchResult, error) {
	keyword = strings.TrimSpace(keyword)
	if keyword == "" {
		return SearchResult{}, fmt.Errorf("enter a keyword to search")
	}
	if maxResults <= 0 {
		maxResults = 20
	}
	settings := a.settingsSnapshot()
	var result SearchResult
	err := a.runScrapeCLI(&result,
		"search-format", keyword,
		"--max-results", strconv.Itoa(maxResults),
		"--db-path", settings.CacheDBPath,
		"--session-path", settings.SessionPath,
		"--min-delay", formatFloat(settings.MinDelaySeconds),
		"--max-delay", formatFloat(settings.MaxDelaySeconds),
	)
	return result, err
}

func (a *App) ScanAccount(username string, maxResults int) (SearchResult, error) {
	username = strings.TrimPrefix(strings.TrimSpace(username), "@")
	if username == "" {
		return SearchResult{}, fmt.Errorf("enter an account username")
	}
	if maxResults <= 0 {
		maxResults = 30
	}
	settings := a.settingsSnapshot()
	var result SearchResult
	err := a.runScrapeCLI(&result,
		"scan-account", username,
		"--max-results", strconv.Itoa(maxResults),
		"--db-path", settings.CacheDBPath,
		"--session-path", settings.SessionPath,
		"--min-delay", formatFloat(settings.MinDelaySeconds),
		"--max-delay", formatFloat(settings.MaxDelaySeconds),
	)
	return result, err
}

func (a *App) runScrapeCLI(target any, arguments ...string) error {
	a.scrapeMu.Lock()
	defer a.scrapeMu.Unlock()
	settings := a.settingsSnapshot()
	tool := "python"
	if len(arguments) > 0 {
		tool = arguments[0]
	}
	activityID, _ := writeActivity(settings.CacheDBPath, tool, map[string]any{"args": arguments[1:]}, "running", "", 0)
	err := a.runCLI(target, arguments...)
	status, summary := "done", "Completed"
	if err != nil {
		status, summary = "error", err.Error()
	}
	_, _ = writeActivity(settings.CacheDBPath, tool, nil, status, summary, activityID)
	return err
}

func (a *App) runCLI(target any, arguments ...string) error {
	python := pythonExecutable(a.projectRoot)
	if !fileExists(python) {
		return fmt.Errorf("Python environment not found at %s", python)
	}
	commandArgs := append([]string{"-m", "tiktok_scout.cli"}, arguments...)
	command := exec.CommandContext(a.ctx, python, commandArgs...)
	command.Dir = a.projectRoot
	command.Env = append(os.Environ(), "PYTHONUNBUFFERED=1")

	var stdout bytes.Buffer
	var stderr bytes.Buffer
	command.Stdout = &stdout
	command.Stderr = &stderr
	runErr := command.Run()

	var envelope cliEnvelope
	if err := json.Unmarshal(stdout.Bytes(), &envelope); err != nil {
		detail := strings.TrimSpace(stderr.String())
		if detail == "" {
			detail = strings.TrimSpace(stdout.String())
		}
		if detail == "" {
			detail = "no output"
		}
		return fmt.Errorf("Python returned invalid JSON: %s", detail)
	}
	if envelope.Error != "" {
		return fmt.Errorf("%s", envelope.Error)
	}
	if runErr != nil {
		detail := strings.TrimSpace(stderr.String())
		if detail != "" {
			return fmt.Errorf("Python command failed: %s", detail)
		}
		return fmt.Errorf("Python command failed: %w", runErr)
	}
	if !envelope.OK {
		return fmt.Errorf("Python command did not complete")
	}
	if err := json.Unmarshal(stdout.Bytes(), target); err != nil {
		return fmt.Errorf("parse Python response: %w", err)
	}
	return nil
}

func formatFloat(value float64) string {
	return strconv.FormatFloat(value, 'f', -1, 64)
}
