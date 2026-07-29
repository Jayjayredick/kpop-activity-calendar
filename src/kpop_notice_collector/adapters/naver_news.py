from __future__ import annotations

import html
import os
import re
from datetime import datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse

from ..models import Artist, Notice
from .base import BaseAdapter


API_URL = "https://naverapihub.apigw.ntruss.com/search/v1/news"


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", value or ""))).strip()


def _domain(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def search_names(artist: Artist, limit: int = 2) -> list[str]:
    candidates = [re.sub(r"\s*\([^)]*\)", "", artist.name).strip()]
    korean = next((a for a in artist.aliases if re.search(r"[가-힣]", a)), "")
    if korean:
        candidates.append(korean)
    candidates.extend(artist.aliases)
    result: list[str] = []
    for value in candidates:
        normalized = value.strip()
        if normalized and normalized.lower() not in {x.lower() for x in result}:
            result.append(normalized)
        if len(result) >= limit:
            break
    return result


class NaverNewsAdapter(BaseAdapter):
    def __init__(
        self,
        *,
        key_id: str | None = None,
        key: str | None = None,
        publisher_scores: dict[str, int] | None = None,
        default_publisher_score: int = 3,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.key_id = key_id or os.getenv("NAVER_API_KEY_ID", "")
        self.key = key or os.getenv("NAVER_API_KEY", "")
        self.publisher_scores = publisher_scores or {}
        self.default_publisher_score = default_publisher_score
        if not self.key_id or not self.key:
            raise RuntimeError(
                "NAVER_API_KEY_ID와 NAVER_API_KEY 환경변수가 필요합니다."
            )

    def collect_query(
        self,
        artist: Artist,
        query: str,
        fetched_at: datetime,
        *,
        display: int = 100,
        start: int = 1,
        sort: str = "date",
    ) -> list[Notice]:
        response = self.session.get(
            API_URL,
            params={
                "query": query,
                "display": max(1, min(display, 100)),
                "start": max(1, min(start, 1000)),
                "sort": sort,
            },
            headers={
                "X-NCP-APIGW-API-KEY-ID": self.key_id,
                "X-NCP-APIGW-API-KEY": self.key,
                "User-Agent": "KpopActivityTracker/2.0",
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        items = response.json().get("items", [])
        notices: list[Notice] = []
        for item in items:
            original = item.get("originallink") or item.get("link") or ""
            naver_link = item.get("link") or ""
            domain = _domain(original)
            published = None
            try:
                published = parsedate_to_datetime(item.get("pubDate", ""))
            except (TypeError, ValueError):
                pass
            description = _clean(item.get("description", ""))
            title = _clean(item.get("title", ""))
            notices.append(
                Notice(
                    source_id="naver_news",
                    source_name="NAVER 뉴스 검색",
                    source_type="NAVER_NEWS",
                    company=artist.company,
                    label=artist.label,
                    artist_id=artist.artist_id,
                    artist=artist.name,
                    title=title,
                    url=original or naver_link,
                    original_url=original,
                    naver_url=naver_link,
                    published_at=published,
                    body=description,
                    clipped_text=description,
                    fetched_at=fetched_at,
                    publisher=domain,
                    publisher_score=self.publisher_scores.get(
                        domain, self.default_publisher_score
                    ),
                    search_query=query,
                    raw=item,
                )
            )
        return notices

    def collect(self, source, artists, fetched_at):
        raise NotImplementedError("NAVER 뉴스는 collect_query()를 사용합니다.")
