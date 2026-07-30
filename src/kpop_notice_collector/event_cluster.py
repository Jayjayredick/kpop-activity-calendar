from __future__ import annotations

import re
from difflib import SequenceMatcher

from .models import Notice


STOPWORDS = {
    "공식",
    "확정",
    "개최",
    "발표",
    "오픈",
    "컴백",
    "신보",
    "앨범",
    "발매",
    "투어",
    "월드투어",
    "콘서트",
    "팬미팅",
    "팬콘",
    "팝업",
    "팝업스토어",
    "추가",
    "회차",
    "공연",
    "앙코르",
    "첫",
    "글로벌",
}


def _tokens(notice: Notice) -> set[str]:
    text = f"{notice.title} {notice.event_name}".lower()
    for alias in [notice.artist, notice.matched_artist_alias]:
        if alias:
            text = text.replace(alias.lower(), " ")
    tokens = {
        token
        for token in re.findall(r"[0-9a-z가-힣♥]+", text)
        if len(token) >= 2 and token not in STOPWORDS
    }
    return tokens


def _anchor(notice: Notice) -> str:
    value = (notice.event_name or "").lower()
    value = re.sub(r"\b(?:20\d{2}|정규|미니|싱글|앨범|투어|콘서트)\b", " ", value)
    return re.sub(r"[^0-9a-z가-힣]+", "", value)


def _similarity(left: Notice, right: Notice) -> float:
    left_tokens, right_tokens = _tokens(left), _tokens(right)
    union = left_tokens | right_tokens
    jaccard = len(left_tokens & right_tokens) / len(union) if union else 0.0
    left_text = re.sub(r"[^0-9a-z가-힣]+", "", left.event_name.lower())
    right_text = re.sub(r"[^0-9a-z가-힣]+", "", right.event_name.lower())
    sequence = (
        SequenceMatcher(None, left_text, right_text).ratio()
        if left_text and right_text
        else 0.0
    )
    return max(jaccard, sequence)


def _same_event(left: Notice, right: Notice) -> bool:
    if left.artist_id != right.artist_id or left.activity_type != right.activity_type:
        return False
    left_anchor, right_anchor = _anchor(left), _anchor(right)
    if (
        left_anchor
        and right_anchor
        and len(left_anchor) >= 3
        and left_anchor == right_anchor
    ):
        return True
    if set(left.event_dates) & set(right.event_dates):
        # 컴백은 같은 날짜면 같은 발매일 가능성이 높고, 공연은 도시나 행사명까지 본다.
        if left.activity_type == "COMEBACK":
            return True
        if set(left.cities) & set(right.cities) or _similarity(left, right) >= 0.32:
            return True
    if set(left.cities) & set(right.cities) and _similarity(left, right) >= 0.30:
        return True
    return _similarity(left, right) >= 0.38


def cluster_events(notices: list[Notice]) -> list[Notice]:
    clusters: list[list[Notice]] = []
    ordered = sorted(
        notices,
        key=lambda item: (
            item.score,
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
        representative = group[0]
        representative.event_dates = sorted(
            {value for item in group for value in item.event_dates}
        )
        ranges = sorted(
            {
                (item.event_start_date, item.event_end_date)
                for item in group
                if item.event_start_date
            }
        )
        if ranges:
            representative.event_start_date = ranges[0][0]
            representative.event_end_date = ranges[0][1] or ranges[0][0]
            representative.event_is_range = (
                representative.event_start_date != representative.event_end_date
            )
        representative.cities = sorted(
            {value for item in group for value in item.cities}
        )
        representative.venues = sorted(
            {value for item in group for value in item.venues}
        )
        all_urls = []
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
        if representative.event_dates:
            representative.validation_status = "AUTO_SELECTED"
        representatives.append(representative)
    return representatives
