"""Data models used across the scraper, storage, and MCP server."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class Post:
    """A single TikTok post (video or photo/slideshow)."""

    post_id: str
    username: str
    caption: str = ""
    create_time: datetime | None = None  # UTC
    view_count: int = 0
    like_count: int = 0
    comment_count: int = 0
    share_count: int = 0
    is_slideshow: bool = False
    image_count: int = 0  # >0 for slideshows
    url: str = ""
    bio_link: str = ""
    scraped_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_row(self) -> tuple:
        return (
            self.post_id,
            self.username,
            self.caption,
            self.create_time.isoformat() if self.create_time else None,
            self.view_count,
            self.like_count,
            self.comment_count,
            self.share_count,
            int(self.is_slideshow),
            self.image_count,
            self.url,
            self.scraped_at.isoformat(),
            self.bio_link,
        )


@dataclass
class AccountStats:
    """Aggregate stats for an account, computed from its recent posts."""

    username: str
    follower_count: int = 0
    posts_last_30d: int = 0
    total_views_last_30d: int = 0
    max_single_post_views: int = 0
    avg_views_per_post: float = 0.0
    days_active_last_30d: int = 0  # distinct days with >=1 post
    has_bio_link: bool = False  # rough proxy for "already has a product"

    # --- Step-2 filters from the playbook ---
    def passes_playbook_filters(
        self,
        min_total_views_30d: int = 100_000,
        max_single_post_share: float = 0.7,
        min_posts_last_30d: int = 15,  # ~daily-ish
    ) -> bool:
        """
        Mirrors the filters from the slideshow-distribution-app-growth skill:
        - active + repeatable (posts most days)
        - 100k+ views in the last 30 days, spread across posts (not one fluke)
        """
        if self.posts_last_30d < min_posts_last_30d:
            return False
        if self.total_views_last_30d < min_total_views_30d:
            return False
        if self.total_views_last_30d > 0:
            share = self.max_single_post_views / self.total_views_last_30d
            if share > max_single_post_share:
                return False  # one viral fluke, not a repeatable format
        return True
