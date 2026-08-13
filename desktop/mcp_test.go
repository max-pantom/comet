package main

import (
	"fmt"
	"net"
	"path/filepath"
	"testing"
	"time"
)

func TestMCPServerLifecycle(t *testing.T) {
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	port := listener.Addr().(*net.TCPAddr).Port
	listener.Close()
	if port < 1024 {
		t.Skip("operating system selected a privileged test port")
	}

	app := NewApp()
	if !fileExists(pythonExecutable(app.projectRoot)) {
		t.Skip("project virtual environment is unavailable")
	}
	temp := t.TempDir()
	app.settings = Settings{
		MinDelaySeconds: 0,
		MaxDelaySeconds: 0,
		CacheDBPath:     filepath.Join(temp, "cache.db"),
		SessionPath:     filepath.Join(temp, "session.json"),
		MCPPort:         port,
	}

	status, err := app.startMCPServer(false)
	if err != nil {
		t.Fatalf("start MCP server: %v", err)
	}
	if !status.Running || status.URL != mcpURL(port) || status.PID == 0 {
		t.Fatalf("unexpected running status: %+v", status)
	}

	connection, err := net.DialTimeout("tcp", listenerAddress(port), time.Second)
	if err != nil {
		t.Fatalf("MCP port is not reachable: %v", err)
	}
	connection.Close()

	if err := app.stopMCPServer(false); err != nil {
		t.Fatalf("stop MCP server: %v", err)
	}
	if status := app.GetMCPStatus(); status.Running {
		t.Fatalf("server still reports running after stop: %+v", status)
	}
}

func listenerAddress(port int) string {
	return net.JoinHostPort("127.0.0.1", fmt.Sprint(port))
}
