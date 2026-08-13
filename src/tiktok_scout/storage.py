"""SQLite cache for scraped posts. Keeps scraping cheap by avoiding repeat hits."""

from __future__ import annotations

import sqlite3
import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .models import AccountStats, Post

DEFAULT_DB_PATH = Path.home() / ".tiktok_scout" / "cache.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS posts (
    post_id TEXT PRIMARY KEY,
    username TEXT NOT NULL,
    caption TEXT,
    create_time TEXT,
    view_count INTEGER,
    like_count INTEGER,
    comment_count INTEGER,
    share_count INTEGER,
    is_slideshow INTEGER,
    image_count INTEGER,
    url TEXT,
    scraped_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_posts_username ON posts(username);
CREATE TABLE IF NOT EXISTS activity_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tool_name TEXT NOT NULL,
    args TEXT NOT NULL DEFAULT '{}',
    reason TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL,
    result_summary TEXT NOT NULL DEFAULT '',
    screenshot_path TEXT NOT NULL DEFAULT '',
    started_at TEXT NOT NULL,
    finished_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_activity_started_at ON activity_log(started_at DESC);
"""


class Store:
    def __init__(self, db_path: Path = DEFAULT_DB_PATH):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def upsert_posts(self, posts: list[Post]) -> int:
        rows = [p.to_row() for p in posts]
        self.conn.executemany(
            """
            INSERT INTO posts (post_id, username, caption, create_time, view_count,
                like_count, comment_count, share_count, is_slideshow, image_count,
                url, scraped_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(post_id) DO UPDATE SET
                view_count=excluded.view_count,
                like_count=excluded.like_count,
                comment_count=excluded.comment_count,
                share_count=excluded.share_count,
                scraped_at=excluded.scraped_at
            """,
            rows,
        )
        self.conn.commit()
        return len(rows)

    def activity_start(self, tool_name: str, args: dict, reason: str = "") -> int:
        now = datetime.now(timezone.utc).isoformat()
        cursor = self.conn.execute(
            """INSERT INTO activity_log
               (tool_name, args, reason, status, started_at)
               VALUES (?, ?, ?, 'running', ?)""",
            (tool_name, json.dumps(args, ensure_ascii=False), reason, now),
        )
        self.conn.commit()
        return int(cursor.lastrowid)

    def activity_finish(
        self,
        activity_id: int,
        status: str,
        result_summary: str = "",
        screenshot_path: str = "",
    ) -> None:
        self.conn.execute(
            """UPDATE activity_log SET status=?, result_summary=?,
               screenshot_path=?, finished_at=? WHERE id=?""",
            (
                status,
                result_summary,
                screenshot_path,
                datetime.now(timezone.utc).isoformat(),
                activity_id,
            ),
        )
        self.conn.commit()

    def recent_activity(self, limit: int = 100) -> list[sqlite3.Row]:
        self.conn.row_factory = sqlite3.Row
        return self.conn.execute(
            "SELECT * FROM activity_log ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()

    def posts_for_username(self, username: str) -> list[sqlite3.Row]:
        self.conn.row_factory = sqlite3.Row
        cur = self.conn.execute(
            "SELECT * FROM posts WHERE username = ? ORDER BY create_time DESC",
            (username,),
        )
        return cur.fetchall()

    def compute_account_stats(self, username: str, window_days: int = 30) -> AccountStats:
        rows = self.posts_for_username(username)
        cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
        recent = [
            r
            for r in rows
            if r["create_time"] and datetime.fromisoformat(r["create_time"]) >= cutoff
        ]
        total_views = sum(r["view_count"] or 0 for r in recent)
        max_views = max((r["view_count"] or 0 for r in recent), default=0)
        days_active = len(
            {datetime.fromisoformat(r["create_time"]).date() for r in recent}
        )
        return AccountStats(
            username=username,
            posts_last_30d=len(recent),
            total_views_last_30d=total_views,
            max_single_post_views=max_views,
            avg_views_per_post=(total_views / len(recent)) if recent else 0.0,
            days_active_last_30d=days_active,
        )

    def all_known_usernames(self) -> list[str]:
        cur = self.conn.execute("SELECT DISTINCT username FROM posts")
        return [r[0] for r in cur.fetchall()]

    def close(self) -> None:
        self.conn.close()
