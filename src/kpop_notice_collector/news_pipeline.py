from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .adapters.naver_news import NaverNewsAdapter
from .classifier import classify, news_rejection_reason
from .event_parser import parse_event_fields
from .models import Artist, Notice
from .schedule_compare import assess_schedule_change


def load_news_config(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _artist_aliases(artist: Artist, blocked: set[str]) -> list[str]:
    name_without_note = re.sub(r"\s*\([^)]*\)", "", artist.name).strip()
    parenthetical = re.findall(r"\(([^)]+)\)", artist.name)
    candidates = [name_without_note, *parenthetical, *artist.aliases]
    aliases: list[str] = []
    for value in candidates:
        value = value.strip()
        if not value or value.casefold() in blocked:
            continue
        if value.casefold() not in {x.casefold() for x in aliases}:
            aliases.append(value)
    return aliases


def choose_search_name(artist: Artist, config: dict) -> str:
    overrides = config.get("search_name_overrides", {})
    if artist.artist_id in overrides:
        return str(overrides[artist.artist_id])
    blocked = {x.casefold() for x in config.get("blocked_title_aliases", [])}
    aliases = _artist_aliases(artist, blocked)
    korean = next(
        (x for x in aliases if re.search(r"[가-힣]", x) and len(x) >= 3),
        "",
    )
    return korean or (aliases[0] if aliases else artist.name)


def _contains_alias(title: str, alias: str) -> bool:
    if re.search(r"[A-Za-z0-9]", alias):
        pattern = rf"(?<![A-Za-z0-9]){re.escape(alias)}(?![A-Za-z0-9])"
        return bool(re.search(pattern, title, re.I))
    return alias in title


def title_artist_alias(
    title: str, artist: Artist, config: dict
) -> str:
    blocked = {x.casefold() for x in config.get("blocked_title_aliases", [])}
    aliases = sorted(
        _artist_aliases(artist, blocked),
        key=lambda value: len(re.sub(r"\s+", "", value)),
        reverse=True,
    )
    return next((alias for alias in aliases if _contains_alias(title, alias)), "")


def _excluded_row(notice: Notice, reason: str) -> dict:
    return {
        "artist_id": notice.artist_id,
        "아티스트": notice.artist,
        "기사 제목": notice.title,
        "출처 URL": notice.url,
        "검색어": notice.search_query,
        "제외 사유": reason,
    }


def run_naver_news(
    artists: list[Artist],
    config: dict,
    *,
    history: list[dict],
    now: datetime | None = None,
    company: str | None = None,
    min_score: int | None = None,
    adapter: NaverNewsAdapter | None = None,
) -> tuple[list[Notice], list[dict], list[dict]]:
    tz = ZoneInfo("Asia/Seoul")
    now = now or datetime.now(tz)
    if now.tzinfo is None:
        now = now.replace(tzinfo=tz)
    hours = int(config.get("hours", 24))
    cutoff = now - timedelta(hours=hours)
    display = max(1, min(int(config.get("display", 100)), 100))
    max_pages = max(1, min(int(config.get("max_pages", 3)), 10))
    min_score = int(
        config.get("min_score", 40) if min_score is None else min_score
    )
    max_excluded = int(config.get("excluded_examples_per_reason", 20))
    adapter = adapter or NaverNewsAdapter(
        publisher_scores=config.get("publisher_scores", {}),
        default_publisher_score=int(config.get("default_publisher_score", 3)),
    )
    selected = [
        artist
        for artist in artists
        if not company or artist.company.upper() == company.upper()
    ]
    accepted: list[Notice] = []
    excluded: list[dict] = []
    excluded_counts: Counter[str] = Counter()
    run_log: list[dict] = []

    def exclude(notice: Notice, reason: str) -> None:
        excluded_counts[reason] += 1
        if excluded_counts[reason] <= max_excluded:
            excluded.append(_excluded_row(notice, reason))

    for index, artist in enumerate(selected, start=1):
        query = choose_search_name(artist, config)
        recent_rows: list[Notice] = []
        outside_window = 0
        missing_date = 0
        pages = 0
        error = ""
        seen_urls: set[str] = set()

        for page in range(max_pages):
            start = 1 + page * display
            try:
                rows = adapter.collect_query(
                    artist,
                    query,
                    now,
                    display=display,
                    start=start,
                    sort="date",
                )
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
                break
            pages += 1
            oldest: datetime | None = None
            for notice in rows:
                published = notice.published_at
                if published and published.tzinfo is None:
                    published = published.replace(tzinfo=tz)
                    notice.published_at = published
                if not published:
                    missing_date += 1
                    continue
                published_kst = published.astimezone(tz)
                oldest = min(oldest, published_kst) if oldest else published_kst
                if published_kst < cutoff:
                    outside_window += 1
                    continue
                if published_kst > now + timedelta(minutes=10):
                    continue
                canonical = (notice.original_url or notice.url).split("#", 1)[0]
                if canonical in seen_urls:
                    continue
                seen_urls.add(canonical)
                recent_rows.append(notice)
            if len(rows) < display or (oldest and oldest < cutoff):
                break

        accepted_before = len(accepted)
        for notice in recent_rows:
            matched_alias = title_artist_alias(notice.title, artist, config)
            if not matched_alias:
                exclude(notice, "제목에 정확한 아티스트명 없음")
                continue
            notice.matched_artist_alias = matched_alias
            classify(notice, title_only=True)
            reason = news_rejection_reason(notice)
            if reason:
                exclude(notice, reason)
                continue
            notice.score += notice.publisher_score + 15
            if notice.score < min_score:
                exclude(notice, "활동 분류/점수 기준 미달")
                continue
            parse_event_fields(notice)
            assess_schedule_change(notice, history)
            notice.validation_status = (
                "AUTO_SELECTED" if notice.event_dates else "REVIEW_REQUIRED"
            )
            accepted.append(notice)

        run_log.append(
            {
                "source_id": "naver_news",
                "artist_id": artist.artist_id,
                "artist": artist.name,
                "query": query,
                "api_calls": pages,
                "rows_received": len(recent_rows) + outside_window + missing_date,
                "recent_rows": len(recent_rows),
                "outside_24h": outside_window,
                "missing_pubdate": missing_date,
                "selected_before_clustering": len(accepted) - accepted_before,
                "error": error,
                "note": "",
            }
        )
        print(
            f"[{index:02d}/{len(selected):02d}] {artist.name}: "
            f"recent={len(recent_rows)}, selected={len(accepted) - accepted_before}, "
            f"outside_24h={outside_window}, calls={pages}"
        )

    deduped: dict[str, Notice] = {}
    for notice in sorted(
        accepted, key=lambda item: (item.score, item.published_at or now), reverse=True
    ):
        deduped.setdefault(notice.dedupe_key, notice)

    for reason, count in excluded_counts.items():
        run_log.append(
            {
                "source_id": "exclusion_summary",
                "artist_id": "",
                "artist": "",
                "query": "",
                "api_calls": 0,
                "rows_received": count,
                "recent_rows": count,
                "outside_24h": 0,
                "missing_pubdate": 0,
                "selected_before_clustering": 0,
                "error": "",
                "note": reason,
            }
        )
    return list(deduped.values()), excluded, run_log
