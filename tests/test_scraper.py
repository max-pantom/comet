import asyncio
import unittest
from unittest.mock import AsyncMock

from tiktok_scout.scraper import (
    _authenticated_cookie_names,
    _navigate_for_api_json,
)


class AuthCookieDetectionTests(unittest.TestCase):
    def test_accepts_current_tiktok_session_cookies(self) -> None:
        cookies = [{"name": "ttwid"}, {"name": "sid_tt"}]
        self.assertEqual(_authenticated_cookie_names(cookies), ["sid_tt"])

    def test_cookie_names_are_case_insensitive(self) -> None:
        self.assertEqual(
            _authenticated_cookie_names([{"name": "SESSIONID_SS"}]),
            ["sessionid_ss"],
        )

    def test_rejects_anonymous_cookie_set(self) -> None:
        cookies = [{"name": "ttwid"}, {"name": "tt_csrf_token"}]
        self.assertEqual(_authenticated_cookie_names(cookies), [])


class FakeResponse:
    def __init__(self, body: bytes):
        self.url = "https://www.tiktok.com/api/search/general/full/"
        self._body = body

    async def body(self) -> bytes:
        return self._body


class FakePage:
    def __init__(self) -> None:
        self.listeners = []
        self.goto = AsyncMock()
        self.locator = lambda _selector: None

    def on(self, event: str, listener) -> None:
        self.assert_event(event)
        self.listeners.append(listener)

    def remove_listener(self, event: str, listener) -> None:
        self.assert_event(event)
        self.listeners.remove(listener)

    @staticmethod
    def assert_event(event: str) -> None:
        if event != "response":
            raise AssertionError(f"unexpected event: {event}")


class SearchResponseTests(unittest.IsolatedAsyncioTestCase):
    async def test_ignores_empty_response_before_usable_retry(self) -> None:
        page = FakePage()

        async def emit_responses(*_args, **_kwargs) -> None:
            await asyncio.sleep(0)
            for listener in list(page.listeners):
                listener(FakeResponse(b""))
                listener(FakeResponse(b'{"status_code": 0, "data": []}'))

        page.goto.side_effect = emit_responses
        payload = await _navigate_for_api_json(
            page,
            "https://www.tiktok.com/search?q=meal%20prep",
            "/api/search/general/full/",
            label="search",
            timeout_s=1,
        )
        self.assertEqual(payload, {"status_code": 0, "data": []})
        self.assertEqual(page.listeners, [])


if __name__ == "__main__":
    unittest.main()
