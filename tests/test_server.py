import unittest
from dataclasses import dataclass
from unittest.mock import AsyncMock, patch

from tiktok_scout import server


@dataclass
class FakePost:
    username: str


@dataclass
class FakeStats:
    username: str
    total_views_last_30d: int = 200_000
    posts_last_30d: int = 20
    max_single_post_views: int = 40_000
    avg_views_per_post: float = 10_000
    days_active_last_30d: int = 20
    follower_count: int = 0
    has_bio_link: bool = False


class PlaybookTests(unittest.IsolatedAsyncioTestCase):
    async def test_composite_run_is_sequential_and_returns_reports(self) -> None:
        calls: list[str] = []

        async def search(keyword: str, max_results: int = 20):
            calls.append(f"search:{keyword}")
            users = [FakePost("alice"), FakePost("bob")]
            return users, len(users)

        async def scan(username: str, max_results: int = 30):
            calls.append(f"scan:{username}")
            return [FakePost(username)], 1

        with (
            patch.object(server, "_search_and_cache", side_effect=search),
            patch.object(server, "_scan_and_cache", side_effect=scan),
            patch.object(server, "_winning_accounts", return_value=[FakeStats("alice")]),
            patch.object(
                server,
                "_report_payload",
                return_value={"stats": {"username": "alice"}, "top_posts": []},
            ),
        ):
            result = await server.run_playbook_scan(["meal prep", "meal prep"])

        self.assertEqual(calls, ["search:meal prep", "scan:alice", "scan:bob"])
        self.assertEqual(result["candidate_usernames"], ["alice", "bob"])
        self.assertEqual(result["passed_count"], 1)
        self.assertEqual(result["passed_accounts"][0]["username"], "alice")

    def test_bundled_playbook_is_available(self) -> None:
        text = server.slideshow_distribution_playbook()
        self.assertIn("format first → app second → distribution engine third", text)
        self.assertIn("run_playbook_scan", server.apply_slideshow_distribution_playbook())


if __name__ == "__main__":
    unittest.main()
