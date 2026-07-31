from __future__ import annotations

import re
from difflib import SequenceMatcher

from .models import Notice


STOPWORDS = {
    "공식", "확정", "개최", "발표", "오픈", "컴백", "신보", "앨범",
    "발매", "투어", "월드투어", "콘서트", "팬미팅", "팬콘", "팝업",
    "팝업스토어", "추가", "회차", "공연", "앙코르", "첫", "글로벌",
    "일정", "예정", "단독", "서울", "한국", "일본",
}
GENERIC_ANCHOR = re.compile(
    r"^(?:첫|새|신규|단독|월드|아시아|글로벌|공식|컴백|투어|"
    r"콘서트|팬미팅|팬콘서트|팝업스토어|추가공연|앙코르)+$",
    re.I,
)
DATE_CONFIDENCE = {"NONE": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3, "CONFLICT": -1}


def _tokens(notice: Notice) -> set[str]:
    text = f"{notice.title} {notice.event_name}".lower()
    for alias in [notice.artist, notice.matched_artist_alias]:
        if alias:
            text = text.replace(alias.lower(), " ")
    return {
        token
        for token in re.findall(r"[0-9a-z가-힣♥]+", text)
        if len(token) >= 2 and token not in STOPWORDS
    }


def _anchor(notice: Notice) -> str:
    value = (notice.event_name or "").lower()
    for alias in [notice.artist, notice.matched_artist_alias]:
        if alias:
            value = re.sub(re.escape(alias.lower()), " ", value)
    value = re.sub(
        r"\b(?:20\d{2}|정규|미니|싱글|앨범|투어|콘서트|팬미팅|팬콘서트)\b",
        " ",
        value,
    )
    value = re.sub(r"[^0-9a-z가-힣♥]+", "", value)
    if len(value) < 4 or GENERIC_ANCHOR.match(value):
        return ""
    return value


def _similarity(left: Notice, right: Notice) -> float:
    left_tokens, right_tokens = _tokens(left), _tokens(right)
    union = left_tokens | right_tokens
    jaccard = len(left_tokens & right_tokens) / len(union) if union else 0.0
    left_text = _anchor(left)
    right_text = _anchor(right)
    sequence = (
        SequenceMatcher(None, left_text, right_text).ratio()
        if left_text and right_text
        else 0.0
    )
    return max(jaccard, sequence)


def _date_range(notice: Notice) -> tuple[str, str] | None:
    if notice.date_conflict:
        return None
    if not notice.event_start_date and notice.event_dates:
        values = sorted(notice.event_dates)
        return values[0], values[-1]
    if not notice.event_start_date:
        return None
    return (
        notice.event_start_date,
        notice.event_end_date or notice.event_start_date,
    )


def _dates_overlap(left: Notice, right: Notice) -> bool:
    left_range, right_range = _date_range(left), _date_range(right)
    if not left_range or not right_range:
        return False
    return left_range[0] <= right_range[1] and right_range[0] <= left_range[1]


def _same_event(left: Notice, right: Notice) -> bool:
    if left.artist_id != right.artist_id or left.activity_type != right.activity_type:
        return False

    left_range, right_range = _date_range(left), _date_range(right)
    # 날짜가 모두 명확한데 서로 겹치지 않으면 행사명이 같더라도 다른 회차로 보존한다.
    if left_range and right_range and not _dates_overlap(left, right):
        return False

    left_anchor, right_anchor = _anchor(left), _anchor(right)
    exact_anchor = bool(left_anchor and left_anchor == right_anchor)
    similarity = _similarity(left, right)
    if exact_anchor:
        return True
    if _dates_overlap(left, right):
        # 같은 날짜·도시는 서로 다른 공연에서도 흔하므로 행사명 유사도가
        # 확인되지 않으면 합치지 않는다.
        return similarity >= 0.48
    # 한쪽만 날짜가 없는 경우 행사명이 매우 유사할 때만 보강 기사로 합친다.
    if bool(left_range) != bool(right_range):
        return similarity >= 0.72
    # 둘 다 날짜가 없으면 제목만 비슷한 일반 기사끼리 합치지 않는다.
    return similarity >= 0.82 and bool(left_anchor and right_anchor)


def _date_quality(notice: Notice) -> tuple[int, int, int]:
    return (
        DATE_CONFIDENCE.get(notice.date_confidence, 0),
        1 if notice.date_source == "TITLE" else 0,
        notice.score,
    )


def _copy_best_date(representative: Notice, group: list[Notice]) -> None:
    dated = [
        item
        for item in group
        if item.event_start_date and not item.date_conflict
    ]
    if not dated:
        representative.event_dates = []
        representative.event_start_date = ""
        representative.event_end_date = ""
        representative.event_is_range = False
        if any(item.date_conflict for item in group):
            representative.date_conflict = True
            representative.date_confidence = "CONFLICT"
        return

    best = max(dated, key=_date_quality)
    representative.event_dates = list(best.event_dates)
    representative.event_start_date = best.event_start_date
    representative.event_end_date = best.event_end_date
    representative.event_is_range = best.event_is_range
    representative.date_confidence = best.date_confidence
    representative.date_evidence = best.date_evidence
    representative.date_source = best.date_source
    representative.date_conflict = False


def cluster_events(notices: list[Notice]) -> list[Notice]:
    clusters: list[list[Notice]] = []
    ordered = sorted(
        notices,
        key=lambda item: (
            _date_quality(item),
            item.publisher_score,
            item.published_at or item.fetched_at,
        ),
        reverse=True,
    )
    for notice in ordered:
        cluster = next(
            (
                group
                for group in clusters
                if any(_same_event(notice, existing) for existing in group)
            ),
            None,
        )
        if cluster is None:
            clusters.append([notice])
        else:
            cluster.append(notice)

    representatives: list[Notice] = []
    for group in clusters:
        representative = max(
            group,
            key=lambda item: (
                _date_quality(item),
                item.publisher_score,
                item.published_at or item.fetched_at,
            ),
        )
        _copy_best_date(representative, group)
        representative.cities = sorted(
            {value for item in group for value in item.cities}
        )
        representative.venues = sorted(
            {value for item in group for value in item.venues}
        )
        all_urls: list[str] = []
        for item in group:
            for value in [item.url, *item.related_urls]:
                if value and value not in all_urls:
                    all_urls.append(value)
        representative.related_urls = [
            value for value in all_urls if value != representative.url
        ]
        representative.supporting_article_count = sum(
            max(1, item.supporting_article_count) for item in group
        )
        representatives.append(representative)
    return representatives
