from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

from .config import load_artists, project_root
from .calendar_feed import build_calendar_feed
from .event_cluster import cluster_events
from .event_store import append_daily_rows, upsert_event_history
from .exporter import export_xlsx
from .news_pipeline import load_news_config, run_naver_news
from .schedule_compare import load_event_history


def parser() -> argparse.ArgumentParser:
    root = project_root()
    p = argparse.ArgumentParser(description="4사 59팀 NAVER 뉴스 활동 추적기 v2.2")
    p.add_argument("--hours", type=int, default=24)
    p.add_argument("--company", choices=["HYBE", "SM", "JYP", "YG"])
    p.add_argument("--min-score", type=int, default=None)
    p.add_argument("--artists", default=None)
    p.add_argument("--news-config", default=str(root / "config" / "news_queries.json"))
    p.add_argument("--history", default=str(root / "data" / "events_history.csv"))
    p.add_argument("--daily-history", default=str(root / "data" / "daily_collected.csv"))
    p.add_argument("--out", default=str(root / "output" / "latest_activity_tracker.xlsx"))
    p.add_argument(
        "--calendar-json",
        default=str(root / "docs" / "calendar_events.json"),
    )
    p.add_argument("--no-persist", action="store_true")
    return p


def main() -> None:
    args = parser().parse_args()
    root = project_root()
    if load_dotenv:
        load_dotenv(root / ".env")
    now = datetime.now(ZoneInfo("Asia/Seoul"))
    artists = load_artists(args.artists)
    history = load_event_history(args.history)
    news_config = load_news_config(args.news_config)
    news_config["hours"] = args.hours
    news, excluded_news, news_log = run_naver_news(
        artists,
        news_config,
        history=history,
        now=now,
        company=args.company,
        min_score=args.min_score,
    )
    selected = cluster_events(news)

    if args.no_persist:
        calendar_rows = history
    else:
        calendar_rows = upsert_event_history(args.history, selected, now=now)
        append_daily_rows(args.daily_history, selected)

    export_xlsx(
        args.out,
        selected,
        excluded_news,
        news_log,
        {
            "version": "2.2.0",
            "timezone": "Asia/Seoul",
            "hours": args.hours,
            "company": args.company or "ALL",
            "min_score": args.min_score or news_config.get("min_score", 40),
            "run_at": now.isoformat(),
            "artist_count": len(artists),
            "search_mode": "NAVER_NEWS_ONLY",
            "naver_candidates": len(news),
            "selected_count": len(selected),
            "api_calls": sum(int(row.get("api_calls", 0)) for row in news_log),
            "outside_24h_not_exported": sum(
                int(row.get("outside_24h", 0)) for row in news_log
            ),
        },
        calendar_rows=calendar_rows,
    )
    build_calendar_feed(
        calendar_rows,
        args.calendar_json,
        now=now,
        months=3,
    )
    errors = sum(
        bool(row.get("error"))
        for row in news_log
        if row.get("source_id") == "naver_news"
    )
    print(
        f"완료: candidates={len(news)}, clustered={len(selected)}, "
        f"api_errors={errors}"
    )
    print(Path(args.out))
    print(Path(args.calendar_json))


if __name__ == "__main__":
    main()
