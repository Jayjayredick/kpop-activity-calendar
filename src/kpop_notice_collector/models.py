from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


TRACKING_QUERY_KEYS = {
    "fbclid",
    "gclid",
    "dclid",
    "msclkid",
    "mc_cid",
    "mc_eid",
    "igshid",
    "referrer",
}


def canonicalize_url(value: str) -> str:
    """추적 파라미터만 제거하고 기사 식별 파라미터는 보존한다."""
    value = (value or "").strip()
    if not value:
        return ""
    try:
        parsed = urlsplit(value)
    except ValueError:
        return value.split("#", 1)[0]
    if not parsed.scheme or not parsed.netloc:
        return value.split("#", 1)[0]

    hostname = (parsed.hostname or "").lower()
    try:
        port = parsed.port
    except ValueError:
        return value.split("#", 1)[0]
    default_port = (
        (parsed.scheme.lower() == "http" and port == 80)
        or (parsed.scheme.lower() == "https" and port == 443)
    )
    netloc = hostname if not port or default_port else f"{hostname}:{port}"
    if parsed.username:
        credentials = parsed.username
        if parsed.password:
            credentials += f":{parsed.password}"
        netloc = f"{credentials}@{netloc}"

    query = [
        (key, item)
        for key, item in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.casefold().startswith("utm_")
        and key.casefold() not in TRACKING_QUERY_KEYS
    ]
    query.sort(key=lambda pair: (pair[0].casefold(), pair[1]))
    path = parsed.path.rstrip("/") or "/"
    return urlunsplit(
        (parsed.scheme.lower(), netloc, path, urlencode(query, doseq=True), "")
    )


@dataclass(frozen=True)
class Artist:
    artist_id: str
    company: str
    label: str
    name: str
    aliases: list[str]
    official_url: str
    source_ids: list[str]


@dataclass(frozen=True)
class Source:
    source_id: str
    scope: str
    company: str
    label: str
    name: str
    url: str
    adapter: str
    official_domain: str
    status: str
    artist_ids: list[str] = field(default_factory=list)
    options: dict[str, Any] = field(default_factory=dict)


@dataclass
class Notice:
    source_id: str
    company: str
    label: str
    artist_id: str
    artist: str
    title: str
    url: str
    published_at: datetime | None
    body: str
    fetched_at: datetime
    source_name: str = ""
    activity_type: str = "OTHER"
    score: int = 0
    matched_keywords: list[str] = field(default_factory=list)
    clipped_text: str = ""
    notice_id: str = ""
    raw: dict[str, Any] = field(default_factory=dict)
    source_type: str = "OFFICIAL"
    original_url: str = ""
    naver_url: str = ""
    publisher: str = ""
    search_query: str = ""
    official_verified: bool = False
    publisher_score: int = 0
    event_name: str = ""
    event_dates: list[str] = field(default_factory=list)
    event_start_date: str = ""
    event_end_date: str = ""
    event_is_range: bool = False
    date_confidence: str = "NONE"
    date_evidence: str = ""
    date_source: str = ""
    date_conflict: bool = False
    cities: list[str] = field(default_factory=list)
    venues: list[str] = field(default_factory=list)
    schedule_status: str = "UNASSESSED"
    previous_event_keys: list[str] = field(default_factory=list)
    validation_status: str = "UNREVIEWED"
    matched_artist_alias: str = ""
    related_urls: list[str] = field(default_factory=list)
    supporting_article_count: int = 1
    review_reason: str = ""
    entity_parent_id: str = ""

    @property
    def dedupe_key(self) -> str:
        import hashlib
        import re

        canonical_url = self.original_url or self.url
        canonical = canonicalize_url(canonical_url)
        normalized_title = re.sub(r"\s+", " ", self.title).strip().lower()
        # 같은 종합 기사에 여러 아티스트가 등장할 수 있으므로 URL만으로 합치지 않는다.
        value = f"{self.artist_id}|{canonical or normalized_title}"
        return hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]

    @property
    def event_key(self) -> str:
        import hashlib
        import re

        date_part = (
            f"{self.event_start_date}:{self.event_end_date}"
            if self.event_start_date
            else ",".join(sorted(self.event_dates))
        )
        city_part = ",".join(sorted(self.cities))
        name = re.sub(r"\W+", "", self.event_name or self.title).lower()
        # 행사명은 같은 날짜의 서로 다른 공연을 분리하고, 날짜가 없는 기사도
        # 앨범명·투어명 기준으로 안정적으로 묶기 위해 항상 포함한다.
        identity = f"{name}|{date_part}|{city_part}"
        value = f"{self.artist_id}|{self.activity_type}|{identity}"
        return hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]

    @property
    def candidate_id(self) -> str:
        """검토 과정에서 날짜·유형이 수정되어도 유지되는 후보 식별자."""
        import hashlib
        import re

        canonical_url = canonicalize_url(self.original_url or self.url)
        fallback = re.sub(r"\W+", "", self.title).lower()
        # 기사 URL이 있으면 파서가 행사명을 더 잘 추출하도록 개선된 뒤에도
        # 같은 검토 후보 ID를 유지한다.
        value = f"{self.artist_id}|{canonical_url or fallback}"
        return hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]
