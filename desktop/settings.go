package main

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

type Settings struct {
	MinDelaySeconds float64 `json:"min_delay_seconds"`
	MaxDelaySeconds float64 `json:"max_delay_seconds"`
	CacheDBPath     string  `json:"cache_db_path"`
	SessionPath     string  `json:"session_path"`
	MCPPort         int     `json:"mcp_port"`
	MCPAutostart    bool    `json:"mcp_autostart"`
}

type AppState struct {
	Settings      Settings `json:"settings"`
	SettingsPath  string   `json:"settings_path"`
	ProjectRoot   string   `json:"project_root"`
	PythonPath    string   `json:"python_path"`
	CacheExists   bool     `json:"cache_exists"`
	SessionExists bool     `json:"session_exists"`
}

func defaultSettings() Settings {
	home, _ := os.UserHomeDir()
	base := filepath.Join(home, ".tiktok_scout")
	return Settings{
		MinDelaySeconds: 4,
		MaxDelaySeconds: 9,
		CacheDBPath:     filepath.Join(base, "cache.db"),
		SessionPath:     filepath.Join(base, "session.json"),
		MCPPort:         8765,
		MCPAutostart:    false,
	}
}

func settingsFilePath() string {
	home, _ := os.UserHomeDir()
	return filepath.Join(home, ".tiktok_scout", "desktop_settings.json")
}

func loadSettings(defaults Settings) (Settings, error) {
	data, err := os.ReadFile(settingsFilePath())
	if os.IsNotExist(err) {
		return defaults, nil
	}
	if err != nil {
		return defaults, fmt.Errorf("read desktop settings: %w", err)
	}
	settings := defaults
	if err := json.Unmarshal(data, &settings); err != nil {
		return defaults, fmt.Errorf("parse desktop settings: %w", err)
	}
	return normalizeSettings(settings)
}

func normalizeSettings(settings Settings) (Settings, error) {
	if settings.MinDelaySeconds < 0 || settings.MaxDelaySeconds < 0 {
		return Settings{}, fmt.Errorf("delay values cannot be negative")
	}
	if settings.MaxDelaySeconds < settings.MinDelaySeconds {
		return Settings{}, fmt.Errorf("maximum delay must be greater than or equal to minimum delay")
	}
	if settings.MCPPort < 1024 || settings.MCPPort > 65535 {
		return Settings{}, fmt.Errorf("MCP port must be between 1024 and 65535")
	}

	var err error
	settings.CacheDBPath, err = normalizePath(settings.CacheDBPath)
	if err != nil {
		return Settings{}, fmt.Errorf("cache database path: %w", err)
	}
	settings.SessionPath, err = normalizePath(settings.SessionPath)
	if err != nil {
		return Settings{}, fmt.Errorf("session file path: %w", err)
	}
	return settings, nil
}

func normalizePath(path string) (string, error) {
	path = strings.TrimSpace(path)
	if path == "" {
		return "", fmt.Errorf("path is required")
	}
	if path == "~" || strings.HasPrefix(path, "~/") {
		home, err := os.UserHomeDir()
		if err != nil {
			return "", err
		}
		path = filepath.Join(home, strings.TrimPrefix(path, "~/"))
	}
	return filepath.Abs(path)
}

func writeSettings(settings Settings) error {
	path := settingsFilePath()
	if err := os.MkdirAll(filepath.Dir(path), 0o700); err != nil {
		return fmt.Errorf("create settings directory: %w", err)
	}
	data, err := json.MarshalIndent(settings, "", "  ")
	if err != nil {
		return fmt.Errorf("encode desktop settings: %w", err)
	}
	temporary, err := os.CreateTemp(filepath.Dir(path), "desktop_settings-*.tmp")
	if err != nil {
		return fmt.Errorf("create temporary settings file: %w", err)
	}
	temporaryPath := temporary.Name()
	defer os.Remove(temporaryPath)
	if err := temporary.Chmod(0o600); err != nil {
		temporary.Close()
		return fmt.Errorf("protect temporary settings file: %w", err)
	}
	if _, err := temporary.Write(data); err != nil {
		temporary.Close()
		return fmt.Errorf("write desktop settings: %w", err)
	}
	if err := temporary.Close(); err != nil {
		return fmt.Errorf("close desktop settings: %w", err)
	}
	if err := os.Rename(temporaryPath, path); err != nil {
		return fmt.Errorf("save desktop settings: %w", err)
	}
	return nil
}
