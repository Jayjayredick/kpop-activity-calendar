from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


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
        canonical = canonical_url.split("#", 1)[0].split("?", 1)[0].rstrip("/")
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

        canonical_url = (self.original_url or self.url).split("#", 1)[0].split("?", 1)[0]
        anchor = re.sub(r"\W+", "", self.event_name or self.title).lower()
        value = f"{self.artist_id}|{anchor}|{canonical_url}"
        return hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]
