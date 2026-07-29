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
    "FANMEETING": "팬미팅",
    "POPUP": "팝업",
}

ACTIVITY_COLORS = {
    "COMEBACK": "#2563eb",
    "TOUR_ANNOUNCEMENT": "#7c3aed",
    "TOUR_EXPANSION": "#9333ea",
    "ADDITIONAL_SHOW": "#dc2626",
    "ENCORE": "#ea580c",
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
) -> Path:
    start = now.date()
    end_inclusive = add_months(start, months)
    end_exclusive = end_inclusive + timedelta(days=1)
    events: list[dict] = []

    for row in rows:
        activity_type = str(row.get("activity_type", ""))
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
            artist = str(row.get("artist", "")).strip()
            label = ACTIVITY_LABELS.get(activity_type, activity_type)
            events.append(
                {
                    "id": f"{row.get('event_key', '')}:{raw_date}",
                    "groupId": str(row.get("event_key", "")),
                    "title": f"{artist} · {label}",
                    "start": raw_date,
                    "allDay": True,
                    "color": ACTIVITY_COLORS.get(activity_type, "#64748b"),
                    "url": str(row.get("primary_url", "")),
                    "extendedProps": {
                        "company": str(row.get("company", "")),
                        "label": str(row.get("label", "")),
                        "artist": artist,
                        "activityType": activity_type,
                        "activityLabel": label,
                        "eventName": str(row.get("event_name", "")),
                        "cities": str(row.get("cities", "")),
                        "venues": str(row.get("venues", "")),
                        "status": str(row.get("status", "")),
                        "score": str(row.get("score", "")),
                        "supportingArticleCount": str(
                            row.get("supporting_article_count", "")
                        ),
                    },
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
        "events": events,
    }
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path
