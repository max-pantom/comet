# tiktok-scout

A cheap, self-hosted MCP tool that automates Steps 1–3 of the
`slideshow-distribution-app-growth` playbook: search a niche, cache what
comes back, filter down to accounts that are actually winning on a
repeatable format (not a one-off fluke), and pull a report to reverse-
engineer why. The desktop app hosts it over local streamable HTTP so Claude
Code and Codex can share one running server and one cache.

## Why it's built this way

TikTok has no public API for keyword/account search. This uses Playwright
to load the real public web pages and reads the JSON blob TikTok embeds in
the page for its own hydration, instead of a paid scraping API. That keeps
infra cost at $0 (no API credits, no proxy subscription) — the tradeoff is
it's more fragile (breaks when TikTok changes its frontend) and carries the
same ToS risk any unofficial scraper does. Treat it as a personal research
tool, not something you stand up as a public service.

**Run this outside of any locked-down/sandboxed network.** It needs
outbound access to `www.tiktok.com`; most restricted dev containers won't
allow that domain.

## Setup

```bash
cd tiktok-scout
python -m venv .venv && source .venv/bin/activate
pip install -e .
playwright install chromium
```

Playwright is capped below 1.61 because newer browser bundles no longer
support this project's current macOS 13 host. The desktop app uses the same
`.venv` and browser installation.

Note: pinned to `mcp==1.9.4`. The `mcp` package hit a `2.0.0` release that
restructured its API and breaks `FastMCP`'s tool registration as written
here — don't `pip install -U mcp` without checking this server still boots.

## Connecting an agent

Open the desktop app's **MCP server** screen, start the server, then use its
copy buttons. The default endpoint is `http://127.0.0.1:8765/mcp/` and is
bound to this Mac only.

For Claude Code:

```bash
claude mcp add --transport http --scope user comet http://127.0.0.1:8765/mcp/
```

For Codex:

```toml
[mcp_servers.comet]
url = "http://127.0.0.1:8765/mcp/"
```

## Typical session, once it's wired in

```
you: run_playbook_scan(["lock in challenge glow up", "30 day discipline challenge"])
```

`run_playbook_scan` is the preferred end-to-end entry point: it searches
each keyword, deduplicates the surfaced accounts, scans them sequentially,
applies the repeatability filter, and returns reports for every winner. The
four smaller tools remain available for manual step-by-step runs.

MCP clients can read the complete bundled method from
`playbook://slideshow-distribution` or request the
`apply_slideshow_distribution_playbook` prompt.

`find_winning_accounts` only applies the filter over accounts you've
actually scanned with `scan_account` — `search_format` alone just surfaces
candidate usernames, it doesn't pull their full post history. That two-step
split is intentional: it's the expensive/slow part (one full profile load
per account), so you only pay it for accounts worth checking.

## Desktop app

The Comet Wails v2 desktop app lives in `desktop/`. It keeps scraping in Python:

- scrape actions run `python -m tiktok_scout.cli` through the project venv;
- one Go mutex serializes login, search, and account-scan subprocesses;
- cached account lists and reports are read directly from SQLite by Go;
- the app starts and owns one long-running local HTTP MCP server;
- the UI and MCP tools share the configured cache, session, and delay range.
- Activity history is stored in SQLite and streamed live at `/events` while
  the local MCP server is running.

Build and launch the app on macOS:

```bash
cd desktop
$(go env GOPATH)/bin/wails build
open "build/bin/TikTok Scout.app"
```

For live development, run `$(go env GOPATH)/bin/wails dev` from `desktop/`.

The app stores its desktop settings in
`~/.tiktok_scout/desktop_settings.json`. The defaults are:

- cache: `~/.tiktok_scout/cache.db`
- browser session: `~/.tiktok_scout/session.json`
- polite delay: 4–9 seconds after successful scrapes

The Login / Session screen opens visible Google Chrome when it is installed,
or the bundled Playwright Chromium otherwise. Complete TikTok login there;
the Python helper saves Playwright `storage_state` when it sees TikTok's
authenticated session cookie, and future scrapes load that state.

## Staying cheap and not getting blocked immediately

- No proxies by default — your IP eats every rate-limit decision, so
  `scraper.polite_delay()` is called between every scrape. Don't remove it
  or tighten it much; that delay is the entire reason this stays free.
  Speeding it up trades reliability for speed.
- If you start getting `ScrapeBlocked` (captcha wall) constantly, that's
  TikTok flagging the IP/session — the cheap fixes in order: run less
  often, run from a residential connection instead of a datacenter/cloud
  IP, rotate the profile's `User-Agent` list in `scraper.py`. If none of
  that holds up under the volume you need, that's the point where paying
  for a data API (EnsembleData etc.) actually becomes cheaper than the
  time lost to babysitting this.
- Everything scraped is cached in SQLite (`~/.tiktok_scout/cache.db`), so
  re-running `find_winning_accounts` or `account_report` costs nothing —
  only `search_format` / `scan_account` hit the network.

## Known fragility

TikTok's hydration blob shape changes across frontend deploys. If scraping
suddenly returns nothing, open `scraper.py`, load a profile page manually
in a real browser, view source, and check whether the script tag is still
`__UNIVERSAL_DATA_FOR_REHYDRATION__` / `SIGI_STATE` and whether
`_walk_item_list()`'s candidate paths still match. This is the maintenance
cost of the free route — expect to fix this occasionally.

## What's not built yet

- Media download (pulling the actual slide images) — data/stats only for now.
- `analyze_format` as an MCP tool — right now `account_report` just hands
  you the raw top posts; doing the Step-3 hook/DNA breakdown is left to the
  calling agent (Claude Code/Codex), which already does it well from the
  captions + view data.
- Hashtag-based search (only keyword search is wired up).
