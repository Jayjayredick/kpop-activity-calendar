from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .adapters import ADAPTERS
from .classifier import classify
from .config import assert_official_url
from .event_parser import parse_event_fields
from .models import Artist, Notice, Source
from .schedule_compare import assess_schedule_change


def run_pipeline(
    artists: list[Artist],
    sources: list[Source],
    *,
    hours: int = 24,
    company: str | None = None,
    now: datetime | None = None,
    min_score: int = 20,
    history: list[dict] | None = None,
) -> tuple[list[Notice], list[dict], list[dict]]:
    tz = ZoneInfo("Asia/Seoul")
    now = now or datetime.now(tz)
    if now.tzinfo is None:
        now = now.replace(tzinfo=tz)
    cutoff = now - timedelta(hours=hours)

    selected_artists = [
        artist for artist in artists if not company or artist.company.upper() == company.upper()
    ]
    by_id = {artist.artist_id: artist for artist in selected_artists}
    accepted: list[Notice] = []
    excluded: list[dict] = []
    run_log: list[dict] = []
    history = history or []

    for source in sources:
        if source.status != "LIVE":
            continue
        mapped = [by_id[artist_id] for artist_id in source.artist_ids if artist_id in by_id]
        if not mapped:
            continue
        started = datetime.now(tz)
        try:
            assert_official_url(source)
            adapter = ADAPTERS[source.adapter]()
            raw_notices = adapter.collect(source, mapped, started)
            error = ""
        except Exception as exc:
            raw_notices = []
            error = f"{type(exc).__name__}: {exc}"

        run_log.append(
            {
                "source_id": source.source_id,
                "source_name": source.name,
                "url": source.url,
                "started_at": started.isoformat(),
                "rows": len(raw_notices),
                "error": error,
            }
        )

        for notice in raw_notices:
            notice.source_type = "OFFICIAL"
            notice.official_verified = True
            classify(notice)
            notice.score += 25
            parse_event_fields(notice)
            assess_schedule_change(notice, history)
            published = notice.published_at
            if published and published.tzinfo is None:
                published = published.replace(tzinfo=tz)
                notice.published_at = published
            reason = ""
            if not published:
                reason = "게시일 미확인"
            elif not cutoff <= published <= now + timedelta(minutes=10):
                reason = f"{hours}시간 범위 밖"
            elif notice.activity_type == "OTHER" or notice.score < min_score:
                reason = "활동 분류/점수 기준 미달"
            if reason:
                row = notice_to_row(notice)
                row["제외 사유"] = reason
                excluded.append(row)
            else:
                accepted.append(notice)

    deduped: dict[str, Notice] = {}
    for notice in sorted(accepted, key=lambda n: (n.score, n.published_at or now), reverse=True):
        deduped.setdefault(notice.dedupe_key, notice)
    return list(deduped.values()), excluded, run_log


def notice_to_row(notice: Notice) -> dict:
    return {
        "candidate_id": notice.candidate_id,
        "event_key": notice.event_key,
        "수집 채널": notice.source_type,
        "회사": notice.company,
        "레이블": notice.label,
        "아티스트": notice.artist,
        "artist_id": notice.artist_id,
        "활동 유형": notice.activity_type,
        "일정 판정": notice.schedule_status,
        "점수": notice.score,
        "매체 점수": notice.publisher_score,
        "게시일": notice.published_at.isoformat() if notice.published_at else "",
        "제목": notice.title,
        "행사명": notice.event_name,
        "시작일": notice.event_start_date,
        "종료일": notice.event_end_date,
        "이벤트 날짜": "|".join(notice.event_dates),
        "도시": "|".join(notice.cities),
        "공연장": "|".join(notice.venues),
        "클리핑 문구": notice.clipped_text,
        "매칭 키워드": ", ".join(notice.matched_keywords),
        "출처 URL": notice.url,
        "기사 원문 URL": notice.original_url,
        "네이버 뉴스 URL": notice.naver_url,
        "매체": notice.publisher,
        "공식 소스": notice.source_name,
        "공식 확인": "N/A" if notice.source_type == "NAVER_NEWS" else (
            "Y" if notice.official_verified else "N"
        ),
        "검색어": notice.search_query,
        "검증 상태": notice.validation_status,
        "검토 사유": notice.review_reason,
        "제목 매칭 별칭": notice.matched_artist_alias,
        "관련 기사 수": notice.supporting_article_count,
        "관련 기사 URL": "|".join(notice.related_urls),
        "기존 event_key": "|".join(notice.previous_event_keys),
        "source_id": notice.source_id,
        "notice_id": notice.notice_id,
        "dedupe_key": notice.dedupe_key,
        "수집시각": notice.fetched_at.isoformat(),
    }
