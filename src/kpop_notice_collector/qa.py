from __future__ import annotations

import csv
import re
from pathlib import Path


def _norm(value: str) -> str:
    return re.sub(r"[^0-9a-z가-힣]+", "", (value or "").lower())


def _row_key(row: dict) -> str:
    # 자동 결과의 해시 event_key를 수동 조사자가 알 필요가 없도록 의미 필드로 비교한다.
    artist = row.get("아티스트") or row.get("artist") or row.get("artist_id", "")
    activity = row.get("활동 유형") or row.get("activity_type", "")
    name = row.get("행사명") or row.get("event_name", "")
    dates = row.get("이벤트 날짜") or row.get("event_dates", "")
    cities = row.get("도시") or row.get("cities", "")
    identity = f"{dates}|{cities}" if dates or cities else name
    semantic = "|".join(map(_norm, [artist, activity, identity]))
    return semantic if semantic.strip("|") else row.get("event_key", "")


def load_keys(path: str | Path) -> set[str]:
    path = Path(path)
    if not path.exists():
        return set()
    with path.open(encoding="utf-8-sig", newline="") as f:
        return {_row_key(row) for row in csv.DictReader(f) if _row_key(row)}


def compare_manual_truth(
    automated_path: str | Path, manual_path: str | Path
) -> dict:
    predicted = load_keys(automated_path)
    actual = load_keys(manual_path)
    true_positive = predicted & actual
    false_positive = predicted - actual
    false_negative = actual - predicted
    precision = len(true_positive) / len(predicted) if predicted else 0.0
    recall = len(true_positive) / len(actual) if actual else 0.0
    return {
        "자동 수집": len(predicted),
        "수동 정답": len(actual),
        "일치": len(true_positive),
        "오탐": len(false_positive),
        "누락": len(false_negative),
        "정밀도": precision,
        "재현율": recall,
        "오탐 event_key": sorted(false_positive),
        "누락 event_key": sorted(false_negative),
    }
