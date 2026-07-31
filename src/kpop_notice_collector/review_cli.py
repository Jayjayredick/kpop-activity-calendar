from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from .calendar_feed import build_calendar_feed, build_review_feed
from .config import project_root
from .event_store import EVENT_FIELDS, load_event_rows, write_event_rows
from .review_store import (
    append_review_log,
    load_review_queue,
    write_review_queue,
)


ALLOWED_ACTIONS = {"APPROVE", "REJECT", "UPDATE", "DELETE", "CREATE"}
ALLOWED_ACTIVITIES = {
    "COMEBACK",
    "TOUR_ANNOUNCEMENT",
    "TOUR_EXPANSION",
    "ADDITIONAL_SHOW",
    "ENCORE",
    "CONCERT",
    "FANMEETING",
    "POPUP",
}
FIELD_MAP = {
    "company": "company",
    "label": "label",
    "artistId": "artist_id",
    "artist": "artist",
    "activityType": "activity_type",
    "eventName": "event_name",
    "eventStartDate": "event_start_date",
    "eventEndDate": "event_end_date",
    "cities": "cities",
    "venues": "venues",
    "primaryUrl": "primary_url",
    "note": "note",
}


def parser() -> argparse.ArgumentParser:
    root = project_root()
    result = argparse.ArgumentParser(description="캘린더 검토 결정 반영")
    result.add_argument("--issue-body", required=True)
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
        "--calendar-json",
        default=str(root / "docs" / "calendar_events.json"),
    )
    result.add_argument(
        "--review-json",
        default=str(root / "docs" / "review_queue.json"),
    )
    result.add_argument(
        "--repository",
        default="jayjayredick/kpop-activity-calendar",
    )
    return result


def extract_payload(text: str) -> dict:
    matches = re.findall(r"```json\s*(\{.*?\})\s*```", text, flags=re.I | re.S)
    raw = matches[-1] if matches else text.strip()
    payload = json.loads(raw)
    if payload.get("schema") != "kpop-calendar-review-v1":
        raise ValueError("지원하지 않는 검토 요청 형식입니다.")
    decisions = payload.get("decisions")
    if not isinstance(decisions, list) or not 1 <= len(decisions) <= 30:
        raise ValueError("검토 결정은 1~30건이어야 합니다.")
    if not all(isinstance(item, dict) for item in decisions):
        raise ValueError("각 검토 결정은 JSON 객체여야 합니다.")
    return payload


def _iso(value: str, field: str) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise ValueError(f"{field}는 YYYY-MM-DD 형식이어야 합니다.") from exc


def _event_key(row: dict) -> str:
    normalized = re.sub(
        r"[^0-9a-z가-힣]+",
        "",
        str(row.get("event_name", "")).lower(),
    )
    identity = "|".join(
        [
            str(row.get("artist_id", "")),
            str(row.get("activity_type", "")),
            normalized,
            str(row.get("event_start_date", "")),
            str(row.get("cities", "")),
        ]
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]


def _event_dates(start: str, end: str) -> str:
    start_date = date.fromisoformat(start)
    end_date = date.fromisoformat(end or start)
    if end_date < start_date:
        raise ValueError("종료일은 시작일보다 빠를 수 없습니다.")
    if (end_date - start_date).days > 45:
        return f"{start}|{end_date.isoformat()}"
    return "|".join(
        (start_date + timedelta(days=offset)).isoformat()
        for offset in range((end_date - start_date).days + 1)
    )


def _apply_fields(base: dict, decision: dict) -> dict:
    row = dict(base)
    for source, target in FIELD_MAP.items():
        if source in decision:
            row[target] = str(decision[source] or "").strip()
    row["event_start_date"] = _iso(
        row.get("event_start_date", ""),
        "시작일",
    )
    row["event_end_date"] = _iso(
        row.get("event_end_date", ""),
        "종료일",
    )
    if row["event_start_date"] and not row["event_end_date"]:
        row["event_end_date"] = row["event_start_date"]
    if row.get("activity_type") not in ALLOWED_ACTIVITIES:
        raise ValueError(f"허용되지 않은 활동 유형: {row.get('activity_type')}")
    if not row.get("artist") or not row.get("event_name"):
        raise ValueError("아티스트와 행사명은 필수입니다.")
    if not row["event_start_date"]:
        raise ValueError("확정 일정에는 시작일이 필요합니다.")
    row["event_dates"] = _event_dates(
        row["event_start_date"],
        row["event_end_date"],
    )
    primary_url = row.get("primary_url", "")
    if primary_url:
        parsed = urlparse(primary_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("출처 URL은 http 또는 https 주소여야 합니다.")
    return row


def _history_row(source: dict, decision: dict, now: datetime) -> dict:
    base = {
        "company": source.get("company", ""),
        "label": source.get("label", ""),
        "artist_id": source.get("artist_id", ""),
        "artist": source.get("artist", ""),
        "activity_type": source.get("activity_type", ""),
        "event_name": source.get("event_name", ""),
        "event_start_date": source.get("event_start_date", ""),
        "event_end_date": source.get("event_end_date", ""),
        "date_confidence": "MANUAL",
        "date_evidence": source.get("date_evidence", ""),
        "date_source": "OWNER_REVIEW",
        "date_conflict": "N",
        "cities": source.get("cities", ""),
        "venues": source.get("venues", ""),
        "first_seen": source.get("first_seen") or now.isoformat(),
        "last_seen": now.isoformat(),
        "status": "MANUAL_CONFIRMED",
        "primary_url": source.get("primary_url", ""),
        "source_type": source.get("source_type") or "MANUAL_REVIEW",
        "official_verified": source.get("official_verified") or "N/A",
        "score": source.get("score") or "100",
        "supporting_article_count": source.get("supporting_article_count") or "1",
        "related_urls": source.get("related_urls", ""),
        "approval_status": "MANUAL_CONFIRMED",
        "article_title": source.get("article_title", ""),
        "reviewed_at": now.isoformat(),
        "review_source": "GITHUB_OWNER_REVIEW",
    }
    row = _apply_fields(base, decision)
    row["event_key"] = _event_key(row)
    return {field: row.get(field, "") for field in EVENT_FIELDS}


def apply_decisions(
    payload: dict,
    history_rows: list[dict],
    queue_rows: list[dict],
    *,
    now: datetime,
) -> tuple[list[dict], list[dict], list[dict]]:
    history = {
        row.get("event_key", ""): row
        for row in history_rows
        if row.get("event_key")
    }
    queue = {
        row.get("candidate_id", ""): row
        for row in queue_rows
        if row.get("candidate_id")
    }
    log_rows: list[dict] = []

    for decision in payload["decisions"]:
        action = str(decision.get("action", "")).upper()
        if action not in ALLOWED_ACTIONS:
            raise ValueError(f"허용되지 않은 검토 동작: {action}")
        candidate_id = str(decision.get("candidateId", "")).strip()
        target_event_key = str(decision.get("eventKey", "")).strip()

        if action in {"APPROVE", "REJECT"}:
            if not candidate_id or candidate_id not in queue:
                raise ValueError(f"검토 대기 후보를 찾지 못했습니다: {candidate_id}")
            source = queue[candidate_id]
            if action == "APPROVE":
                row = _history_row(source, decision, now)
                history[row["event_key"]] = row
            queue.pop(candidate_id)
        elif action in {"UPDATE", "DELETE"}:
            if not target_event_key or target_event_key not in history:
                raise ValueError(f"확정 일정을 찾지 못했습니다: {target_event_key}")
            source = history.pop(target_event_key)
            if action == "UPDATE":
                row = _history_row(source, decision, now)
                history[row["event_key"]] = row
        else:
            source = {
                "first_seen": now.isoformat(),
                "source_type": "MANUAL_CREATE",
                "score": "100",
            }
            row = _history_row(source, decision, now)
            history[row["event_key"]] = row

        log_rows.append(
            {
                "reviewed_at": now.isoformat(),
                "action": action,
                "candidate_id": candidate_id,
                "event_key": target_event_key
                or (source.get("event_key", "") if source else ""),
                "artist": decision.get("artist")
                or (source.get("artist", "") if source else ""),
                "activity_type": decision.get("activityType")
                or (source.get("activity_type", "") if source else ""),
                "event_name": decision.get("eventName")
                or (source.get("event_name", "") if source else ""),
                "note": str(decision.get("note", ""))[:500],
            }
        )

    return list(history.values()), list(queue.values()), log_rows


def main() -> None:
    args = parser().parse_args()
    now = datetime.now(ZoneInfo("Asia/Seoul"))
    text = Path(args.issue_body).read_text(encoding="utf-8")
    payload = extract_payload(text)
    history_rows, queue_rows, log_rows = apply_decisions(
        payload,
        load_event_rows(args.history),
        load_review_queue(args.review_queue),
        now=now,
    )
    write_event_rows(args.history, history_rows)
    write_review_queue(args.review_queue, queue_rows)
    append_review_log(args.review_log, log_rows)
    build_calendar_feed(
        history_rows,
        args.calendar_json,
        now=now,
        months=3,
        days_back=14,
        review_rows=queue_rows,
        repository=args.repository,
    )
    build_review_feed(
        queue_rows,
        args.review_json,
        now=now,
        repository=args.repository,
    )
    print(
        json.dumps(
            {
                "applied": len(log_rows),
                "confirmed": len(history_rows),
                "pending": len(queue_rows),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
