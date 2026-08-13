"""
Unofficial TikTok scraper.

TikTok has no public API for keyword/account search, so this pulls data the
cheap way: load the public web pages with a real (headless) browser and read
the JSON TikTok embeds into the page itself for hydration, instead of
scraping the rendered HTML/DOM (which is far more brittle and changes often).

Two hydration blobs to look for, TikTok has used both over time:
  - <script id="SIGI_STATE" type="application/json">...</script>
  - <script id="__UNIVERSAL_DATA_FOR_REHYDRATION__" type="application/json">...</script>

This WILL break when TikTok changes their frontend build. When that happens,
re-run `find_hydration_key()` against a saved page to locate the new blob id,
or fall back to `--debug-dump` to inspect the raw HTML.

IMPORTANT — run this OUTSIDE of any sandboxed/allowlisted network. It needs
outbound access to www.tiktok.com, which most locked-down dev environments
(including the one this repo may have been scaffolded in) will not allow.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import re
import shutil
import socket
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

from playwright.async_api import (
    BrowserContext,
    Error as PlaywrightError,
    Page,
    TimeoutError as PlaywrightTimeoutError,
    async_playwright,
)

from .models import Post

logger = logging.getLogger(__name__)

HYDRATION_SCRIPT_IDS = ("__UNIVERSAL_DATA_FOR_REHYDRATION__", "SIGI_STATE")
DEFAULT_SESSION_PATH = Path(
    os.environ.get(
        "TIKTOK_SCOUT_SESSION_PATH",
        str(Path.home() / ".tiktok_scout" / "session.json"),
    )
).expanduser()
AUTH_COOKIE_NAMES = {"sessionid", "sessionid_ss", "sid_tt", "sid_guard"}
LAST_SCREENSHOT_PATH = ""


class ScrapeBlocked(Exception):
    """Raised when TikTok serves a captcha / login wall instead of data."""


def browser_channel() -> str:
    """Return the browser channel used for scraping and interactive login."""
    requested = os.environ.get("TIKTOK_SCOUT_BROWSER_CHANNEL", "auto").strip().lower()
    if requested and requested != "auto":
        return requested
    chrome_paths = (
        Path("/Applications/Google Chrome.app"),
        Path.home() / "Applications" / "Google Chrome.app",
    )
    if any(path.exists() for path in chrome_paths) or shutil.which("google-chrome"):
        return "chrome"
    return "chromium"


async def _launch_browser(playwright: Any, *, headless: bool) -> Any:
    channel = browser_channel()
    if channel == "chromium":
        return await playwright.chromium.launch(headless=headless)
    return await playwright.chromium.launch(channel=channel, headless=headless)


def _login_browser_executable(playwright: Any) -> str:
    """Prefer real Chrome, otherwise use Playwright's installed Chromium."""
    chrome_candidates = (
        Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
        Path.home()
        / "Applications"
        / "Google Chrome.app"
        / "Contents"
        / "MacOS"
        / "Google Chrome",
    )
    if browser_channel() == "chrome":
        for candidate in chrome_candidates:
            if candidate.is_file():
                return str(candidate)
        system_chrome = shutil.which("google-chrome")
        if system_chrome:
            return system_chrome
    return playwright.chromium.executable_path


def _desktop_user_agent(executable: str) -> str:
    """Build a normal desktop UA matching the installed browser binary."""
    version = "126.0.0.0"
    try:
        result = subprocess.run(
            [executable, "--version"],
            check=True,
            capture_output=True,
            text=True,
            timeout=3,
        )
        match = re.search(r"(\d+(?:\.\d+){3})", result.stdout)
        if match:
            version = match.group(1)
    except (OSError, subprocess.SubprocessError):
        logger.debug("Could not read browser version; using fallback UA", exc_info=True)
    return (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        f"Chrome/{version} Safari/537.36"
    )


async def _launch_login_browser(
    playwright: Any,
    profile_path: Path,
    *,
    window_position: tuple[int, int] | None = None,
    window_size: tuple[int, int] | None = None,
    headless: bool = False,
) -> tuple[Any, BrowserContext, asyncio.subprocess.Process]:
    """Start Chromium normally, then attach over local CDP to export state.

    Launching the executable ourselves avoids Playwright's automation launch
    flags, which TikTok's QR login can reject even when the phone approves it.
    """
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        debug_port = int(probe.getsockname()[1])

    launch_args = [
        f"--remote-debugging-port={debug_port}",
        "--remote-debugging-address=127.0.0.1",
        f"--user-data-dir={profile_path}",
        "--no-first-run",
        "--no-default-browser-check",
    ]
    if window_position is not None:
        launch_args.append(f"--window-position={window_position[0]},{window_position[1]}")
    if window_size is not None:
        launch_args.append(f"--window-size={window_size[0]},{window_size[1]}")
    if headless:
        launch_args.extend(("--headless", "--disable-gpu"))
    executable = _login_browser_executable(playwright)
    if headless:
        # TikTok returns a misleading HTTP 200 with an empty body when the
        # request advertises HeadlessChrome. Match the real installed build.
        launch_args.append(f"--user-agent={_desktop_user_agent(executable)}")
    process = await asyncio.create_subprocess_exec(
        executable,
        *launch_args,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    endpoint = f"http://127.0.0.1:{debug_port}"
    try:
        for _ in range(80):
            if process.returncode is not None:
                raise RuntimeError("The login browser exited before it was ready")
            try:
                browser = await playwright.chromium.connect_over_cdp(endpoint)
                if not browser.contexts:
                    raise RuntimeError("The login browser did not create a profile")
                return browser, browser.contexts[0], process
            except PlaywrightError:
                await asyncio.sleep(0.1)
        raise RuntimeError("Could not connect to the login browser")
    except Exception:
        if process.returncode is None:
            process.terminate()
            await process.wait()
        raise


async def _stop_login_browser(browser: Any, process: asyncio.subprocess.Process) -> None:
    try:
        await browser.close()
    except Exception:
        logger.debug("Could not detach from login browser", exc_info=True)
    if process.returncode is None:
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=3.0)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()


async def _new_stealthy_page(context: BrowserContext) -> Page:
    page = await context.new_page()
    # Basic bot-signal cleanup. Not bulletproof — pair with residential
    # proxies + real delays if you're scraping at any real volume.
    await page.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
    )
    return page


async def _goto_tiktok_dom(page: Page, url: str) -> None:
    """Navigate without waiting for TikTok's never-idle telemetry requests."""
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=45_000)
    except PlaywrightTimeoutError:
        # TikTok can keep the document request technically pending while the
        # useful DOM is already present. Continue only when a body really loaded.
        if await page.locator("body").count() == 0:
            raise
        logger.warning("TikTok navigation timed out after DOM became usable: %s", url)


async def _goto_tiktok_content(page: Page, url: str) -> None:
    await _goto_tiktok_dom(page, url)
    try:
        await page.wait_for_function(
            """ids => ids.some(id => document.getElementById(id))""",
            arg=list(HYDRATION_SCRIPT_IDS),
            timeout=12_000,
        )
    except PlaywrightTimeoutError:
        # _extract_hydration_json produces the useful captcha/schema error.
        logger.info("TikTok hydration script did not appear before parse: %s", url)


def _session_path(path: str | Path | None) -> Path:
    if path is None:
        return DEFAULT_SESSION_PATH
    return Path(path).expanduser()


def _authenticated_cookie_names(cookies: list[dict[str, Any]]) -> list[str]:
    """Return strong TikTok login-cookie names without exposing their values."""
    names = {str(cookie.get("name", "")).lower() for cookie in cookies}
    return sorted(names & AUTH_COOKIE_NAMES)


async def _new_context(browser: Any, session_path: str | Path | None) -> BrowserContext:
    version = browser.version
    options: dict[str, Any] = {
        "user_agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            f"Chrome/{version} Safari/537.36"
        )
    }
    state_path = _session_path(session_path)
    if state_path.is_file():
        options["storage_state"] = str(state_path)
    return await browser.new_context(**options)


async def _extract_hydration_json(page: Page) -> dict[str, Any]:
    for script_id in HYDRATION_SCRIPT_IDS:
        locator = page.locator(f"script#{script_id}")
        if await locator.count() > 0:
            raw = await locator.first.text_content()
            if raw:
                return json.loads(raw)
    body_text = await page.locator("body").first.text_content()
    if body_text and ("captcha" in body_text.lower() or "verify" in body_text.lower()):
        raise ScrapeBlocked("TikTok served a captcha/verification wall")
    raise ScrapeBlocked("Could not find a known hydration script on the page")


async def _capture_screenshot(page: Page, label: str, session_path: str | Path | None) -> str:
    global LAST_SCREENSHOT_PATH
    root = _session_path(session_path).parent / "screenshots"
    root.mkdir(parents=True, exist_ok=True)
    safe_label = "".join(character if character.isalnum() or character in "-_" else "_" for character in label)[:80]
    filename = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}-{safe_label}.png"
    destination = root / filename
    try:
        await page.screenshot(path=str(destination), full_page=True)
        LAST_SCREENSHOT_PATH = str(destination)
    except PlaywrightError:
        logger.debug("Could not capture TikTok screenshot", exc_info=True)
    return LAST_SCREENSHOT_PATH


def _walk_item_list(blob: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Hydration payload shape shifts between TikTok builds. Try the known
    paths for each, in order, and return the first that yields items.
    """
    candidates = [
        # __UNIVERSAL_DATA_FOR_REHYDRATION__ shape (search results)
        lambda b: b["__DEFAULT_SCOPE__"]["webapp.search-user"]["userList"],
        lambda b: b["__DEFAULT_SCOPE__"]["webapp.user-detail"]["itemList"],
        lambda b: b["__DEFAULT_SCOPE__"]["webapp.video-detail"]["itemList"],
        # SIGI_STATE shape
        lambda b: list(b["ItemModule"].values()),
        lambda b: list(b["UserModule"]["users"].values()),
    ]
    for extract in candidates:
        try:
            result = extract(blob)
            if result:
                return result
        except (KeyError, TypeError):
            continue
    return []


def _search_api_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract post objects from TikTok's current search JSON response."""
    items = []
    for result in payload.get("data") or []:
        if not isinstance(result, dict):
            continue
        item = result.get("item")
        if isinstance(item, dict) and item.get("id"):
            items.append(item)
    return items


async def _response_json(response: Any, *, label: str) -> dict[str, Any]:
    """Decode a TikTok API response and explain empty anti-bot responses."""
    raw = await response.body()
    if not raw:
        raise ScrapeBlocked(
            f"TikTok returned an empty {label} response. The session or IP may "
            "be temporarily restricted; open TikTok in the Session browser and "
            "confirm the page works, then try again more slowly."
        )
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ScrapeBlocked(f"TikTok returned invalid {label} data") from exc
    if not isinstance(payload, dict):
        raise ScrapeBlocked(f"TikTok returned an unexpected {label} response")
    return payload


async def _navigate_for_api_json(
    page: Page,
    url: str,
    endpoint_fragment: str,
    *,
    label: str,
    timeout_s: float = 35.0,
) -> dict[str, Any]:
    """Navigate and accept the first usable matching API response.

    TikTok can send an empty response for an initial request and retry the
    same endpoint moments later with the real payload. `expect_response`
    resolves too early in that case, so keep listening until valid JSON arrives.
    """
    responses: asyncio.Queue[Any] = asyncio.Queue()

    def capture(response: Any) -> None:
        if endpoint_fragment in response.url:
            responses.put_nowait(response)

    page.on("response", capture)
    last_blocked: ScrapeBlocked | None = None
    try:
        await _goto_tiktok_dom(page, url)
        deadline = asyncio.get_running_loop().time() + timeout_s
        while True:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                if last_blocked is not None:
                    raise last_blocked
                raise PlaywrightTimeoutError(
                    f"TikTok did not return {label} data within {int(timeout_s)} seconds"
                )
            try:
                response = await asyncio.wait_for(responses.get(), timeout=remaining)
            except asyncio.TimeoutError as exc:
                if last_blocked is not None:
                    raise last_blocked from exc
                raise PlaywrightTimeoutError(
                    f"TikTok did not return {label} data within {int(timeout_s)} seconds"
                ) from exc
            try:
                return await _response_json(response, label=label)
            except ScrapeBlocked as exc:
                last_blocked = exc
    finally:
        page.remove_listener("response", capture)


def _profile_api_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract post objects from TikTok's current profile-post response."""
    return [
        item
        for item in (payload.get("itemList") or [])
        if isinstance(item, dict) and item.get("id")
    ]


async def _persistent_scrape_context(
    playwright: Any, session_path: str | Path | None
) -> tuple[Any, BrowserContext, asyncio.subprocess.Process]:
    state_path = _session_path(session_path)
    profile_path = state_path.parent / "browser-profile"
    profile_path.mkdir(parents=True, exist_ok=True)
    return await _launch_login_browser(playwright, profile_path, headless=True)


def _post_from_item(item: dict[str, Any]) -> Post:
    stats = item.get("stats") or item.get("statsV2") or {}
    images = item.get("imagePost", {}).get("images", [])
    create_ts = item.get("createTime")
    return Post(
        post_id=str(item.get("id", "")),
        username=(item.get("author") or {}).get("uniqueId", ""),
        caption=item.get("desc", ""),
        create_time=(
            datetime.fromtimestamp(int(create_ts), tz=timezone.utc)
            if create_ts
            else None
        ),
        view_count=int(stats.get("playCount", 0) or 0),
        like_count=int(stats.get("diggCount", 0) or 0),
        comment_count=int(stats.get("commentCount", 0) or 0),
        share_count=int(stats.get("shareCount", 0) or 0),
        is_slideshow=bool(images),
        image_count=len(images),
        url=f"https://www.tiktok.com/@{(item.get('author') or {}).get('uniqueId', '')}/video/{item.get('id', '')}",
    )


async def search_keyword(
    keyword: str,
    max_results: int = 20,
    session_path: str | Path | None = None,
) -> list[Post]:
    """Search TikTok for a keyword and return whatever posts we can parse out."""
    global LAST_SCREENSHOT_PATH
    LAST_SCREENSHOT_PATH = ""
    async with async_playwright() as pw:
        browser, context, browser_process = await _persistent_scrape_context(
            pw, session_path
        )
        page = context.pages[0] if context.pages else await context.new_page()
        try:
            url = f"https://www.tiktok.com/search?q={quote(keyword)}"
            try:
                items = _search_api_items(
                    await _navigate_for_api_json(
                        page,
                        url,
                        "/api/search/general/full/",
                        label="search",
                    )
                )
            except ScrapeBlocked:
                await _capture_screenshot(page, f"search-{keyword}-blocked", session_path)
                raise
            except (PlaywrightTimeoutError, PlaywrightError, ValueError):
                logger.info("Falling back to embedded TikTok search data", exc_info=True)
                await _goto_tiktok_content(page, url)
                blob = await _extract_hydration_json(page)
                items = _walk_item_list(blob)
            posts = [_post_from_item(i) for i in items[:max_results] if i.get("id")]
            await _capture_screenshot(page, f"search-{keyword}", session_path)
            return posts
        finally:
            await _stop_login_browser(browser, browser_process)


async def get_user_posts(
    username: str,
    max_results: int = 30,
    session_path: str | Path | None = None,
) -> list[Post]:
    """Load a user's public profile and return their recent posts."""
    global LAST_SCREENSHOT_PATH
    LAST_SCREENSHOT_PATH = ""
    async with async_playwright() as pw:
        browser, context, browser_process = await _persistent_scrape_context(
            pw, session_path
        )
        page = context.pages[0] if context.pages else await context.new_page()
        try:
            url = f"https://www.tiktok.com/@{username}"
            try:
                items = _profile_api_items(
                    await _navigate_for_api_json(
                        page,
                        url,
                        "/api/post/item_list/",
                        label="profile",
                    )
                )
            except ScrapeBlocked:
                await _capture_screenshot(page, f"account-{username}-blocked", session_path)
                raise
            except (PlaywrightTimeoutError, PlaywrightError, ValueError):
                logger.info("Falling back to embedded TikTok profile data", exc_info=True)
                await _goto_tiktok_content(page, url)
                blob = await _extract_hydration_json(page)
                items = _walk_item_list(blob)
            posts = [_post_from_item(i) for i in items[:max_results] if i.get("id")]
            await _capture_screenshot(page, f"account-{username}", session_path)
            return posts
        finally:
            await _stop_login_browser(browser, browser_process)


async def create_login_session(
    session_path: str | Path | None = None,
    timeout_s: float = 300.0,
    *,
    window_position: tuple[int, int] | None = None,
    window_size: tuple[int, int] | None = None,
) -> dict[str, Any]:
    """Open TikTok in a visible browser and save storage state after login."""
    state_path = _session_path(session_path)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path = state_path.parent / "browser-profile"
    profile_path.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as pw:
        browser, context, browser_process = await _launch_login_browser(
            pw,
            profile_path,
            window_position=window_position,
            window_size=window_size,
        )
        page = context.pages[0] if context.pages else await _new_stealthy_page(context)
        last_cookie_names: list[str] = []
        last_url = "https://www.tiktok.com/login"
        try:
            await page.goto(
                "https://www.tiktok.com/login",
                wait_until="domcontentloaded",
                timeout=30_000,
            )
            deadline = asyncio.get_running_loop().time() + timeout_s
            while asyncio.get_running_loop().time() < deadline:
                try:
                    cookies = await context.cookies()
                    last_cookie_names = sorted(
                        str(cookie.get("name", "")) for cookie in cookies
                    )
                    authenticated = _authenticated_cookie_names(cookies)
                    active_pages = [candidate for candidate in context.pages if not candidate.is_closed()]
                    if active_pages:
                        last_url = active_pages[-1].url
                except PlaywrightError as exc:
                    raise RuntimeError(
                        "The login browser was closed before TikTok sign-in was detected. "
                        "Leave it open until the app confirms that the session was saved."
                    ) from exc
                if authenticated:
                    # TikTok writes several cookies during QR login. Give the final
                    # redirect a moment to settle before exporting the full state.
                    await asyncio.sleep(1.0)
                    await context.storage_state(path=str(state_path))
                    return {
                        "saved": True,
                        "session_path": str(state_path),
                        "profile_path": str(profile_path),
                        "browser_channel": browser_channel(),
                        "auth_cookies": authenticated,
                    }
                await asyncio.sleep(1.0)
            seen = ", ".join(last_cookie_names) if last_cookie_names else "none"
            raise TimeoutError(
                f"TikTok login was not detected within {int(timeout_s)} seconds. "
                f"Last page: {last_url}. Cookie names seen: {seen}. "
                "Leave the TikTok window open after approving the QR login."
            )
        finally:
            await _stop_login_browser(browser, browser_process)


async def polite_delay(min_s: float = 4.0, max_s: float = 9.0) -> None:
    """
    Call this between scrape calls. This is the single most important knob
    for staying cheap: no proxies means your IP eats every rate-limit/ban
    decision TikTok makes, so slow, human-shaped pacing is what keeps this
    usable at $0 infra cost instead of forcing you into residential proxies.
    """
    await asyncio.sleep(random.uniform(min_s, max_s))
