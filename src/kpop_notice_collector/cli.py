from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

from .config import load_activity_entities, load_artists, project_root
from .calendar_feed import build_calendar_feed, build_review_feed
from .event_cluster import cluster_events
from .event_store import append_daily_rows, upsert_event_history
from .exporter import export_xlsx
from .news_pipeline import (
    enrich_undated_events,
    load_news_config,
    run_naver_news,
)
from .review_store import load_review_queue, upsert_review_queue
from .schedule_compare import load_event_history


def parser() -> argparse.ArgumentParser:
    root = project_root()
    p = argparse.ArgumentParser(description="4사 K-pop NAVER 뉴스 활동 추적기 v3.0")
    p.add_argument("--hours", type=int, default=24)
    p.add_argument("--company", choices=["HYBE", "SM", "JYP", "YG"])
    p.add_argument("--min-score", type=int, default=None)
    p.add_argument("--artists", default=None)
    p.add_argument(
        "--activity-entities",
        default=str(root / "config" / "activity_entities.json"),
    )
    p.add_argument("--news-config", default=str(root / "config" / "news_queries.json"))
    p.add_argument("--history", default=str(root / "data" / "events_history.csv"))
    p.add_argument("--daily-history", default=str(root / "data" / "daily_collected.csv"))
    p.add_argument(
        "--review-queue",
        default=str(root / "data" / "review_queue.csv"),
    )
    p.add_argument(
        "--review-log",
        default=str(root / "data" / "review_log.csv"),
    )
    p.add_argument("--out", default=str(root / "output" / "latest_activity_tracker.xlsx"))
    p.add_argument(
        "--calendar-json",
        default=str(root / "docs" / "calendar_events.json"),
    )
    p.add_argument(
        "--review-json",
        default=str(root / "docs" / "review_queue.json"),
    )
    p.add_argument("--no-date-enrichment", action="store_true")
    p.add_argument("--no-persist", action="store_true")
    return p


def main() -> None:
    args = parser().parse_args()
    root = project_root()
    if load_dotenv:
        load_dotenv(root / ".env")
    now = datetime.now(ZoneInfo("Asia/Seoul"))
    parent_artists = load_artists(args.artists)
    activity_entities = load_activity_entities(args.activity_entities)
    artists = parent_artists + activity_entities
    history = load_event_history(args.history)
    news_config = load_news_config(args.news_config)
    news_config["hours"] = args.hours
    news_config["priority_entity_ids"] = [
        artist.artist_id for artist in activity_entities
    ]
    news, excluded_news, news_log = run_naver_news(
        artists,
        news_config,
        history=history,
        now=now,
        company=args.company,
        min_score=args.min_score,
    )
    selected = cluster_events(news)
    enrichment_log = []
    if not args.no_date_enrichment:
        enrichment_log = enrich_undated_events(
            selected,
            artists,
            news_config,
            now=now,
        )
        news_log.extend(enrichment_log)
    auto_confirmed = [
        notice
        for notice in selected
        if notice.validation_status == "AUTO_SELECTED" and notice.event_dates
    ]
    pending = [
        notice for notice in selected if notice not in auto_confirmed
    ]
    site_config = json.loads(
        (root / "config" / "site.json").read_text(encoding="utf-8")
    )

    if args.no_persist:
        calendar_rows = history
        review_rows = load_review_queue(args.review_queue)
    else:
        calendar_rows = upsert_event_history(
            args.history,
            auto_confirmed,
            now=now,
        )
        review_rows = upsert_review_queue(
            args.review_queue,
            pending,
            now=now,
            review_log_path=args.review_log,
        )
        append_daily_rows(args.daily_history, selected)

    export_xlsx(
        args.out,
        selected,
        excluded_news,
        news_log,
        {
            "version": "3.0.0",
            "timezone": "Asia/Seoul",
            "hours": args.hours,
            "company": args.company or "ALL",
            "min_score": args.min_score or news_config.get("min_score", 40),
            "run_at": now.isoformat(),
            "parent_artist_count": len(parent_artists),
            "solo_unit_entity_count": len(activity_entities),
            "search_entity_count": len(artists),
            "search_mode": "NAVER_NEWS_ONLY",
            "naver_candidates": len(news),
            "selected_count": len(selected),
            "auto_confirmed_count": len(auto_confirmed),
            "review_pending_count": len(pending),
            "date_enrichment_calls": sum(
                int(row.get("api_calls", 0)) for row in enrichment_log
            ),
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
        months=int(site_config.get("calendar_months_forward", 3)),
        days_back=int(site_config.get("calendar_days_back", 14)),
        review_rows=review_rows,
        repository=str(site_config.get("repository", "")),
    )
    build_review_feed(
        review_rows,
        args.review_json,
        now=now,
        repository=str(site_config.get("repository", "")),
    )
    errors = sum(
        bool(row.get("error"))
        for row in news_log
        if row.get("source_id") == "naver_news"
    )
    print(
        f"완료: candidates={len(news)}, clustered={len(selected)}, "
        f"auto_confirmed={len(auto_confirmed)}, pending={len(pending)}, "
        f"api_errors={errors}"
    )
    print(Path(args.out))
    print(Path(args.calendar_json))
    print(Path(args.review_json))


if __name__ == "__main__":
    main()
