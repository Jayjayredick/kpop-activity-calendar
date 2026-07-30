from __future__ import annotations

import re
from calendar import monthrange
from datetime import date, datetime
from zoneinfo import ZoneInfo

from .models import Notice


DATE_PATTERNS = [
    re.compile(r"\b(20\d{2})[.\-/년]\s*(\d{1,2})[.\-/월]\s*(\d{1,2})일?\b"),
    re.compile(r"\b(20\d{2})\s*(?:년)?\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일\b"),
]
MONTH_DAY_RANGE = re.compile(
    r"\b(\d{1,2})\s*월\s*(\d{1,2})\s*(?:일)?\s*(?:부터|[~～\-–—])\s*(\d{1,2})\s*일(?:까지)?"
)
CROSS_MONTH_RANGE = re.compile(
    r"\b(\d{1,2})\s*월\s*(\d{1,2})\s*일?\s*(?:부터|[~～\-–—])\s*"
    r"(\d{1,2})\s*월\s*(\d{1,2})\s*일(?:까지)?"
)
RELATIVE_CROSS_MONTH_RANGE = re.compile(
    r"(?:오는\s*)?(\d{1,2})\s*일\s*(?:부터|[~～\-–—])\s*"
    r"(?:내달|다음\s*달)\s*(\d{1,2})\s*일(?:까지)?"
)
MONTH_DAY = re.compile(r"(?<!\d)(\d{1,2})\s*월\s*(\d{1,2})\s*일")
NEXT_MONTH_DAY = re.compile(r"(?:내달|다음\s*달)\s*(\d{1,2})\s*일")

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

CONTEXTUAL_EVENT_NAME = re.compile(
    r"(?:정규\s*\d*집|미니\s*\d*집|싱글|앨범|신보|투어|콘서트|팬콘|"
    r"팬\s*콘서트|팬미팅|팝업(?:스토어)?)"
    r"[^'\"‘’“”<>\[\]]{0,28}['\"‘’“”<\[]\s*"
    r"([^'\"‘’“”<>\[\]]{2,100})\s*['\"‘’“”>\]]",
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


def _date_span(start: date, end: date) -> list[str]:
    from datetime import timedelta

    if end < start or (end - start).days > 45:
        return []
    return [
        (start + timedelta(days=offset)).isoformat()
        for offset in range((end - start).days + 1)
    ]


def _clean_venue(value: str) -> str:
    value = re.sub(r"\s+", " ", value).strip(" -–—,·")
    # 정규식이 앞 문장의 서술부까지 잡지 않도록 마지막 쉼표·마침표 뒤만 유지한다.
    parts = re.split(r"[,.]|(?:에서|으로|에서의)\s+", value)
    candidate = parts[-1].strip() if parts else value
    if len(candidate) < 2:
        candidate = value
    if "까지" in candidate:
        candidate = candidate.split("까지", 1)[1].strip()
    candidate = re.sub(
        r"^.*?\d{1,2}\s*일(?:부터|까지)?\s*",
        "",
        candidate,
    )
    candidate = re.sub(
        r"^(?:서울|부산|인천|도쿄|오사카|나고야|후쿠오카|타이베이|"
        r"홍콩|마카오|방콕|싱가포르|자카르타|마닐라|뉴욕|런던|파리)\s+",
        "",
        candidate,
        flags=re.I,
    )
    return candidate


def extract_event_name(notice: Notice, text: str) -> str:
    title = re.sub(r"\s+", " ", notice.title).strip()
    contextual = [
        re.sub(r"\s+", " ", value).strip()
        for value in CONTEXTUAL_EVENT_NAME.findall(title)
        if not NOISY_EVENT_WORDS.match(value.strip())
    ]
    if contextual:
        # 제목 앞쪽에서 활동 키워드와 직접 연결된 이름을 우선한다.
        return contextual[0][:120]

    release_match = UNQUOTED_RELEASE_NAME.search(title)
    if release_match:
        return release_match.group(1).strip()[:120]

    tour_match = TOUR_NAME.search(title)
    if tour_match:
        value = re.sub(r"\s+", " ", tour_match.group(1)).strip(" -–—,·")
        if len(value) >= 3:
            return value[:120]

    # 따옴표가 있더라도 팬콘 기사 속 신곡명처럼 활동명과 관계없는 경우는 채택하지 않는다.
    cleaned = title.split("…", 1)[0].split("...", 1)[0]
    for alias in [notice.matched_artist_alias, notice.artist]:
        if alias:
            cleaned = re.sub(re.escape(alias), " ", cleaned, flags=re.I)
    cleaned = re.sub(
        r"(컴백|신보\s*발매|새\s*앨범|발매\s*확정|개최|발표|오픈|"
        r"일정\s*공개|출사표|카운트다운)",
        " ",
        cleaned,
        flags=re.I,
    )
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -–—|,·")
    if not cleaned or len(cleaned) < 3:
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
    return cleaned[:120]


def parse_event_fields(notice: Notice) -> Notice:
    text = re.sub(r"<[^>]+>", " ", f"{notice.title} {notice.body}")
    text = re.sub(r"\s+", " ", text).strip()
    dates: set[str] = set()
    for pattern in DATE_PATTERNS:
        for year, month, day in pattern.findall(text):
            try:
                dates.add(datetime(int(year), int(month), int(day)).date().isoformat())
            except ValueError:
                continue
    reference = notice.published_at or notice.fetched_at
    if reference.tzinfo:
        reference = reference.astimezone(ZoneInfo("Asia/Seoul"))
    reference_date = reference.date()
    explicit_ranges: list[tuple[date, date]] = []

    def infer_year(month: int, day: int) -> int:
        year = reference_date.year
        try:
            candidate = date(year, month, day)
        except ValueError:
            return year
        # 기사 시점보다 한 달 이상 과거면 다음 해 일정으로 해석한다.
        if candidate < reference_date and (reference_date - candidate).days > 31:
            year += 1
        return year

    without_ranges = text
    for start_month, start_day, end_month, end_day in CROSS_MONTH_RANGE.findall(text):
        sm, sd, em, ed = map(int, (start_month, start_day, end_month, end_day))
        start_year = infer_year(sm, sd)
        end_year = start_year + (1 if em < sm else 0)
        try:
            start_date = date(start_year, sm, sd)
            end_date = date(end_year, em, ed)
        except ValueError:
            continue
        values = _date_span(start_date, end_date)
        if values:
            dates.update(values)
            explicit_ranges.append((start_date, end_date))
    without_ranges = CROSS_MONTH_RANGE.sub(" ", without_ranges)

    for start_day, end_day in RELATIVE_CROSS_MONTH_RANGE.findall(without_ranges):
        sd, ed = int(start_day), int(end_day)
        sm = reference_date.month
        start_year = infer_year(sm, sd)
        em = 1 if sm == 12 else sm + 1
        end_year = start_year + (1 if sm == 12 else 0)
        try:
            start_date = date(start_year, sm, sd)
            end_date = date(end_year, em, ed)
        except ValueError:
            continue
        values = _date_span(start_date, end_date)
        if values:
            dates.update(values)
            explicit_ranges.append((start_date, end_date))
    without_ranges = RELATIVE_CROSS_MONTH_RANGE.sub(" ", without_ranges)

    for month, start_day, end_day in MONTH_DAY_RANGE.findall(without_ranges):
        month_i, start_i, end_i = int(month), int(start_day), int(end_day)
        year = infer_year(month_i, start_i)
        try:
            start_date = date(year, month_i, start_i)
            end_date = date(year, month_i, end_i)
        except ValueError:
            continue
        values = _date_span(start_date, end_date)
        if values:
            dates.update(values)
            explicit_ranges.append((start_date, end_date))
    without_ranges = MONTH_DAY_RANGE.sub(" ", without_ranges)
    for month, day in MONTH_DAY.findall(without_ranges):
        month_i, day_i = int(month), int(day)
        try:
            dates.add(date(infer_year(month_i, day_i), month_i, day_i).isoformat())
        except ValueError:
            continue
    for day in NEXT_MONTH_DAY.findall(text):
        month = 1 if reference_date.month == 12 else reference_date.month + 1
        year = reference_date.year + (1 if reference_date.month == 12 else 0)
        day_i = min(int(day), monthrange(year, month)[1])
        dates.add(date(year, month, day_i).isoformat())
    cities = {
        canonical
        for canonical, aliases in CITY_ALIASES.items()
        if any(alias.lower() in f" {text.lower()} " for alias in aliases)
    }
    venues = {_clean_venue(x) for x in VENUE_RE.findall(text)}
    venues = {value for value in venues if 2 <= len(value) <= 60}

    notice.event_name = extract_event_name(notice, text)
    notice.event_dates = sorted(dates)
    if explicit_ranges:
        # 같은 기사에 복수 구간이 있으면 가장 앞선 구간을 대표 범위로 보존한다.
        start_date, end_date = sorted(explicit_ranges)[0]
        notice.event_start_date = start_date.isoformat()
        notice.event_end_date = end_date.isoformat()
        notice.event_is_range = start_date != end_date
    elif len(dates) == 1:
        single = next(iter(dates))
        notice.event_start_date = single
        notice.event_end_date = single
        notice.event_is_range = False
    notice.cities = sorted(cities)
    notice.venues = sorted(venues)
    return notice
