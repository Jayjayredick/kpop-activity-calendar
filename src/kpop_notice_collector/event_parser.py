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
    r"\b(\d{1,2})\s*월\s*(\d{1,2})\s*(?:일)?\s*[~～\-–—]\s*(\d{1,2})\s*일"
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
    r"([A-Za-z0-9&.'’\-\s가-힣]{2,60}?"
    r"(?:stadium|arena|dome|hall|theatre|theater|center|centre|"
    r"스타디움|아레나|돔|홀|체육관|공연장))",
    re.I,
)


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

    for month, start_day, end_day in MONTH_DAY_RANGE.findall(text):
        month_i, start_i, end_i = int(month), int(start_day), int(end_day)
        year = infer_year(month_i, start_i)
        for day_i in range(start_i, end_i + 1):
            try:
                dates.add(date(year, month_i, day_i).isoformat())
            except ValueError:
                continue
    without_ranges = MONTH_DAY_RANGE.sub(" ", text)
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
    venues = {re.sub(r"\s+", " ", x).strip(" -–—") for x in VENUE_RE.findall(text)}

    event_name = notice.title
    event_name = re.sub(
        r"\[(?:공지|notice)\]|\((?:공지|notice)\)|"
        r"(추가\s*(?:회차|공연|일정)|컴백|신보\s*발매|개최|발표|오픈)",
        " ",
        event_name,
        flags=re.I,
    )
    event_name = re.sub(r"\s+", " ", event_name).strip(" -–—|")

    notice.event_name = event_name[:180]
    notice.event_dates = sorted(dates)
    notice.cities = sorted(cities)
    notice.venues = sorted(venues)
    return notice
