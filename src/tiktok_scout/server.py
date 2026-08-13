"""
MCP server for tiktok-scout.

Exposes the slideshow-distribution-app-growth playbook's Step 2/3 workflow
as tools an agent (Claude Code, Codex, etc.) can call directly:

  - search_format(keyword)      -> scrape + cache posts matching a keyword
  - scan_account(username)      -> scrape + cache a specific account's posts
  - find_winning_accounts(...)  -> apply the playbook's filters over cached data
  - account_report(username)    -> raw stats + top posts for Step-3 analysis
  - run_playbook_scan(...)      -> run the complete search/scan/filter/report flow

Run it with:  python -m tiktok_scout.server
Then point Claude Code / Codex at http://127.0.0.1:8765/mcp.
"""

import asyncio
import argparse
import json
import time
from dataclasses import asdict
import logging
import os
from urllib.parse import quote_plus, urlparse
from urllib.request import urlopen
from pathlib import Path
from typing import Any, Iterable

from mcp.server.fastmcp import FastMCP
from starlette.routing import WebSocketRoute
from starlette.websockets import WebSocket, WebSocketDisconnect
import uvicorn

from . import scraper
from .storage import Store

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

mcp = FastMCP(
    "comet",
    instructions=(
        "Comet serializes scrape tools so pacing is preserved. Prefer "
        "run_playbook_scan for the complete workflow. The underlying method is "
        "available at playbook://slideshow-distribution. Keep the smaller tools "
        "for deliberate one-step runs. All tools share the desktop app's cache."
    ),
)
_store = Store(Path(os.environ.get("TIKTOK_SCOUT_DB_PATH", "~/.tiktok_scout/cache.db")).expanduser())
_scrape_lock = asyncio.Lock()
_playbook_path = (
    Path(__file__).with_name("playbooks")
    / "slideshow-distribution-app-growth"
    / "SKILL.md"
)
_activity_clients: set[asyncio.Queue[str]] = set()


def _activity_row(activity_id: int) -> dict[str, Any]:
    row = _store.conn.execute(
        "SELECT * FROM activity_log WHERE id = ?", (activity_id,)
    ).fetchone()
    if row is None:
        return {"id": activity_id}
    # sqlite3.Row is not enabled globally, so read the known columns explicitly.
    values = _store.conn.execute(
        "SELECT id, tool_name, args, reason, status, result_summary, screenshot_path, started_at, finished_at FROM activity_log WHERE id = ?",
        (activity_id,),
    ).fetchone()
    keys = ("id", "tool_name", "args", "reason", "status", "result_summary", "screenshot_path", "started_at", "finished_at")
    payload = dict(zip(keys, values))
    try:
        payload["args"] = json.loads(payload["args"] or "{}")
    except json.JSONDecodeError:
        pass
    return payload


async def _broadcast_activity(activity_id: int) -> None:
    message = json.dumps(_activity_row(activity_id), ensure_ascii=False)
    for queue in tuple(_activity_clients):
        await queue.put(message)


async def _activity_start(tool_name: str, args: dict[str, Any], reason: str = "") -> int:
    activity_id = _store.activity_start(tool_name, args, reason)
    await _broadcast_activity(activity_id)
    return activity_id


async def _activity_finish(
    activity_id: int,
    status: str,
    result_summary: str = "",
    screenshot_path: str = "",
) -> None:
    _store.activity_finish(activity_id, status, result_summary, screenshot_path)
    await _broadcast_activity(activity_id)


async def _activity_events(websocket: WebSocket) -> None:
    await websocket.accept()
    queue: asyncio.Queue[str] = asyncio.Queue()
    _activity_clients.add(queue)
    try:
        for row in _store.recent_activity(100)[::-1]:
            payload = dict(row)
            try:
                payload["args"] = json.loads(payload["args"] or "{}")
            except json.JSONDecodeError:
                pass
            await websocket.send_json(payload)
        while True:
            await websocket.send_text(await queue.get())
    except WebSocketDisconnect:
        pass
    finally:
        _activity_clients.discard(queue)


def _http_app():
    app = mcp.streamable_http_app()
    app.routes.append(WebSocketRoute("/events", _activity_events))
    return app


async def _run_http() -> None:
    config = uvicorn.Config(
        _http_app(), host=mcp.settings.host, port=mcp.settings.port, log_level="info"
    )
    await uvicorn.Server(config).serve()


def _delay_range() -> tuple[float, float]:
    return (
        float(os.environ.get("TIKTOK_SCOUT_MIN_DELAY", "4")),
        float(os.environ.get("TIKTOK_SCOUT_MAX_DELAY", "9")),
    )


def _playbook_text() -> str:
    return _playbook_path.read_text(encoding="utf-8")


@mcp.resource(
    "playbook://slideshow-distribution",
    name="Slideshow distribution app-growth playbook",
    description=(
        "The complete format-first TikTok slideshow research and distribution method."
    ),
    mime_type="text/markdown",
)
def slideshow_distribution_playbook() -> str:
    """Return the playbook bundled with this MCP server."""
    return _playbook_text()


@mcp.prompt(
    name="apply_slideshow_distribution_playbook",
    description="Apply the bundled format-first slideshow growth method.",
)
def apply_slideshow_distribution_playbook() -> str:
    """Give an agent the method and the preferred automated entry point."""
    return (
        _playbook_text()
        + "\n\n## Comet execution\n\n"
        + "Use `run_playbook_scan` to execute Steps 2–3 as one serialized run."
    )


async def _search_and_cache(keyword: str, max_results: int = 20) -> tuple[list[Any], int]:
    try:
        posts = await scraper.search_keyword(keyword, max_results=max_results)
        return posts, _store.upsert_posts(posts)
    finally:
        await scraper.polite_delay(*_delay_range())


async def _scan_and_cache(username: str, max_results: int = 30) -> tuple[list[Any], int]:
    try:
        posts = await scraper.get_user_posts(username, max_results=max_results)
        return posts, _store.upsert_posts(posts)
    finally:
        await scraper.polite_delay(*_delay_range())


def _winning_accounts(
    usernames: Iterable[str],
    *,
    min_total_views_30d: int,
    min_posts_last_30d: int,
    max_single_post_share: float,
) -> list[Any]:
    winners = []
    for username in usernames:
        stats = _store.compute_account_stats(username)
        if stats.passes_playbook_filters(
            min_total_views_30d=min_total_views_30d,
            min_posts_last_30d=min_posts_last_30d,
            max_single_post_share=max_single_post_share,
        ):
            winners.append(stats)
    winners.sort(key=lambda stats: stats.total_views_last_30d, reverse=True)
    return winners


def _stats_payload(stats: Any) -> dict[str, Any]:
    payload = asdict(stats)
    payload["max_single_post_share"] = (
        stats.max_single_post_views / stats.total_views_last_30d
        if stats.total_views_last_30d
        else 0.0
    )
    return payload


def _report_payload(username: str, top_n: int = 8) -> dict[str, Any]:
    stats = _store.compute_account_stats(username)
    rows = _store.posts_for_username(username)
    top = sorted(rows, key=lambda row: row["view_count"] or 0, reverse=True)[:top_n]
    return {
        "stats": _stats_payload(stats),
        "top_posts": [dict(row) for row in top],
    }


def _app_link_kind(link: str) -> str:
    host = (urlparse(link).hostname or "").lower()
    if host in {"apps.apple.com", "itunes.apple.com", "play.google.com"}:
        return "app_store"
    if any(host == domain or host.endswith("." + domain) for domain in ("linktr.ee", "beacons.ai", "stan.store", "lnk.bio", "bio.site")):
        return "needs_manual_check"
    return "other"


@mcp.tool()
async def check_app_store(query: str, country: str = "us", limit: int = 10) -> dict[str, Any]:
    """Check Apple's public iTunes Search API for competing apps."""
    query = query.strip()
    if not query:
        raise ValueError("Provide an app or idea to search for")
    if not 1 <= limit <= 50:
        raise ValueError("limit must be between 1 and 50")
    activity_id = await _activity_start("check_app_store", {"query": query, "country": country, "limit": limit})
    try:
        url = "https://itunes.apple.com/search?term=" + quote_plus(query) + f"&country={quote_plus(country)}&entity=software&limit={limit}"
        with urlopen(url, timeout=15) as response:
            payload = json.load(response)
        apps = []
        for rank, item in enumerate(payload.get("results", [])[:limit], 1):
            apps.append({"rank": rank, "name": item.get("trackName", ""), "artist": item.get("artistName", ""), "rating": item.get("averageUserRating"), "rating_count": item.get("userRatingCount", 0), "url": item.get("trackViewUrl", ""), "artwork_url": item.get("artworkUrl100", "")})
        result = {"query": query, "country": country, "result_count": len(apps), "apps": apps}
        await _activity_finish(activity_id, "done", f"Found {len(apps)} App Store matches")
        return result
    except Exception as exc:
        await _activity_finish(activity_id, "error", str(exc))
        raise


@mcp.tool()
async def discover_niches(seed_category: str, max_results: int = 20) -> dict[str, Any]:
    """Discover adjacent hashtags surfaced by TikTok search results."""
    seed = seed_category.strip().lstrip("#")
    if not seed:
        raise ValueError("Provide a seed category")
    activity_id = await _activity_start("discover_niches", {"seed_category": seed, "max_results": max_results})
    try:
        async with _scrape_lock:
            posts, _ = await _search_and_cache(seed, max_results=max_results)
        counts: dict[str, int] = {}
        for post in posts:
            for tag in post.caption.split():
                if tag.startswith("#"):
                    key = tag.strip("#,.!?\"'()[]{}").lower()
                    if key and key != seed.lower():
                        counts[key] = counts.get(key, 0) + max(post.view_count, 0)
        candidates = [{"keyword": k, "rough_view_volume": v} for k, v in sorted(counts.items(), key=lambda pair: pair[1], reverse=True)[:max_results]]
        result = {"seed_category": seed, "candidates": candidates, "source": "TikTok search result captions"}
        await _activity_finish(activity_id, "done", f"Found {len(candidates)} adjacent hashtags")
        return result
    except Exception as exc:
        await _activity_finish(activity_id, "error", str(exc))
        raise


@mcp.tool()
async def find_app_accounts(keywords: list[str], max_results: int = 20) -> dict[str, Any]:
    """Find surfaced accounts and classify their bio links."""
    terms = list(dict.fromkeys(k.strip() for k in keywords if k.strip()))
    if not terms:
        raise ValueError("Provide at least one keyword")
    activity_id = await _activity_start("find_app_accounts", {"keywords": terms, "max_results": max_results})
    try:
        accounts: dict[str, dict[str, Any]] = {}
        async with _scrape_lock:
            for term in terms:
                posts, _ = await _search_and_cache(term, max_results=max_results)
                for post in posts:
                    if post.username:
                        accounts.setdefault(post.username, {"username": post.username, "bio_link": post.bio_link, "link_kind": _app_link_kind(post.bio_link) if post.bio_link else "none"})
        values = list(accounts.values())
        result = {"keywords": terms, "app_accounts": [a for a in values if a["link_kind"] == "app_store"], "needs_manual_check": [a for a in values if a["link_kind"] == "needs_manual_check"], "unclaimed_accounts": [a for a in values if a["link_kind"] == "none"], "all_accounts": values}
        await _activity_finish(activity_id, "done", f"Classified {len(values)} accounts")
        return result
    except Exception as exc:
        await _activity_finish(activity_id, "error", str(exc))
        raise


@mcp.tool()
async def search_format(keyword: str, max_results: int = 20) -> str:
    """
    Search TikTok for a keyword/niche phrase and cache what comes back.
    Use this for Step 1/2 of the playbook: sweeping a sub-niche's keywords
    to build a swipe file of posts before filtering down to real accounts.
    """
    activity_id = await _activity_start("search_format", {"keyword": keyword, "max_results": max_results})
    try:
        async with _scrape_lock:
            posts, n = await _search_and_cache(keyword, max_results=max_results)
        usernames = sorted({p.username for p in posts if p.username})
        result = (
            f"Cached {n} posts for keyword '{keyword}'. "
            f"Touched {len(usernames)} accounts: {', '.join(usernames[:15])}"
            + (" ..." if len(usernames) > 15 else "")
        )
        await _activity_finish(activity_id, "done", result, scraper.LAST_SCREENSHOT_PATH)
        return result
    except Exception as exc:
        await _activity_finish(activity_id, "error", str(exc), scraper.LAST_SCREENSHOT_PATH)
        raise


@mcp.tool()
async def scan_account(username: str, max_results: int = 30) -> str:
    """
    Pull a specific account's recent posts and cache them. Call this for
    every account name that came out of search_format before running
    find_winning_accounts, since filtering needs each account's own history,
    not just the one post that surfaced it in search.
    """
    activity_id = await _activity_start("scan_account", {"username": username, "max_results": max_results})
    try:
        async with _scrape_lock:
            _, n = await _scan_and_cache(username, max_results=max_results)
        result = f"Cached {n} posts for @{username}."
        await _activity_finish(activity_id, "done", result, scraper.LAST_SCREENSHOT_PATH)
        return result
    except Exception as exc:
        await _activity_finish(activity_id, "error", str(exc), scraper.LAST_SCREENSHOT_PATH)
        raise


@mcp.tool()
async def run_playbook_scan(
    niche_keywords: list[str],
    min_total_views_30d: int = 100_000,
    min_posts_last_30d: int = 15,
    max_single_post_share: float = 0.7,
) -> dict[str, Any]:
    """Run the slideshow playbook's complete research pipeline.

    Search every niche keyword, scan every distinct account surfaced, apply
    the repeatability thresholds, and attach a top-post report to each passing
    account. All network calls run sequentially under the shared scrape lock.
    This is the default tool for an end-to-end Step 2–3 research run.
    """
    keywords = list(dict.fromkeys(keyword.strip() for keyword in niche_keywords if keyword.strip()))
    if not keywords:
        raise ValueError("Provide at least one non-empty niche keyword")
    if min_total_views_30d < 0 or min_posts_last_30d < 0:
        raise ValueError("View and post thresholds cannot be negative")
    if not 0 <= max_single_post_share <= 1:
        raise ValueError("max_single_post_share must be between 0 and 1")

    activity_id = await _activity_start("run_playbook_scan", {"niche_keywords": keywords})
    search_runs: list[dict[str, Any]] = []
    scan_runs: list[dict[str, Any]] = []
    candidates: set[str] = set()

    async with _scrape_lock:
        for keyword in keywords:
            try:
                posts, cached = await _search_and_cache(keyword)
                usernames = sorted({post.username for post in posts if post.username})
                candidates.update(usernames)
                search_runs.append(
                    {
                        "keyword": keyword,
                        "posts_found": len(posts),
                        "posts_cached": cached,
                        "usernames": usernames,
                    }
                )
            except Exception as exc:
                logger.exception("Playbook keyword search failed for %s", keyword)
                search_runs.append({"keyword": keyword, "error": str(exc)})

        for username in sorted(candidates):
            try:
                posts, cached = await _scan_and_cache(username)
                scan_runs.append(
                    {
                        "username": username,
                        "posts_found": len(posts),
                        "posts_cached": cached,
                    }
                )
            except Exception as exc:
                logger.exception("Playbook account scan failed for @%s", username)
                scan_runs.append({"username": username, "error": str(exc)})

    try:
        winners = _winning_accounts(
            candidates,
            min_total_views_30d=min_total_views_30d,
            min_posts_last_30d=min_posts_last_30d,
            max_single_post_share=max_single_post_share,
        )
        passed_accounts = [
            {"username": stats.username, **_report_payload(stats.username)}
            for stats in winners
        ]
        result = {
            "keywords": keywords,
            "thresholds": {
                "min_total_views_30d": min_total_views_30d,
                "min_posts_last_30d": min_posts_last_30d,
                "max_single_post_share": max_single_post_share,
            },
            "candidate_usernames": sorted(candidates),
            "search_runs": search_runs,
            "scan_runs": scan_runs,
            "passed_count": len(passed_accounts),
            "passed_accounts": passed_accounts,
        }
        await _activity_finish(activity_id, "done", f"{len(passed_accounts)} accounts passed from {len(candidates)} candidates")
        return result
    except Exception as exc:
        await _activity_finish(activity_id, "error", str(exc))
        raise


@mcp.tool()
async def find_winning_accounts(
    min_total_views_30d: int = 100_000,
    min_posts_last_30d: int = 15,
    max_single_post_share: float = 0.7,
) -> str:
    """
    Apply the playbook's Step-2 filter over every account currently in the
    cache (populated via search_format / scan_account) and return only the
    ones that pass: posts near-daily, 100k+ views/30d spread across posts
    rather than one viral fluke. This is the swipe-file shortlist.
    """
    activity_id = await _activity_start("find_winning_accounts", {"min_total_views_30d": min_total_views_30d, "min_posts_last_30d": min_posts_last_30d, "max_single_post_share": max_single_post_share})
    try:
        winners = _winning_accounts(_store.all_known_usernames(), min_total_views_30d=min_total_views_30d, min_posts_last_30d=min_posts_last_30d, max_single_post_share=max_single_post_share)
        if not winners:
            result = "No cached accounts currently pass the filters. Run search_format and scan_account for more accounts first, or loosen the thresholds."
        else:
            result = "\n".join(f"@{w.username} — {w.total_views_last_30d:,} views / {w.posts_last_30d} posts (last 30d), max single post {w.max_single_post_views:,} views ({w.max_single_post_views / max(w.total_views_last_30d, 1):.0%} of total)" for w in winners)
        await _activity_finish(activity_id, "done", result[:500])
        return result
    except Exception as exc:
        await _activity_finish(activity_id, "error", str(exc))
        raise


@mcp.tool()
async def account_report(username: str, top_n: int = 8) -> str:
    """
    Return an account's stats plus its top posts by view count, formatted
    for Step-3 analysis (hook / slide count / where value lands / why it
    gets saved). Feed this straight into the analysis conversation.
    """
    activity_id = await _activity_start("account_report", {"username": username, "top_n": top_n})
    try:
        report = _report_payload(username, top_n=top_n)
        stats = report["stats"]
        top = report["top_posts"]
        lines = [
            f"@{username} — {stats['posts_last_30d']} posts / {stats['total_views_last_30d']:,} "
            f"views in last 30d, avg {stats['avg_views_per_post']:,.0f} views/post",
            "",
            "Top posts:",
        ]
        for r in top:
            slide_tag = f"[slideshow, {r['image_count']} slides]" if r["is_slideshow"] else "[video]"
            lines.append(f"  {r['view_count']:,} views {slide_tag} — {r['caption'][:100]!r} — {r['url']}")
        result = "\n".join(lines)
        await _activity_finish(activity_id, "done", result[:500])
        return result
    except Exception as exc:
        await _activity_finish(activity_id, "error", str(exc))
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description="Comet MCP server")
    parser.add_argument(
        "--transport",
        choices=("stdio", "streamable-http"),
        default=os.environ.get("TIKTOK_SCOUT_MCP_TRANSPORT", "streamable-http"),
    )
    parser.add_argument("--host", default=os.environ.get("TIKTOK_SCOUT_MCP_HOST", "127.0.0.1"))
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("TIKTOK_SCOUT_MCP_PORT", "8765")),
    )
    args = parser.parse_args()
    mcp.settings.host = args.host
    mcp.settings.port = args.port
    try:
        if args.transport == "streamable-http":
            asyncio.run(_run_http())
        else:
            mcp.run(transport=args.transport)
    except KeyboardInterrupt:
        logger.info("MCP server stopped")


if __name__ == "__main__":
    main()
