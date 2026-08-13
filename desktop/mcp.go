package main

import (
	"fmt"
	"net"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"time"

	wailsruntime "github.com/wailsapp/wails/v2/pkg/runtime"
)

type MCPStatus struct {
	Running   bool   `json:"running"`
	URL       string `json:"url"`
	Port      int    `json:"port"`
	PID       int    `json:"pid"`
	Autostart bool   `json:"autostart"`
	Error     string `json:"error"`
}

func mcpURL(port int) string {
	return fmt.Sprintf("http://127.0.0.1:%d/mcp/", port)
}

func (a *App) GetMCPStatus() MCPStatus {
	settings := a.settingsSnapshot()
	a.mcpMu.Lock()
	defer a.mcpMu.Unlock()
	status := MCPStatus{
		URL:       mcpURL(settings.MCPPort),
		Port:      settings.MCPPort,
		Autostart: settings.MCPAutostart,
		Error:     a.mcpLastErr,
	}
	if a.mcpCmd != nil && a.mcpCmd.Process != nil && a.mcpCmd.ProcessState == nil {
		status.Running = true
		status.PID = a.mcpCmd.Process.Pid
	}
	return status
}

func (a *App) StartMCPServer() (MCPStatus, error) {
	return a.startMCPServer(true)
}

func (a *App) startMCPServer(remember bool) (MCPStatus, error) {
	a.mcpMu.Lock()
	if a.mcpCmd != nil && a.mcpCmd.Process != nil && a.mcpCmd.ProcessState == nil {
		a.mcpMu.Unlock()
		if remember {
			_ = a.persistMCPAutostart(true)
		}
		return a.GetMCPStatus(), nil
	}

	settings := a.settingsSnapshot()
	python := pythonExecutable(a.projectRoot)
	if !fileExists(python) {
		a.mcpMu.Unlock()
		return MCPStatus{}, fmt.Errorf("Python environment not found at %s", python)
	}

	logPath := filepath.Join(filepath.Dir(settingsFilePath()), "mcp.log")
	if err := os.MkdirAll(filepath.Dir(logPath), 0o700); err != nil {
		a.mcpMu.Unlock()
		return MCPStatus{}, fmt.Errorf("create MCP log directory: %w", err)
	}
	logFile, err := os.OpenFile(logPath, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0o600)
	if err != nil {
		a.mcpMu.Unlock()
		return MCPStatus{}, fmt.Errorf("open MCP log: %w", err)
	}

	command := exec.Command(
		python,
		"-m", "tiktok_scout.server",
		"--transport", "streamable-http",
		"--host", "127.0.0.1",
		"--port", strconv.Itoa(settings.MCPPort),
	)
	command.Dir = a.projectRoot
	command.Env = append(
		os.Environ(),
		"PYTHONUNBUFFERED=1",
		"TIKTOK_SCOUT_DB_PATH="+settings.CacheDBPath,
		"TIKTOK_SCOUT_SESSION_PATH="+settings.SessionPath,
		"TIKTOK_SCOUT_MIN_DELAY="+formatFloat(settings.MinDelaySeconds),
		"TIKTOK_SCOUT_MAX_DELAY="+formatFloat(settings.MaxDelaySeconds),
		"TIKTOK_SCOUT_MCP_PORT="+strconv.Itoa(settings.MCPPort),
	)
	command.Stdout = logFile
	command.Stderr = logFile
	if err := command.Start(); err != nil {
		logFile.Close()
		a.mcpMu.Unlock()
		return MCPStatus{}, fmt.Errorf("start MCP server: %w", err)
	}

	done := make(chan error, 1)
	a.mcpCmd = command
	a.mcpDone = done
	a.mcpLastErr = ""
	a.mcpStopping = false
	a.mcpMu.Unlock()

	go func() {
		err := command.Wait()
		logFile.Close()
		done <- err
		close(done)
		a.mcpMu.Lock()
		if a.mcpCmd == command {
			stopping := a.mcpStopping
			a.mcpCmd = nil
			a.mcpDone = nil
			a.mcpStopping = false
			if err != nil && !stopping {
				a.mcpLastErr = strings.TrimSpace(err.Error())
			}
		}
		a.mcpMu.Unlock()
	}()

	deadline := time.Now().Add(8 * time.Second)
	address := fmt.Sprintf("127.0.0.1:%d", settings.MCPPort)
	for time.Now().Before(deadline) {
		connection, dialErr := net.DialTimeout("tcp", address, 180*time.Millisecond)
		if dialErr == nil {
			connection.Close()
			if remember {
				if err := a.persistMCPAutostart(true); err != nil {
					return a.GetMCPStatus(), err
				}
			}
			return a.GetMCPStatus(), nil
		}
		select {
		case processErr := <-done:
			if processErr == nil {
				processErr = fmt.Errorf("server exited before opening its port")
			}
			return a.GetMCPStatus(), fmt.Errorf("MCP server failed to start: %w", processErr)
		case <-time.After(120 * time.Millisecond):
		}
	}
	_ = a.stopMCPServer(false)
	return a.GetMCPStatus(), fmt.Errorf("MCP server did not open %s within 8 seconds", address)
}

func (a *App) StopMCPServer() (MCPStatus, error) {
	err := a.stopMCPServer(true)
	return a.GetMCPStatus(), err
}

func (a *App) stopMCPServer(remember bool) error {
	a.mcpMu.Lock()
	command := a.mcpCmd
	done := a.mcpDone
	if command != nil {
		a.mcpStopping = true
		a.mcpLastErr = ""
	}
	a.mcpMu.Unlock()

	if command != nil && command.Process != nil && command.ProcessState == nil {
		_ = command.Process.Signal(os.Interrupt)
		if done != nil {
			select {
			case <-done:
			case <-time.After(4 * time.Second):
				_ = command.Process.Kill()
				<-done
			}
		}
	}
	if remember {
		return a.persistMCPAutostart(false)
	}
	return nil
}

func (a *App) SetMCPPort(port int) (MCPStatus, error) {
	a.mcpMu.Lock()
	running := a.mcpCmd != nil && a.mcpCmd.Process != nil && a.mcpCmd.ProcessState == nil
	a.mcpMu.Unlock()
	if running {
		return a.GetMCPStatus(), fmt.Errorf("stop the MCP server before changing its port")
	}

	settings := a.settingsSnapshot()
	settings.MCPPort = port
	normalized, err := normalizeSettings(settings)
	if err != nil {
		return a.GetMCPStatus(), err
	}
	if err := writeSettings(normalized); err != nil {
		return a.GetMCPStatus(), err
	}
	a.settingsMu.Lock()
	a.settings = normalized
	a.settingsMu.Unlock()
	return a.GetMCPStatus(), nil
}

func (a *App) CopyMCPConfig(client string) (string, error) {
	status := a.GetMCPStatus()
	var config string
	switch strings.ToLower(strings.TrimSpace(client)) {
	case "codex":
		config = fmt.Sprintf("[mcp_servers.tiktok-scout]\nurl = %q", status.URL)
	case "claude", "claude-code":
		config = fmt.Sprintf(
			"claude mcp add --transport http --scope user tiktok-scout %s",
			status.URL,
		)
	default:
		return "", fmt.Errorf("choose Codex or Claude Code")
	}
	if err := wailsruntime.ClipboardSetText(a.ctx, config); err != nil {
		return "", fmt.Errorf("copy MCP config: %w", err)
	}
	return config, nil
}

func (a *App) persistMCPAutostart(value bool) error {
	settings := a.settingsSnapshot()
	settings.MCPAutostart = value
	if err := writeSettings(settings); err != nil {
		return fmt.Errorf("save MCP restart preference: %w", err)
	}
	a.settingsMu.Lock()
	a.settings = settings
	a.settingsMu.Unlock()
	return nil
}
