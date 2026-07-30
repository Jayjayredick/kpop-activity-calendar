from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .calendar_feed import add_months, build_calendar_feed, build_review_feed
from .config import load_activity_entities, load_artists, project_root
from .event_cluster import cluster_events
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
    result = argparse.ArgumentParser(description="향후 일정 최초 백필 v3.0")
    result.add_argument("--days-back", type=int, default=180)
    result.add_argument("--company", choices=["HYBE", "SM", "JYP", "YG"])
    result.add_argument("--min-score", type=int, default=None)
    result.add_argument(
        "--news-config",
        default=str(root / "config" / "news_queries.json"),
    )
    result.add_argument(
        "--history",
        default=str(root / "data" / "events_history.csv"),
    )
    result.add_argument(
        "--review-queue",
        default=str(root / "data" / "review_queue.csv"),
    )
    result.add_argument(
        "--review-log",
        default=str(root / "data" / "review_log.csv"),
    )
    result.add_argument(
        "--out",
        default=str(root / "output" / "backfill_review.xlsx"),
    )
    result.add_argument(
        "--calendar-json",
        default=str(root / "docs" / "calendar_events.json"),
    )
    result.add_argument(
        "--review-json",
        default=str(root / "docs" / "review_queue.json"),
    )
    result.add_argument("--publish-review-queue", action="store_true")
    result.add_argument("--no-date-enrichment", action="store_true")
    return result


def _within_calendar_window(
    event_dates: list[str],
    *,
    start: date,
    end: date,
) -> bool:
    if not event_dates:
        return True
    for raw in event_dates:
        try:
            value = date.fromisoformat(raw)
        except ValueError:
            continue
        if start <= value <= end:
            return True
    return False


def main() -> None:
    args = parser().parse_args()
    root = project_root()
    now = datetime.now(ZoneInfo("Asia/Seoul"))
    parent_artists = load_artists()
    activity_entities = load_activity_entities()
    artists = parent_artists + activity_entities
    history = load_event_history(args.history)
    config = load_news_config(args.news_config)
    config["hours"] = max(1, args.days_back) * 24
    config["priority_entity_ids"] = [
        artist.artist_id for artist in activity_entities
    ]
    news, excluded, run_log = run_naver_news(
        artists,
        config,
        history=history,
        now=now,
        company=args.company,
        min_score=args.min_score,
        mode="backfill",
    )
    selected = cluster_events(news)
    enrichment_log: list[dict] = []
    if not args.no_date_enrichment:
        enrichment_log = enrich_undated_events(
            selected,
            artists,
            config,
            now=now,
            max_items=int(config.get("backfill_date_enrichment_max_items", 80)),
        )
        run_log.extend(enrichment_log)

    site_config = json.loads(
        (root / "config" / "site.json").read_text(encoding="utf-8")
    )
    start = now.date() - timedelta(
        days=int(site_config.get("calendar_days_back", 14))
    )
    end = add_months(
        now.date(),
        int(site_config.get("calendar_months_forward", 3)),
    )
    queue_candidates = [
        notice
        for notice in selected
        if _within_calendar_window(
            notice.event_dates,
            start=start,
            end=end,
        )
    ]
    for notice in queue_candidates:
        notice.validation_status = "REVIEW_REQUIRED"
        notice.review_reason = (
            "BACKFILL_DATE_FOUND"
            if notice.event_dates
            else "BACKFILL_DATE_NOT_FOUND"
        )

    calendar_rows = history
    if args.publish_review_queue:
        review_rows = upsert_review_queue(
            args.review_queue,
            queue_candidates,
            now=now,
            review_log_path=args.review_log,
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
    else:
        review_rows = load_review_queue(args.review_queue)

    export_xlsx(
        args.out,
        queue_candidates,
        excluded,
        run_log,
        {
            "version": "3.0.0",
            "mode": "BACKFILL",
            "timezone": "Asia/Seoul",
            "days_back": args.days_back,
            "calendar_start": start.isoformat(),
            "calendar_end": end.isoformat(),
            "company": args.company or "ALL",
            "parent_artist_count": len(parent_artists),
            "solo_unit_entity_count": len(activity_entities),
            "search_entity_count": len(artists),
            "candidate_count": len(news),
            "clustered_count": len(selected),
            "review_queue_candidates": len(queue_candidates),
            "published_to_review_queue": args.publish_review_queue,
            "api_calls": sum(int(row.get("api_calls", 0)) for row in run_log),
        },
        calendar_rows=calendar_rows,
    )
    print(
        f"백필 완료: clustered={len(selected)}, "
        f"review_candidates={len(queue_candidates)}, "
        f"published={args.publish_review_queue}"
    )
    print(Path(args.out))


if __name__ == "__main__":
    main()
