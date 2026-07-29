from __future__ import annotations

import json
import re
from datetime import datetime
from urllib.parse import urljoin

import dateparser
from bs4 import BeautifulSoup

from ..models import Artist, Notice, Source
from .base import BaseAdapter


DATE_RE = re.compile(r"(20\d{2})[.\-/년]\s*(\d{1,2})[.\-/월]\s*(\d{1,2})")


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _parse_date(text: str) -> datetime | None:
    match = DATE_RE.search(text or "")
    if match:
        return datetime(int(match[1]), int(match[2]), int(match[3]))
    parsed = dateparser.parse(
        text or "",
        languages=["ko", "en", "ja"],
        settings={"RETURN_AS_TIMEZONE_AWARE": False},
    )
    return parsed


def _artist_for_text(
    artists: list[Artist], text: str, *, single_source_fallback: bool = False
) -> list[Artist]:
    lower = text.lower()
    hits = [
        artist
        for artist in artists
        if any(alias.lower() in lower for alias in [artist.name, *artist.aliases])
    ]
    if hits:
        return hits
    if single_source_fallback and len(artists) == 1:
        return artists
    return []


class GenericHtmlAdapter(BaseAdapter):
    """Configurable list/detail parser with conservative official-link discovery."""

    def collect(
        self, source: Source, artists: list[Artist], fetched_at: datetime
    ) -> list[Notice]:
        response = self.get(source.url)
        soup = BeautifulSoup(response.text, "html.parser")
        options = source.options
        link_pattern = re.compile(
            options.get("link_pattern", r"(notice|newsroom|news|report|post|detail)"),
            re.I,
        )
        selectors = options.get("item_selectors", ["article", "li", ".post", ".item"])
        nodes = []
        for selector in selectors:
            nodes.extend(soup.select(selector))

        seen: set[str] = set()
        notices: list[Notice] = []
        for node in nodes:
            anchor = node.select_one("a[href]")
            if not anchor:
                continue
            url = urljoin(source.url, anchor.get("href", ""))
            if not link_pattern.search(url):
                continue
            title = _clean(anchor.get_text(" ", strip=True) or node.get_text(" ", strip=True))
            if len(title) < 4 or url in seen:
                continue
            seen.add(url)
            node_text = _clean(node.get_text(" ", strip=True))
            published = _parse_date(node_text)
            body = node_text
            try:
                detail = BeautifulSoup(self.get(url).text, "html.parser")
                body_node = detail.select_one(options.get("body_selector", "article, main, .content, .view_cont"))
                if body_node:
                    body = _clean(body_node.get_text(" ", strip=True))
                if not published:
                    time_node = detail.select_one("time, .date, .datetime")
                    published = _parse_date(time_node.get_text(" ", strip=True) if time_node else "")
            except Exception:
                pass

            matched_artists = _artist_for_text(
                artists,
                f"{title} {body}",
                single_source_fallback=source.scope == "artist",
            )
            for artist in matched_artists:
                notices.append(
                    Notice(
                        source_id=source.source_id,
                        source_name=source.name,
                        company=artist.company,
                        label=artist.label,
                        artist_id=artist.artist_id,
                        artist=artist.name,
                        title=title,
                        url=url,
                        published_at=published,
                        body=body,
                        fetched_at=fetched_at,
                    )
                )
        return notices


class WeverseNoticeAdapter(GenericHtmlAdapter):
    """Weverse notice list parser, including links embedded in Next.js JSON."""

    def collect(
        self, source: Source, artists: list[Artist], fetched_at: datetime
    ) -> list[Notice]:
        response = self.get(source.url)
        soup = BeautifulSoup(response.text, "html.parser")
        links: set[str] = set()
        for anchor in soup.select('a[href*="/notice/"]'):
            links.add(urljoin(source.url, anchor.get("href", "")))
        for script in soup.select("script"):
            raw = script.string or ""
            for match in re.findall(r'https?:\\/\\/weverse\\.io\\/[^"\\\\]+\\/notice\\/\\d+', raw):
                links.add(match.replace("\\/", "/"))
            for match in re.findall(r'\\/[^"\\\\]+\\/notice\\/\\d+', raw):
                links.add(urljoin("https://weverse.io", match.replace("\\/", "/")))

        notices: list[Notice] = []
        for url in sorted(links):
            try:
                detail = BeautifulSoup(self.get(url).text, "html.parser")
            except Exception:
                continue
            title = _clean(
                (detail.select_one("h1") or detail.select_one('meta[property="og:title"]') or detail.title).get_text(" ", strip=True)
                if (detail.select_one("h1") or detail.title)
                else ""
            )
            if not title:
                meta = detail.select_one('meta[property="og:title"]')
                title = _clean(meta.get("content", "") if meta else "")
            body_node = detail.select_one("article, main")
            body = _clean(body_node.get_text(" ", strip=True) if body_node else detail.get_text(" ", strip=True))
            time_node = detail.select_one("time")
            published = _parse_date(time_node.get("datetime", "") if time_node else body[:200])
            for artist in artists:
                notices.append(
                    Notice(
                        source_id=source.source_id,
                        source_name=source.name,
                        company=artist.company,
                        label=artist.label,
                        artist_id=artist.artist_id,
                        artist=artist.name,
                        title=title,
                        url=url,
                        published_at=published,
                        body=body,
                        fetched_at=fetched_at,
                        notice_id=url.rstrip("/").split("/")[-1],
                    )
                )
        return notices


class JypNoticeAdapter(GenericHtmlAdapter):
    pass
