from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from pathlib import Path
from zoneinfo import ZoneInfo

from .adapters.naver_news import NaverNewsAdapter
from .classifier import classify, news_rejection_reason
from .event_parser import parse_event_fields
from .models import Artist, Notice, canonicalize_url
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


def resolve_title_artist(
    title: str,
    default_artist: Artist,
    artists: list[Artist],
    config: dict,
) -> tuple[Artist | None, str]:
    """그룹명과 멤버명이 함께 있으면 등록된 솔로·유닛을 우선한다."""
    priority_ids = set(config.get("priority_entity_ids", []))
    candidates = sorted(
        artists,
        key=lambda artist: (
            artist.artist_id not in priority_ids,
            -max(
                [
                    len(re.sub(r"\s+", "", alias))
                    for alias in _artist_aliases(
                        artist,
                        {x.casefold() for x in config.get("blocked_title_aliases", [])},
                    )
                ]
                or [0]
            ),
        ),
    )
    for artist in candidates:
        alias = title_artist_alias(title, artist, config)
        if alias:
            return artist, alias
    alias = title_artist_alias(title, default_artist, config)
    return (default_artist, alias) if alias else (None, "")


def _queries_for_artist(artist: Artist, config: dict, *, backfill: bool) -> list[str]:
    base = choose_search_name(artist, config)
    suffixes = config.get("backfill_query_suffixes", []) if backfill else []
    if not suffixes:
        return [base]
    return [f"{base} {suffix}".strip() for suffix in suffixes]


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
    mode: str = "daily",
) -> tuple[list[Notice], list[dict], list[dict]]:
    tz = ZoneInfo("Asia/Seoul")
    now = now or datetime.now(tz)
    if now.tzinfo is None:
        now = now.replace(tzinfo=tz)
    hours = int(config.get("hours", 24))
    cutoff = now - timedelta(hours=hours)
    display = max(1, min(int(config.get("display", 100)), 100))
    max_pages = max(1, min(int(config.get("max_pages", 3)), 10))
    if mode == "backfill":
        max_pages = max(
            1,
            min(int(config.get("backfill_max_pages", max_pages)), 10),
        )
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

    backfill = mode == "backfill"
    auto_publish_min_score = int(config.get("auto_publish_min_score", 65))
    auto_publish_enabled = bool(config.get("auto_publish_enabled", False))

    for index, artist in enumerate(selected, start=1):
        queries = _queries_for_artist(artist, config, backfill=backfill)
        recent_rows: list[Notice] = []
        outside_window = 0
        missing_date = 0
        pages = 0
        error = ""
        seen_urls: set[str] = set()

        for query in queries:
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
                    canonical = canonicalize_url(
                        notice.original_url or notice.url
                    )
                    if canonical in seen_urls:
                        continue
                    seen_urls.add(canonical)
                    recent_rows.append(notice)
                if len(rows) < display or (oldest and oldest < cutoff):
                    break
            if error:
                break

        accepted_before = len(accepted)
        for notice in recent_rows:
            matched_artist, matched_alias = resolve_title_artist(
                notice.title, artist, selected, config
            )
            if not matched_artist:
                exclude(notice, "제목에 정확한 아티스트명 없음")
                continue
            notice.artist_id = matched_artist.artist_id
            notice.artist = matched_artist.name
            notice.company = matched_artist.company
            notice.label = matched_artist.label
            notice.matched_artist_alias = matched_alias
            classify(notice, title_only=True)
            reason = news_rejection_reason(notice, backfill=backfill)
            if reason:
                exclude(notice, reason)
                continue
            notice.score += notice.publisher_score + 15
            if notice.score < min_score:
                exclude(notice, "활동 분류/점수 기준 미달")
                continue
            parse_event_fields(notice)
            assess_schedule_change(notice, history)
            if backfill:
                notice.validation_status = "REVIEW_REQUIRED"
                notice.review_reason = "BACKFILL_CANDIDATE"
            elif (
                auto_publish_enabled
                and notice.event_dates
                and notice.date_confidence == "HIGH"
                and notice.date_source == "TITLE"
                and not notice.date_conflict
                and notice.score >= auto_publish_min_score
            ):
                notice.validation_status = "AUTO_SELECTED"
            else:
                notice.validation_status = "REVIEW_REQUIRED"
                if notice.date_conflict:
                    notice.review_reason = "DATE_CONFLICT"
                elif not notice.event_dates:
                    notice.review_reason = "DATE_NOT_FOUND"
                elif notice.date_confidence != "HIGH":
                    notice.review_reason = "DATE_LOW_CONFIDENCE"
                else:
                    notice.review_reason = "MANUAL_APPROVAL_REQUIRED"
            accepted.append(notice)

        run_log.append(
            {
                "source_id": "naver_news",
                "artist_id": artist.artist_id,
                "artist": artist.name,
                "query": " | ".join(queries),
                "api_calls": pages,
                "rows_received": len(recent_rows) + outside_window + missing_date,
                "recent_rows": len(recent_rows),
                "outside_24h": outside_window,
                "outside_window": outside_window,
                "missing_pubdate": missing_date,
                "selected_before_clustering": len(accepted) - accepted_before,
                "error": error,
                "note": "",
                "mode": mode,
            }
        )
        print(
            f"[{index:02d}/{len(selected):02d}] {artist.name}: "
            f"recent={len(recent_rows)}, selected={len(accepted) - accepted_before}, "
            f"outside_window={outside_window}, calls={pages}"
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
                "outside_window": 0,
                "missing_pubdate": 0,
                "selected_before_clustering": 0,
                "error": "",
                "note": reason,
                "mode": mode,
            }
        )
    return list(deduped.values()), excluded, run_log


def enrich_undated_events(
    notices: list[Notice],
    artists: list[Artist],
    config: dict,
    *,
    now: datetime,
    adapter: NaverNewsAdapter | None = None,
    max_items: int | None = None,
) -> list[dict]:
    """날짜가 없는 행사만 행사명+날짜 검색으로 한 차례 보강한다."""
    adapter = adapter or NaverNewsAdapter(
        publisher_scores=config.get("publisher_scores", {}),
        default_publisher_score=int(config.get("default_publisher_score", 3)),
    )
    by_id = {artist.artist_id: artist for artist in artists}
    limit = int(
        max_items
        if max_items is not None
        else config.get("date_enrichment_max_items", 20)
    )
    display = max(
        1,
        min(int(config.get("date_enrichment_display", 30)), 100),
    )
    logs: list[dict] = []
    candidates = [
        notice
        for notice in notices
        if not notice.event_dates and not notice.date_conflict
    ][:limit]

    def event_anchor(value: str) -> str:
        value = re.sub(
            r"\b(?:컴백|신보|앨범|발매|개최|발표|공식|투어|콘서트|"
            r"팬미팅|팬콘서트|팝업스토어)\b",
            " ",
            value.lower(),
        )
        return re.sub(r"[^0-9a-z가-힣♥]+", "", value)

    def same_event_name(left: str, right: str) -> bool:
        left_anchor, right_anchor = event_anchor(left), event_anchor(right)
        if len(left_anchor) < 4 or len(right_anchor) < 4:
            return False
        if left_anchor == right_anchor:
            return True
        return SequenceMatcher(None, left_anchor, right_anchor).ratio() >= 0.82

    for notice in candidates:
        artist = by_id.get(notice.artist_id)
        if not artist:
            continue
        anchor = re.sub(r"\s+", " ", notice.event_name or "").strip()
        if not anchor or anchor.casefold() == notice.artist.casefold():
            continue
        date_word = "발매일" if notice.activity_type == "COMEBACK" else "일정"
        query = f"{choose_search_name(artist, config)} {anchor[:80]} {date_word}"
        found: list[Notice] = []
        error = ""
        try:
            rows = adapter.collect_query(
                artist,
                query,
                now,
                display=display,
                start=1,
                sort="date",
            )
        except Exception as exc:
            rows = []
            error = f"{type(exc).__name__}: {exc}"

        for row in rows:
            matched_artist, matched_alias = resolve_title_artist(
                row.title, artist, artists, config
            )
            if not matched_artist or matched_artist.artist_id != notice.artist_id:
                continue
            row.matched_artist_alias = matched_alias
            row.activity_type = notice.activity_type
            parse_event_fields(row)
            if (
                row.event_dates
                and not row.date_conflict
                and row.date_confidence in {"HIGH", "MEDIUM"}
                and same_event_name(notice.event_name, row.event_name)
            ):
                found.append(row)

        if found:
            by_range: dict[tuple[str, str], list[Notice]] = {}
            for row in found:
                key = (
                    row.event_start_date,
                    row.event_end_date or row.event_start_date,
                )
                by_range.setdefault(key, []).append(row)
            ranked = sorted(
                by_range.items(),
                key=lambda item: (
                    len(item[1]),
                    max(row.score for row in item[1]),
                ),
                reverse=True,
            )
            winner_key, winner_rows = ranked[0]
            tied = (
                len(ranked) > 1
                and len(ranked[0][1]) == len(ranked[1][1])
                and ranked[0][0] != ranked[1][0]
            )
            if tied:
                notice.date_conflict = True
                notice.date_confidence = "CONFLICT"
                notice.review_reason = "DATE_ENRICHMENT_CONFLICT"
                winner_rows = []
            else:
                best = max(
                    winner_rows,
                    key=lambda row: (
                        row.date_confidence == "HIGH",
                        row.date_source == "TITLE",
                        row.score,
                    ),
                )
                notice.event_dates = list(best.event_dates)
                notice.event_start_date = winner_key[0]
                notice.event_end_date = winner_key[1]
                notice.event_is_range = winner_key[0] != winner_key[1]
                notice.date_confidence = best.date_confidence
                notice.date_evidence = best.date_evidence
                notice.date_source = f"ENRICHED_{best.date_source}"
                notice.date_conflict = False
                notice.review_reason = "DATE_ENRICHED_REVIEW"
            notice.cities = sorted(
                set(notice.cities)
                | {value for row in winner_rows for value in row.cities}
            )
            notice.venues = sorted(
                set(notice.venues)
                | {value for row in winner_rows for value in row.venues}
            )
            for row in winner_rows:
                if row.url and row.url not in notice.related_urls and row.url != notice.url:
                    notice.related_urls.append(row.url)
            notice.supporting_article_count += len(winner_rows)
            notice.validation_status = "REVIEW_REQUIRED"

        logs.append(
            {
                "source_id": "naver_date_enrichment",
                "artist_id": notice.artist_id,
                "artist": notice.artist,
                "query": query,
                "api_calls": 1,
                "rows_received": len(rows),
                "recent_rows": len(rows),
                "outside_24h": 0,
                "outside_window": 0,
                "missing_pubdate": 0,
                "selected_before_clustering": len(found),
                "error": error,
                "note": (
                    f"date_found={len(notice.event_dates)}"
                    if found and notice.event_dates
                    else "date_conflict"
                    if notice.date_conflict
                    else "date_not_found"
                ),
                "mode": "date_enrichment",
            }
        )
    return logs
