# Comet desktop

Wails v2 + vanilla JavaScript desktop UI for the Python `tiktok-scout`
scraper. The app deliberately does not reimplement scraping in Go.

## Architecture

- `python.go` runs `../.venv/bin/python -m tiktok_scout.cli` and parses its
  one-object JSON response.
- `App.scrapeMu` serializes login, keyword search, and account scan actions.
- `database.go` opens the configured SQLite cache in read-only mode for the
  Accounts and Account report screens.
- `settings.go` stores delay and file-path settings in
  `~/.tiktok_scout/desktop_settings.json`.
- `mcp.go` owns the long-running streamable-HTTP MCP process, remembers its
  on/off state, and passes the same cache, session, and delay settings.
- `frontend/` is the Wails vanilla/Vite interface.

## Development

From this directory:

```bash
$(go env GOPATH)/bin/wails dev
```

The Python project must already be installed in `../.venv`, including its
Playwright Chromium browser.

## Tests and build

```bash
go test ./...
go vet ./...
npm --prefix frontend run build
$(go env GOPATH)/bin/wails build -clean

# Build and replace the installed macOS app (also removes the old TikTok Scout.app)
./install-macos.sh
```

The macOS application is written to `build/bin/Comet.app`.
