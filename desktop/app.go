package main

import (
	"context"
	"fmt"
	"net/url"
	"os"
	"os/exec"
	"path/filepath"
	goruntime "runtime"
	"strings"
	"sync"

	wailsruntime "github.com/wailsapp/wails/v2/pkg/runtime"
)

type App struct {
	ctx         context.Context
	projectRoot string
	settings    Settings
	settingsErr error
	scrapeMu    sync.Mutex
	settingsMu  sync.RWMutex
	mcpMu       sync.Mutex
	mcpCmd      *exec.Cmd
	mcpDone     chan error
	mcpLastErr  string
	mcpStopping bool
}

func NewApp() *App {
	root, rootErr := discoverProjectRoot()
	settings, settingsErr := loadSettings(defaultSettings())
	if rootErr != nil {
		settingsErr = rootErr
	}
	return &App{
		projectRoot: root,
		settings:    settings,
		settingsErr: settingsErr,
	}
}

func (a *App) startup(ctx context.Context) {
	a.ctx = ctx
	if a.settingsSnapshot().MCPAutostart {
		go func() {
			if _, err := a.startMCPServer(false); err != nil {
				a.mcpMu.Lock()
				a.mcpLastErr = err.Error()
				a.mcpMu.Unlock()
			}
		}()
	}
}

func (a *App) shutdown(_ context.Context) {
	_ = a.stopMCPServer(false)
}

func (a *App) GetAppState() (AppState, error) {
	a.settingsMu.RLock()
	settings := a.settings
	err := a.settingsErr
	a.settingsMu.RUnlock()
	if err != nil {
		return AppState{}, err
	}

	return AppState{
		Settings:      settings,
		SettingsPath:  settingsFilePath(),
		ProjectRoot:   a.projectRoot,
		PythonPath:    pythonExecutable(a.projectRoot),
		CacheExists:   fileExists(settings.CacheDBPath),
		SessionExists: fileExists(settings.SessionPath),
	}, nil
}

func (a *App) SaveSettings(settings Settings) (Settings, error) {
	current := a.settingsSnapshot()
	settings.MCPPort = current.MCPPort
	settings.MCPAutostart = current.MCPAutostart
	normalized, err := normalizeSettings(settings)
	if err != nil {
		return Settings{}, err
	}
	if err := writeSettings(normalized); err != nil {
		return Settings{}, err
	}
	a.settingsMu.Lock()
	a.settings = normalized
	a.settingsErr = nil
	a.settingsMu.Unlock()
	return normalized, nil
}

func (a *App) OpenExternalURL(rawURL string) error {
	parsed, err := url.Parse(rawURL)
	if err != nil || (parsed.Scheme != "https" && parsed.Scheme != "http") {
		return fmt.Errorf("invalid web address")
	}
	wailsruntime.BrowserOpenURL(a.ctx, rawURL)
	return nil
}

func (a *App) settingsSnapshot() Settings {
	a.settingsMu.RLock()
	defer a.settingsMu.RUnlock()
	return a.settings
}

func discoverProjectRoot() (string, error) {
	candidates := []string{os.Getenv("TIKTOK_SCOUT_PROJECT_ROOT")}
	if cwd, err := os.Getwd(); err == nil {
		candidates = append(candidates, cwd)
	}
	if executable, err := os.Executable(); err == nil {
		candidates = append(candidates, filepath.Dir(executable))
	}
	if _, filename, _, ok := goruntime.Caller(0); ok {
		candidates = append(candidates, filepath.Dir(filename))
	}

	seen := make(map[string]bool)
	for _, candidate := range candidates {
		if strings.TrimSpace(candidate) == "" {
			continue
		}
		current, err := filepath.Abs(candidate)
		if err != nil {
			continue
		}
		for {
			if !seen[current] {
				seen[current] = true
				if fileExists(filepath.Join(current, "src", "tiktok_scout", "cli.py")) {
					return current, nil
				}
			}
			parent := filepath.Dir(current)
			if parent == current {
				break
			}
			current = parent
		}
	}
	return "", fmt.Errorf("unable to locate the tiktok-scout Python project")
}

func pythonExecutable(projectRoot string) string {
	if goruntime.GOOS == "windows" {
		return filepath.Join(projectRoot, ".venv", "Scripts", "python.exe")
	}
	return filepath.Join(projectRoot, ".venv", "bin", "python")
}

func fileExists(path string) bool {
	info, err := os.Stat(path)
	return err == nil && !info.IsDir()
}
