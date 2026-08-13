"""JSON command-line bridge for the desktop application.

Every invocation writes exactly one JSON object to stdout. Diagnostics stay on
stderr so callers can always parse stdout, including when a command fails.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, NoReturn

from .models import AccountStats, Post
from .scraper import (
    DEFAULT_SESSION_PATH,
    create_login_session,
    get_user_posts,
    polite_delay,
    search_keyword,
)
from .storage import DEFAULT_DB_PATH, Store

logger = logging.getLogger(__name__)


class CLIError(Exception):
    """A user-correctable CLI invocation error."""


class JSONArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise CLIError(message)


def _json_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"Cannot serialize {type(value).__name__}")


def _emit(payload: dict[str, Any]) -> None:
    json.dump(payload, sys.stdout, default=_json_value, ensure_ascii=False)
    sys.stdout.write("\n")
    sys.stdout.flush()


def _post_dict(post: Post) -> dict[str, Any]:
    return asdict(post)


def _stats_dict(
    stats: AccountStats,
    *,
    min_total_views_30d: int = 100_000,
    min_posts_last_30d: int = 15,
    max_single_post_share: float = 0.7,
) -> dict[str, Any]:
    result = asdict(stats)
    result["max_single_post_share"] = (
        stats.max_single_post_views / stats.total_views_last_30d
        if stats.total_views_last_30d
        else 0.0
    )
    result["passes_filter"] = stats.passes_playbook_filters(
        min_total_views_30d=min_total_views_30d,
        min_posts_last_30d=min_posts_last_30d,
        max_single_post_share=max_single_post_share,
    )
    return result


def _store(path: str) -> Store:
    return Store(Path(path).expanduser())


def _validate_scrape_args(args: argparse.Namespace) -> None:
    if getattr(args, "max_results", 1) < 1:
        raise CLIError("max-results must be at least 1")
    if args.min_delay < 0 or args.max_delay < 0:
        raise CLIError("delay values cannot be negative")
    if args.max_delay < args.min_delay:
        raise CLIError("max-delay must be greater than or equal to min-delay")


async def _delay(args: argparse.Namespace) -> None:
    await polite_delay(args.min_delay, args.max_delay)


async def _run_scrape(args: argparse.Namespace) -> dict[str, Any]:
    _validate_scrape_args(args)
    if args.command in {"search-keyword", "search-format"}:
        posts = await search_keyword(
            args.keyword,
            max_results=args.max_results,
            session_path=args.session_path,
        )
    else:
        posts = await get_user_posts(
            args.username.lstrip("@"),
            max_results=args.max_results,
            session_path=args.session_path,
        )

    cached = None
    if args.command in {"search-format", "scan-account"}:
        store = _store(args.db_path)
        try:
            cached = store.upsert_posts(posts)
        finally:
            store.close()
    await _delay(args)
    return {
        "ok": True,
        "command": args.command,
        "cached": cached,
        "count": len(posts),
        "posts": [_post_dict(post) for post in posts],
    }


def _run_cache(args: argparse.Namespace) -> dict[str, Any]:
    store = _store(args.db_path)
    try:
        if args.command == "compute-account-stats":
            stats = store.compute_account_stats(args.username.lstrip("@"))
            return {"ok": True, "account": _stats_dict(stats)}
        if args.command == "list-accounts":
            accounts = [
                _stats_dict(store.compute_account_stats(username))
                for username in store.all_known_usernames()
            ]
            accounts.sort(
                key=lambda account: account["total_views_last_30d"], reverse=True
            )
            return {"ok": True, "accounts": accounts}
        if args.command == "find-winning-accounts":
            winners = []
            for username in store.all_known_usernames():
                stats = store.compute_account_stats(username)
                if stats.passes_playbook_filters(
                    min_total_views_30d=args.min_total_views_30d,
                    min_posts_last_30d=args.min_posts_last_30d,
                    max_single_post_share=args.max_single_post_share,
                ):
                    winners.append(
                        _stats_dict(
                            stats,
                            min_total_views_30d=args.min_total_views_30d,
                            min_posts_last_30d=args.min_posts_last_30d,
                            max_single_post_share=args.max_single_post_share,
                        )
                    )
            winners.sort(
                key=lambda account: account["total_views_last_30d"], reverse=True
            )
            return {"ok": True, "accounts": winners}

        username = args.username.lstrip("@")
        rows = [dict(row) for row in store.posts_for_username(username)]
        if args.command == "posts-for-username":
            return {"ok": True, "username": username, "posts": rows}
        stats = store.compute_account_stats(username)
        top = sorted(rows, key=lambda row: row.get("view_count") or 0, reverse=True)[
            : args.top_n
        ]
        return {
            "ok": True,
            "account": _stats_dict(stats),
            "top_posts": top,
        }
    finally:
        store.close()


def _add_scrape_options(parser: argparse.ArgumentParser, *, default_max: int) -> None:
    parser.add_argument("--max-results", type=int, default=default_max)
    parser.add_argument("--session-path", default=str(DEFAULT_SESSION_PATH))
    parser.add_argument("--min-delay", type=float, default=4.0)
    parser.add_argument("--max-delay", type=float, default=9.0)


def _add_db_option(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--db-path", default=str(DEFAULT_DB_PATH))


def _parser() -> JSONArgumentParser:
    parser = JSONArgumentParser(prog="python -m tiktok_scout.cli")
    commands = parser.add_subparsers(dest="command", required=True)

    for name in ("search-keyword", "search-format"):
        command = commands.add_parser(name)
        command.add_argument("keyword")
        _add_scrape_options(command, default_max=20)
        if name == "search-format":
            _add_db_option(command)

    for name in ("get-user-posts", "scan-account"):
        command = commands.add_parser(name)
        command.add_argument("username")
        _add_scrape_options(command, default_max=30)
        if name == "scan-account":
            _add_db_option(command)

    login = commands.add_parser("login-session")
    login.add_argument("--session-path", default=str(DEFAULT_SESSION_PATH))
    login.add_argument("--timeout", type=float, default=300.0)
    login.add_argument("--window-x", type=int)
    login.add_argument("--window-y", type=int)
    login.add_argument("--window-width", type=int)
    login.add_argument("--window-height", type=int)

    stats = commands.add_parser("compute-account-stats")
    stats.add_argument("username")
    _add_db_option(stats)

    posts = commands.add_parser("posts-for-username")
    posts.add_argument("username")
    _add_db_option(posts)

    accounts = commands.add_parser("list-accounts")
    _add_db_option(accounts)

    winners = commands.add_parser("find-winning-accounts")
    winners.add_argument("--min-total-views-30d", type=int, default=100_000)
    winners.add_argument("--min-posts-last-30d", type=int, default=15)
    winners.add_argument("--max-single-post-share", type=float, default=0.7)
    _add_db_option(winners)

    report = commands.add_parser("account-report")
    report.add_argument("username")
    report.add_argument("--top-n", type=int, default=8)
    _add_db_option(report)
    return parser


async def _dispatch(args: argparse.Namespace) -> dict[str, Any]:
    if args.command == "login-session":
        if args.timeout <= 0:
            raise CLIError("timeout must be greater than 0")
        position = (
            (args.window_x, args.window_y)
            if args.window_x is not None and args.window_y is not None
            else None
        )
        size = (
            (args.window_width, args.window_height)
            if args.window_width is not None and args.window_height is not None
            else None
        )
        result = await create_login_session(
            args.session_path,
            args.timeout,
            window_position=position,
            window_size=size,
        )
        return {"ok": True, **result}
    if args.command in {
        "search-keyword",
        "search-format",
        "get-user-posts",
        "scan-account",
    }:
        return await _run_scrape(args)
    return _run_cache(args)


def main(argv: list[str] | None = None) -> int:
    command = None
    try:
        args = _parser().parse_args(argv)
        command = args.command
        payload = asyncio.run(_dispatch(args))
        _emit(payload)
        return 0
    except KeyboardInterrupt:
        _emit({"ok": False, "error": "Command cancelled", "command": command})
        return 130
    except Exception as exc:
        logger.error("CLI command failed: %s", exc)
        _emit(
            {
                "ok": False,
                "error": str(exc) or type(exc).__name__,
                "command": command,
            }
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
