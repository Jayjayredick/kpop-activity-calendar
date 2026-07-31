from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from .models import Notice


FULL_DATE = re.compile(
    r"(?<!\d)(20\d{2})\s*(?:[.\-/]|년)\s*(\d{1,2})\s*"
    r"(?:[.\-/]|월)\s*(\d{1,2})\s*일?"
)
CROSS_MONTH_RANGE = re.compile(
    r"(?<!\d)(\d{1,2})\s*월\s*(\d{1,2})\s*일?\s*"
    r"(?:부터|[~∼～\-–—])\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일(?:까지)?"
)
MONTH_DAY_RANGE = re.compile(
    r"(?<!\d)(\d{1,2})\s*월\s*(\d{1,2})\s*(?:일)?\s*"
    r"(?:부터|[~∼～\-–—])\s*(\d{1,2})\s*일(?:까지)?"
)
RELATIVE_CROSS_MONTH_RANGE = re.compile(
    r"(?:오는\s*)?(\d{1,2})\s*일\s*(?:부터|[~∼～\-–—])\s*"
    r"(?:내달|다음\s*달)\s*(\d{1,2})\s*일(?:까지)?"
)
BARE_DAY_RANGE = re.compile(
    r"(?<![\d월])(\d{1,2})\s*(?:일)?\s*[~∼～\-–—]\s*"
    r"(\d{1,2})\s*일(?:까지)?"
)
MONTH_DAY = re.compile(r"(?<!\d)(\d{1,2})\s*월\s*(\d{1,2})\s*일")
NEXT_MONTH_DAY = re.compile(r"(?:내달|다음\s*달)\s*(\d{1,2})\s*일")
RELATIVE_DAY = re.compile(
    r"(?:오늘|오는|내일|익일)(?:\s*\(\s*)?(\d{1,2})\s*일(?:\s*\))?"
)
BARE_DAY = re.compile(
    r"(?<![\d월])(\d{1,2})\s*일"
    r"(?!\s*(?:[~∼～\-–—]|간\b|동안\b|연속\b|째\b|전\b|후\b|"
    r"만에\b|이내\b))"
)
PAST_BARE_DAY_PREFIX = re.compile(r"(?:지난|앞선|앞서|전날)\s*$", re.I)

CITY_ALIASES = {
    "서울": ["서울", "seoul"],
    "부산": ["부산", "busan"],
    "인천": ["인천", "incheon"],
    "도쿄": ["도쿄", "tokyo", "東京"],
    "오사카": ["오사카", "osaka", "大阪"],
    "나고야": ["나고야", "nagoya", "名古屋"],
    "후쿠오카": ["후쿠오카", "fukuoka", "福岡"],
    "타이베이": ["타이베이", "taipei", "台北"],
    "홍콩": ["홍콩", "hong kong", "香港"],
    "마카오": ["마카오", "macau", "macao"],
    "방콕": ["방콕", "bangkok"],
    "싱가포르": ["싱가포르", "singapore"],
    "자카르타": ["자카르타", "jakarta"],
    "마닐라": ["마닐라", "manila"],
    "쿠알라룸푸르": ["쿠알라룸푸르", "kuala lumpur"],
    "로스앤젤레스": ["로스앤젤레스", "los angeles", " la "],
    "뉴욕": ["뉴욕", "new york"],
    "시카고": ["시카고", "chicago"],
    "런던": ["런던", "london"],
    "파리": ["파리", "paris"],
}

VENUE_RE = re.compile(
    r"([A-Za-z0-9&.'’\-\s가-힣]{2,45}?"
    r"(?:stadium|arena|dome|hall|theatre|theater|center|centre|"
    r"스타디움|아레나|돔|홀|체육관|공연장))",
    re.I,
)

QUOTED = r"['\"‘’“”<\[]\s*([^'\"‘’“”<>\[\]]{2,100})\s*['\"‘’“”>\]]"
RELEASE_EVENT_NAME = re.compile(
    rf"(?:정규\s*\d*집|미니\s*\d*집|싱글|앨범|신보)"
    rf"\s*(?:명|은|는|:)?\s*{QUOTED}",
    re.I,
)
LIVE_EVENT_NAME = re.compile(
    rf"(?:월드\s*투어|아시아\s*투어|투어|단독\s*콘서트|콘서트|"
    rf"팬콘(?:서트)?|팬\s*콘서트|팬미팅|팝업(?:스토어)?)"
    rf"\s*(?:명|은|는|:)?\s*{QUOTED}",
    re.I,
)
QUOTED_BEFORE_LIVE_TYPE = re.compile(
    rf"{QUOTED}\s*(?:월드\s*투어|아시아\s*투어|투어|콘서트|"
    rf"팬콘(?:서트)?|팬미팅|팝업(?:스토어)?)",
    re.I,
)
TOUR_NAME = re.compile(
    r"((?:20\d{2}[-–]\d{2}\s*)?[A-Za-z0-9가-힣&:#!?'’\-\s]{2,90}"
    r"(?:WORLD\s+TOUR|LIVE\s+TOUR|CONCERT\s+TOUR|TOUR))",
    re.I,
)
UNQUOTED_RELEASE_NAME = re.compile(
    r"(?:정규\s*\d*집|미니\s*\d*집|싱글|앨범|신보)\s+"
    r"([A-Z][A-Z0-9&:#!?'\-]{2,60})\b"
)
NOISY_EVENT_WORDS = re.compile(
    r"^(?:컴백|신보|새\s*앨범|정규\s*\d*집|미니\s*\d*집|싱글|"
    r"콘서트|팬콘|팬미팅|팝업스토어|월드투어|투어)$",
    re.I,
)
SONG_OR_STAGE_CONTEXT = re.compile(
    r"(?:신곡|미발표곡|수록곡|무대|세트리스트|퍼포먼스)"
    r"[^'\"‘’“”]{0,24}['\"‘’“”]",
    re.I,
)

ACTIVITY_CUES = {
    "COMEBACK": ("컴백", "신보", "앨범", "싱글", "발매", "출시"),
    "TOUR_ANNOUNCEMENT": ("투어", "월드투어", "아시아투어"),
    "TOUR_EXPANSION": ("투어", "추가", "확장", "도시"),
    "ADDITIONAL_SHOW": ("추가 회차", "추가 공연", "공연"),
    "ENCORE": ("앙코르", "콘서트", "공연"),
    "CONCERT": ("콘서트", "공연", "팬콘"),
    "FANMEETING": ("팬미팅", "팬 미팅"),
    "POPUP": ("팝업", "팝업스토어"),
}
FUTURE_CUES = re.compile(
    r"(예정|개최|발매|출시|오픈|연다|돌입|시작|추가|확정|발표|오는|내달|다음\s*달)",
    re.I,
)


@dataclass(frozen=True)
class DateCandidate:
    start: date
    end: date
    score: int
    evidence: str
    source: str
    span: tuple[int, int]


def _date_span(start: date, end: date) -> list[str]:
    if end < start or (end - start).days > 45:
        return []
    return [
        (start + timedelta(days=offset)).isoformat()
        for offset in range((end - start).days + 1)
    ]


def _clean_venue(value: str) -> str:
    value = re.sub(r"\s+", " ", value).strip(" -–—,·")
    parts = re.split(r"[,.]|(?:에서|으로|에서의)\s+", value)
    candidate = parts[-1].strip() if parts else value
    if len(candidate) < 2:
        candidate = value
    if "까지" in candidate:
        candidate = candidate.split("까지", 1)[1].strip()
    candidate = re.sub(r"^.*?\d{1,2}\s*일(?:부터|까지)?\s*", "", candidate)
    candidate = re.sub(
        r"^(?:서울|부산|인천|도쿄|오사카|나고야|후쿠오카|타이베이|"
        r"홍콩|마카오|방콕|싱가포르|자카르타|마닐라|뉴욕|런던|파리)\s+",
        "",
        candidate,
        flags=re.I,
    )
    return candidate


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _infer_year(
    month: int,
    reference_date: date,
    context: str,
) -> int:
    if re.search(r"내년|다음\s*해", context):
        return reference_date.year + 1
    # 연말 기사에서 별도 연도 없이 1분기 일정을 말하는 경우만 다음 해로 본다.
    if (
        reference_date.month >= 10
        and month <= 3
        and FUTURE_CUES.search(context)
    ):
        return reference_date.year + 1
    # 과거 월을 무조건 다음 해로 넘기지 않는다. 회고 기사의 과거 일정을
    # 미래 일정으로 만드는 오류를 막기 위한 보수적 기준이다.
    return reference_date.year


def _overlaps(span: tuple[int, int], occupied: list[tuple[int, int]]) -> bool:
    return any(span[0] < right and span[1] > left for left, right in occupied)


def _candidate_score(
    text: str,
    span: tuple[int, int],
    activity_type: str,
    base: int,
) -> int:
    left = max(0, span[0] - 34)
    right = min(len(text), span[1] + 34)
    context = text[left:right]
    cues = ACTIVITY_CUES.get(activity_type, ())
    cue_bonus = 18 if any(cue.lower() in context.lower() for cue in cues) else 0
    future_bonus = 6 if FUTURE_CUES.search(context) else 0
    return base + cue_bonus + future_bonus


def _extract_candidates(
    text: str,
    *,
    reference_date: date,
    activity_type: str,
    source: str,
) -> list[DateCandidate]:
    candidates: list[DateCandidate] = []
    occupied: list[tuple[int, int]] = []
    source_penalty = 0 if source == "TITLE" else 32

    def add(
        match: re.Match,
        start: date | None,
        end: date | None,
        base: int,
    ) -> None:
        if not start or not end or not _date_span(start, end):
            return
        span = match.span()
        occupied.append(span)
        candidates.append(
            DateCandidate(
                start=start,
                end=end,
                score=_candidate_score(
                    text, span, activity_type, base - source_penalty
                ),
                evidence=re.sub(r"\s+", " ", match.group(0)).strip(),
                source=source,
                span=span,
            )
        )

    for match in CROSS_MONTH_RANGE.finditer(text):
        sm, sd, em, ed = map(int, match.groups())
        context = text[max(0, match.start() - 30):match.end() + 30]
        start_year = _infer_year(sm, reference_date, context)
        end_year = start_year + (1 if em < sm else 0)
        add(
            match,
            _safe_date(start_year, sm, sd),
            _safe_date(end_year, em, ed),
            94,
        )

    for match in RELATIVE_CROSS_MONTH_RANGE.finditer(text):
        if _overlaps(match.span(), occupied):
            continue
        sd, ed = map(int, match.groups())
        sm = reference_date.month
        em = 1 if sm == 12 else sm + 1
        end_year = reference_date.year + (1 if sm == 12 else 0)
        add(
            match,
            _safe_date(reference_date.year, sm, sd),
            _safe_date(end_year, em, ed),
            88,
        )

    for match in MONTH_DAY_RANGE.finditer(text):
        if _overlaps(match.span(), occupied):
            continue
        month, sd, ed = map(int, match.groups())
        context = text[max(0, match.start() - 30):match.end() + 30]
        year = _infer_year(month, reference_date, context)
        add(match, _safe_date(year, month, sd), _safe_date(year, month, ed), 94)

    for match in FULL_DATE.finditer(text):
        if _overlaps(match.span(), occupied):
            continue
        year, month, day = map(int, match.groups())
        value = _safe_date(year, month, day)
        add(match, value, value, 98)

    for match in MONTH_DAY.finditer(text):
        if _overlaps(match.span(), occupied):
            continue
        month, day = map(int, match.groups())
        context = text[max(0, match.start() - 30):match.end() + 30]
        year = _infer_year(month, reference_date, context)
        value = _safe_date(year, month, day)
        add(match, value, value, 90)

    for match in NEXT_MONTH_DAY.finditer(text):
        if _overlaps(match.span(), occupied):
            continue
        day = int(match.group(1))
        month = 1 if reference_date.month == 12 else reference_date.month + 1
        year = reference_date.year + (1 if reference_date.month == 12 else 0)
        value = _safe_date(year, month, day)
        add(match, value, value, 76)

    for match in BARE_DAY_RANGE.finditer(text):
        if _overlaps(match.span(), occupied):
            continue
        sd, ed = map(int, match.groups())
        add(
            match,
            _safe_date(reference_date.year, reference_date.month, sd),
            _safe_date(reference_date.year, reference_date.month, ed),
            66,
        )

    for match in RELATIVE_DAY.finditer(text):
        if _overlaps(match.span(), occupied):
            continue
        day = int(match.group(1))
        value = _safe_date(reference_date.year, reference_date.month, day)
        add(match, value, value, 68)

    # 월이 생략된 단일 일자는 제목에서 활동 키워드와 미래 행동 문구가
    # 함께 있을 때만 기사 게시 월을 기준으로 사용한다.
    if source == "TITLE":
        for match in BARE_DAY.finditer(text):
            if _overlaps(match.span(), occupied):
                continue
            prefix = text[max(0, match.start() - 10):match.start()]
            if PAST_BARE_DAY_PREFIX.search(prefix):
                continue
            context = text[max(0, match.start() - 34):match.end() + 34]
            cues = ACTIVITY_CUES.get(activity_type, ())
            if not FUTURE_CUES.search(context):
                continue
            if not any(cue.lower() in context.lower() for cue in cues):
                continue
            day = int(match.group(1))
            value = _safe_date(reference_date.year, reference_date.month, day)
            add(match, value, value, 40)

    return candidates


def _select_candidate(
    title_candidates: list[DateCandidate],
    body_candidates: list[DateCandidate],
) -> tuple[DateCandidate | None, bool]:
    # 제목의 단일 일자를 설명문의 더 완전한 동일 시작일 범위가 보강하는
    # 경우만 설명문 범위를 허용한다. 그 외에는 제목 날짜를 우선한다.
    pool = title_candidates or body_candidates
    if title_candidates and body_candidates:
        title_best = max(title_candidates, key=lambda item: item.score)
        body_best = max(body_candidates, key=lambda item: item.score)
        if (
            title_best.start == title_best.end
            and body_best.start == title_best.start
            and body_best.end > title_best.end
            and body_best.score >= title_best.score
        ):
            pool = body_candidates
    if not pool:
        return None, False
    by_range: dict[tuple[date, date], DateCandidate] = {}
    for candidate in pool:
        key = (candidate.start, candidate.end)
        current = by_range.get(key)
        if current is None or candidate.score > current.score:
            by_range[key] = candidate
    ranked = sorted(
        by_range.values(),
        key=lambda item: (item.score, item.start, item.end),
        reverse=True,
    )
    if len(ranked) == 1:
        return ranked[0], False
    # 명확히 활동 키워드에 더 가까운 날짜가 하나만 있으면 그 날짜를 택한다.
    if ranked[0].score - ranked[1].score >= 15:
        return ranked[0], False
    return None, True


def extract_event_name(notice: Notice, text: str) -> str:
    title = re.sub(r"\s+", " ", notice.title).strip()
    pattern = (
        RELEASE_EVENT_NAME
        if notice.activity_type == "COMEBACK"
        else LIVE_EVENT_NAME
    )
    strict = pattern.search(title)
    if strict:
        value = re.sub(r"\s+", " ", strict.group(1)).strip()
        if value and not NOISY_EVENT_WORDS.match(value):
            return value[:120]

    if notice.activity_type != "COMEBACK":
        before = QUOTED_BEFORE_LIVE_TYPE.search(title)
        if before:
            value = re.sub(r"\s+", " ", before.group(1)).strip()
            if value and not NOISY_EVENT_WORDS.match(value):
                return value[:120]

    if notice.activity_type == "COMEBACK":
        release_match = UNQUOTED_RELEASE_NAME.search(title)
        if release_match:
            return release_match.group(1).strip()[:120]

    tour_match = TOUR_NAME.search(title)
    if tour_match:
        value = re.sub(r"\s+", " ", tour_match.group(1)).strip(" -–—,·")
        if len(value) >= 3:
            return value[:120]

    # 콘서트 기사 속 신곡·무대명을 행사명으로 오인하지 않는다.
    if notice.activity_type in {
        "CONCERT",
        "TOUR_ANNOUNCEMENT",
        "TOUR_EXPANSION",
        "ADDITIONAL_SHOW",
        "ENCORE",
        "FANMEETING",
    } and SONG_OR_STAGE_CONTEXT.search(title):
        label = "팬콘서트" if re.search(r"팬콘|팬\s*콘서트", title) else {
            "CONCERT": "콘서트",
            "TOUR_ANNOUNCEMENT": "투어",
            "TOUR_EXPANSION": "투어 추가 일정",
            "ADDITIONAL_SHOW": "추가 공연",
            "ENCORE": "앙코르 콘서트",
            "FANMEETING": "팬미팅",
        }.get(notice.activity_type, "공연")
        return f"{notice.artist} {label}"

    cleaned = title.split("…", 1)[0].split("...", 1)[0]
    for alias in [notice.matched_artist_alias, notice.artist]:
        if alias:
            cleaned = re.sub(re.escape(alias), " ", cleaned, flags=re.I)
    for date_pattern in (
        CROSS_MONTH_RANGE,
        RELATIVE_CROSS_MONTH_RANGE,
        MONTH_DAY_RANGE,
        FULL_DATE,
        MONTH_DAY,
        NEXT_MONTH_DAY,
        BARE_DAY_RANGE,
        RELATIVE_DAY,
        BARE_DAY,
    ):
        cleaned = date_pattern.sub(" ", cleaned)
    cleaned = re.sub(
        r"(컴백|신보\s*발매|새\s*앨범|발매\s*확정|개최|발표|오픈|"
        r"일정\s*공개|출사표|카운트다운)",
        " ",
        cleaned,
        flags=re.I,
    )
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -–—|,·")
    if cleaned and len(cleaned) >= 3 and not NOISY_EVENT_WORDS.match(cleaned):
        return cleaned[:120]
    if notice.activity_type == "CONCERT" and re.search(
        r"팬콘|팬\s*콘서트", title, re.I
    ):
        return f"{notice.artist} 팬콘서트"
    label = {
        "COMEBACK": "컴백",
        "CONCERT": "콘서트",
        "TOUR_ANNOUNCEMENT": "투어",
        "TOUR_EXPANSION": "투어 추가 일정",
        "ADDITIONAL_SHOW": "추가 공연",
        "ENCORE": "앙코르 콘서트",
        "FANMEETING": "팬미팅",
        "POPUP": "팝업스토어",
    }.get(notice.activity_type, "활동")
    return f"{notice.artist} {label}"


def parse_event_fields(notice: Notice) -> Notice:
    title = re.sub(r"<[^>]+>", " ", notice.title)
    title = re.sub(r"\s+", " ", title).strip()
    body = re.sub(r"<[^>]+>", " ", notice.body or "")
    body = re.sub(r"\s+", " ", body).strip()
    full_text = f"{title} {body}".strip()

    reference = notice.published_at or notice.fetched_at
    if reference.tzinfo:
        reference = reference.astimezone(ZoneInfo("Asia/Seoul"))
    reference_date = reference.date()

    title_candidates = _extract_candidates(
        title,
        reference_date=reference_date,
        activity_type=notice.activity_type,
        source="TITLE",
    )
    body_candidates = _extract_candidates(
        body,
        reference_date=reference_date,
        activity_type=notice.activity_type,
        source="BODY",
    )
    chosen, conflict = _select_candidate(title_candidates, body_candidates)

    notice.event_name = extract_event_name(notice, full_text)
    notice.event_dates = []
    notice.event_start_date = ""
    notice.event_end_date = ""
    notice.event_is_range = False
    notice.date_conflict = conflict
    notice.date_confidence = "CONFLICT" if conflict else "NONE"
    notice.date_evidence = ""
    notice.date_source = ""

    if chosen:
        notice.event_dates = _date_span(chosen.start, chosen.end)
        notice.event_start_date = chosen.start.isoformat()
        notice.event_end_date = chosen.end.isoformat()
        notice.event_is_range = chosen.start != chosen.end
        notice.date_confidence = (
            "HIGH" if chosen.score >= 85
            else "MEDIUM" if chosen.score >= 55
            else "LOW"
        )
        notice.date_evidence = chosen.evidence
        notice.date_source = chosen.source

    notice.cities = sorted(
        {
            canonical
            for canonical, aliases in CITY_ALIASES.items()
            if any(alias.lower() in f" {full_text.lower()} " for alias in aliases)
        }
    )
    notice.venues = sorted(
        {
            value
            for value in (_clean_venue(x) for x in VENUE_RE.findall(full_text))
            if 2 <= len(value) <= 60
        }
    )
    return notice
