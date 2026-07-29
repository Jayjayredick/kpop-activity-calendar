from __future__ import annotations

import csv
import re
from difflib import SequenceMatcher
from pathlib import Path

from .models import Notice


TOUR_TYPES = {"TOUR_ANNOUNCEMENT", "TOUR_EXPANSION", "ADDITIONAL_SHOW", "ENCORE"}


def _norm(value: str) -> str:
    return re.sub(r"[^0-9a-z가-힣]+", "", (value or "").lower())


def _similar(a: str, b: str) -> float:
    a1, b1 = _norm(a), _norm(b)
    if not a1 or not b1:
        return 0.0
    return SequenceMatcher(None, a1, b1).ratio()


def load_event_history(path: str | Path) -> list[dict]:
    path = Path(path)
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def assess_schedule_change(notice: Notice, history: list[dict]) -> Notice:
    candidates = [
        row
        for row in history
        if row.get("artist_id") == notice.artist_id
        and (
            row.get("activity_type") == notice.activity_type
            or {row.get("activity_type"), notice.activity_type} <= TOUR_TYPES
        )
        and _similar(row.get("event_name", ""), notice.event_name or notice.title) >= 0.48
    ]
    notice.previous_event_keys = [
        row.get("event_key", "") for row in candidates if row.get("event_key")
    ]

    explicit_additional = bool(
        re.search(r"(추가\s*(?:회차|공연)|회차\s*추가|additional\s+show|extra\s+show|追加公演)", notice.title, re.I)
    )
    if explicit_additional:
        notice.activity_type = "ADDITIONAL_SHOW"
        notice.schedule_status = "EXPLICIT_ADDITIONAL_SHOW"
        return notice
    if not candidates:
        notice.schedule_status = "NEW_EVENT"
        return notice

    old_dates = {
        value
        for row in candidates
        for value in (row.get("event_dates", "") or "").split("|")
        if value
    }
    old_cities = {
        value
        for row in candidates
        for value in (row.get("cities", "") or "").split("|")
        if value
    }
    new_dates = set(notice.event_dates) - old_dates
    new_cities = set(notice.cities) - old_cities

    if new_cities:
        notice.activity_type = "TOUR_EXPANSION"
        notice.schedule_status = "NEW_CITY"
        notice.score += 12
    elif new_dates and set(notice.cities) & old_cities:
        notice.activity_type = "ADDITIONAL_SHOW"
        notice.schedule_status = "SAME_CITY_NEW_DATE"
        notice.score += 15
    elif new_dates:
        notice.schedule_status = "NEW_DATE_REVIEW"
        notice.validation_status = "REVIEW_REQUIRED"
        notice.score += 6
    else:
        notice.schedule_status = "EXISTING_SCHEDULE"
    return notice
