from __future__ import annotations

import json
from calendar import monthrange
from datetime import date, datetime, timedelta
from pathlib import Path


ACTIVITY_LABELS = {
    "COMEBACK": "컴백",
    "TOUR_ANNOUNCEMENT": "투어 발표",
    "TOUR_EXPANSION": "투어 확장",
    "ADDITIONAL_SHOW": "추가 회차",
    "ENCORE": "앙코르",
    "CONCERT": "콘서트",
    "FANMEETING": "팬미팅",
    "POPUP": "팝업",
}

ACTIVITY_COLORS = {
    "COMEBACK": "#2563eb",
    "TOUR_ANNOUNCEMENT": "#7c3aed",
    "TOUR_EXPANSION": "#9333ea",
    "ADDITIONAL_SHOW": "#dc2626",
    "ENCORE": "#ea580c",
    "CONCERT": "#0f766e",
    "FANMEETING": "#059669",
    "POPUP": "#ca8a04",
}


def add_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, monthrange(year, month)[1])
    return date(year, month, day)


def build_calendar_feed(
    rows: list[dict],
    path: str | Path,
    *,
    now: datetime,
    months: int = 3,
    days_back: int = 14,
    review_rows: list[dict] | None = None,
    repository: str = "",
) -> Path:
    start = now.date() - timedelta(days=max(0, days_back))
    # "오늘 이후 3개월"은 과거 표시 범위와 무관하게 오늘을 기준으로 계산한다.
    end_inclusive = add_months(now.date(), months)
    end_exclusive = end_inclusive + timedelta(days=1)
    events: list[dict] = []

    for row in rows:
        if str(row.get("approval_status", "")).upper() in {
            "REJECTED",
            "DELETED",
            "PENDING",
        }:
            continue
        activity_type = str(row.get("activity_type", ""))
        range_start = str(row.get("event_start_date", "")).strip()
        range_end = str(row.get("event_end_date", "")).strip()
        event_name = str(row.get("event_name", "")).strip()
        artist = str(row.get("artist", "")).strip()
        label = ACTIVITY_LABELS.get(activity_type, activity_type)
        display_title = (
            f"{artist} · {event_name}"
            if event_name and event_name.casefold() != artist.casefold()
            else f"{artist} · {label}"
        )

        if range_start:
            try:
                parsed_start = date.fromisoformat(range_start)
                parsed_end = date.fromisoformat(range_end or range_start)
            except ValueError:
                parsed_start = parsed_end = None
            if parsed_start and parsed_end and not (
                parsed_end < start or parsed_start > end_inclusive
            ):
                events.append(
                    {
                        "id": str(row.get("event_key", "")),
                        "groupId": str(row.get("event_key", "")),
                        "title": display_title,
                        "start": parsed_start.isoformat(),
                        "end": (parsed_end + timedelta(days=1)).isoformat(),
                        "allDay": True,
                        "color": ACTIVITY_COLORS.get(activity_type, "#64748b"),
                        "url": str(row.get("primary_url", "")),
                        "extendedProps": _extended_props(
                            row, activity_type, label, artist, event_name
                        ),
                    }
                )
                continue

        for raw_date in str(row.get("event_dates", "")).split("|"):
            raw_date = raw_date.strip()
            if not raw_date:
                continue
            try:
                event_date = date.fromisoformat(raw_date)
            except ValueError:
                continue
            if not start <= event_date <= end_inclusive:
                continue
            events.append(
                {
                    "id": f"{row.get('event_key', '')}:{raw_date}",
                    "groupId": str(row.get("event_key", "")),
                    "title": display_title,
                    "start": raw_date,
                    "allDay": True,
                    "color": ACTIVITY_COLORS.get(activity_type, "#64748b"),
                    "url": str(row.get("primary_url", "")),
                    "extendedProps": _extended_props(
                        row, activity_type, label, artist, event_name
                    ),
                }
            )

    events.sort(key=lambda item: (item["start"], item["title"]))
    payload = {
        "generatedAt": now.isoformat(),
        "timezone": "Asia/Seoul",
        "rangeStart": start.isoformat(),
        "rangeEndInclusive": end_inclusive.isoformat(),
        "rangeEndExclusive": end_exclusive.isoformat(),
        "eventCount": len(events),
        "pendingCount": len(review_rows or []),
        "repository": repository,
        "events": events,
    }
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def _extended_props(
    row: dict,
    activity_type: str,
    activity_label: str,
    artist: str,
    event_name: str,
) -> dict:
    return {
        "eventKey": str(row.get("event_key", "")),
        "company": str(row.get("company", "")),
        "label": str(row.get("label", "")),
        "artist": artist,
        "artistId": str(row.get("artist_id", "")),
        "activityType": activity_type,
        "activityLabel": activity_label,
        "eventName": event_name,
        "eventStartDate": str(row.get("event_start_date", "")),
        "eventEndDate": str(row.get("event_end_date", "")),
        "cities": str(row.get("cities", "")),
        "venues": str(row.get("venues", "")),
        "status": str(row.get("status", "")),
        "approvalStatus": str(row.get("approval_status", "")),
        "score": str(row.get("score", "")),
        "articleTitle": str(row.get("article_title", "")),
        "primaryUrl": str(row.get("primary_url", "")),
        "supportingArticleCount": str(
            row.get("supporting_article_count", "")
        ),
    }


def build_review_feed(
    rows: list[dict],
    path: str | Path,
    *,
    now: datetime,
    repository: str = "",
) -> Path:
    payload = {
        "generatedAt": now.isoformat(),
        "timezone": "Asia/Seoul",
        "repository": repository,
        "pendingCount": len(rows),
        "items": [
            {
                "candidateId": str(row.get("candidate_id", "")),
                "eventKey": str(row.get("event_key", "")),
                "company": str(row.get("company", "")),
                "label": str(row.get("label", "")),
                "artistId": str(row.get("artist_id", "")),
                "artist": str(row.get("artist", "")),
                "activityType": str(row.get("activity_type", "")),
                "activityLabel": ACTIVITY_LABELS.get(
                    str(row.get("activity_type", "")),
                    str(row.get("activity_type", "")),
                ),
                "eventName": str(row.get("event_name", "")),
                "eventStartDate": str(row.get("event_start_date", "")),
                "eventEndDate": str(row.get("event_end_date", "")),
                "eventDates": str(row.get("event_dates", "")),
                "cities": str(row.get("cities", "")),
                "venues": str(row.get("venues", "")),
                "articleTitle": str(row.get("article_title", "")),
                "publishedAt": str(row.get("published_at", "")),
                "score": str(row.get("score", "")),
                "reviewReason": str(row.get("review_reason", "")),
                "primaryUrl": str(row.get("primary_url", "")),
                "naverUrl": str(row.get("naver_url", "")),
                "supportingArticleCount": str(
                    row.get("supporting_article_count", "")
                ),
                "clippedText": str(row.get("clipped_text", "")),
                "firstSeen": str(row.get("first_seen", "")),
                "lastSeen": str(row.get("last_seen", "")),
            }
            for row in rows
        ],
    }
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path
