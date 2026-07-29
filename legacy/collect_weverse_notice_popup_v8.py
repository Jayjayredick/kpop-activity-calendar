#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Weverse Community NOTICE popup collector v8.

Purpose
- Source is ONLY artist-specific Weverse Community NOTICE pages:
  https://weverse.io/{artist_slug}/notice/{notice_id}
- Weverse Shop is NOT used.
- Collect only notices whose TITLE contains popup terms:
  POP-UP / POP UP / POPUP / 팝업 / ポップアップ
- Exclude secondary/update/guide/correction notices by TITLE by default.
- One accepted Weverse NOTICE = one Excel row.
- The FIRST Excel sheet is an analysis-ready table with popup period/location columns.

Supported companies/artists
- HYBE: SEVENTEEN, ENHYPEN, LE SSERAFIM
- YG: TREASURE, BABYMONSTER
- SM: RIIZE, NCT WISH

Recommended fast run:
python collect_weverse_notice_popup_v8.py \
  --company all \
  --start-date 2024-01-01 \
  --end-date 2026-06-29 \
  --use-search \
  --search-results 25 \
  --sleep 0.3 \
  --resume \
  --out weverse_hybe_sm_yg_popup_v8.xlsx

Optional limited sweep run for higher recall:
python collect_weverse_notice_popup_v8.py \
  --company all \
  --start-date 2024-01-01 \
  --end-date 2026-06-29 \
  --use-search \
  --search-results 20 \
  --sweep-min 16800 \
  --sweep-max 37000 \
  --sleep 0.3 \
  --resume \
  --out weverse_hybe_sm_yg_popup_v8_full.xlsx
"""

from __future__ import annotations

import argparse
import html as html_lib
import json
import re
import sys
import time
from dataclasses import dataclass, asdict
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

import pandas as pd
import requests
from bs4 import BeautifulSoup

try:
    import dateparser
except ImportError:
    dateparser = None


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7,ja;q=0.6",
}

ARTISTS: dict[str, dict[str, Any]] = {
    # HYBE
    "seventeen": {
        "company_group": "HYBE",
        "community_slug": "seventeen",
        "company": "PLEDIS Entertainment/HYBE",
        "group": "SEVENTEEN",
        "artist_terms": ["seventeen", "svt", "세븐틴", "セブンティーン"],
    },
    "enhypen": {
        "company_group": "HYBE",
        "community_slug": "enhypen",
        "company": "BELIFT LAB/HYBE",
        "group": "ENHYPEN",
        "artist_terms": ["enhypen", "엔하이픈", "エンハイプン"],
    },
    "lesserafim": {
        "company_group": "HYBE",
        "community_slug": "lesserafim",
        "company": "SOURCE MUSIC/HYBE",
        "group": "LE SSERAFIM",
        "artist_terms": ["le sserafim", "lesserafim", "르세라핌", "ルセラフィム"],
    },
    # YG
    "treasure": {
        "company_group": "YG",
        "community_slug": "treasure",
        "company": "YG Entertainment",
        "group": "TREASURE",
        "artist_terms": ["treasure", "트레저", "トレジャー"],
    },
    "babymonster": {
        "company_group": "YG",
        "community_slug": "babymonster",
        "company": "YG Entertainment",
        "group": "BABYMONSTER",
        "artist_terms": ["babymonster", "baby monster", "베이비몬스터", "베몬", "ベイビーモンスター"],
    },
    # SM
    "riize": {
        "company_group": "SM",
        "community_slug": "riize",
        "company": "SM Entertainment",
        "group": "RIIZE",
        "artist_terms": ["riize", "라이즈", "ライズ"],
    },
    "nctwish": {
        "company_group": "SM",
        "community_slug": "nctwish",
        "company": "SM Entertainment",
        "group": "NCT WISH",
        "artist_terms": ["nct wish", "nctwish", "엔시티 위시", "エヌシーティーウィッシュ"],
    },
}

COMPANY_CHOICES = ["all", "hybe", "sm", "yg"]

# Positive title filter. Only these notices are accepted.
TITLE_POPUP_RE = re.compile(r"(pop\s*[-–—]?\s*up|popup|팝업|ポップアップ)", flags=re.I)

# Default negative title filter. User requested not to collect correction/update notices.
SECONDARY_TITLE_RE = re.compile(
    r"("
    r"update|updated|amend|amended|correction|corrected|change|changed|schedule\s+confirmed|opening\s+schedule|"
    r"postpone|postponed|cancel|cancelled|canceled|cancellation|"
    r"t\s*&\s*c|terms\s+(and|&)\s+conditions|terms\s+conditions|"
    r"visitor'?s?\s+guide|visit\s+guide|operating\s+guide|operation\s+guide|operating\s+guidelines|"
    r"reservation\s+guide|pickup\s+guide|pickup\s+reservation|"
    r"변경|수정|정정|추가\s*안내|일정\s*확정|일정\s*변경|운영\s*시간\s*변경|연기|취소|"
    r"利用規約|規約|変更|修正|訂正|延期|中止|追加\s*案内|追加のお知らせ|"
    r"予約|受取|ピックアップ"
    r")",
    flags=re.I,
)

PRODUCT_WORDS = [
    "t-shirt", "tee", "hoodie", "sweatshirt", "shirt", "pants", "shorts", "jacket",
    "cap", "beanie", "hat", "bag", "pouch", "tote", "keyring", "key ring", "acrylic stand",
    "photocard", "photo card", "postcard", "poster", "sticker", "badge", "pin", "magnet",
    "doll", "plush", "cushion", "blanket", "towel", "light stick", "binder", "mirror", "strap",
    "티셔츠", "후드", "후디", "셔츠", "팬츠", "자켓", "재킷", "캡", "모자", "비니", "백", "가방", "파우치",
    "키링", "포토카드", "포카", "엽서", "포스터", "스티커", "뱃지", "배지", "핀", "인형", "쿠션", "담요", "타월", "응원봉",
]

CITY_COUNTRY_MAP = {
    "the hyundai seoul": ("한국", "서울 더현대서울"), "더현대서울": ("한국", "서울 더현대서울"),
    "hyundai department store sinchon": ("한국", "서울 현대백화점 신촌"), "현대백화점 신촌": ("한국", "서울 현대백화점 신촌"),
    "lotte world mall": ("한국", "서울 잠실 롯데월드몰"), "롯데월드몰": ("한국", "서울 잠실 롯데월드몰"),
    "shinsegae gangnam": ("한국", "서울 신세계백화점 강남"), "신세계백화점 강남": ("한국", "서울 신세계백화점 강남"),
    "seoul": ("한국", "서울"), "서울": ("한국", "서울"),
    "hongdae": ("한국", "서울 홍대"), "홍대": ("한국", "서울 홍대"),
    "yongsan": ("한국", "서울 용산"), "용산": ("한국", "서울 용산"),
    "seongsu": ("한국", "서울 성수"), "sungsu": ("한국", "서울 성수"), "성수": ("한국", "서울 성수"),
    "jamsil": ("한국", "서울 잠실"), "잠실": ("한국", "서울 잠실"),
    "gangnam": ("한국", "서울 강남"), "강남": ("한국", "서울 강남"),
    "daegu": ("한국", "대구"), "대구": ("한국", "대구"), "exco": ("한국", "대구 EXCO"),
    "busan": ("한국", "부산"), "부산": ("한국", "부산"),
    "incheon": ("한국", "인천"), "인천": ("한국", "인천"),
    "goyang": ("한국", "고양"), "고양": ("한국", "고양"),
    "tokyo": ("일본", "도쿄"), "東京": ("일본", "도쿄"), "shibuya": ("일본", "도쿄 시부야"), "渋谷": ("일본", "도쿄 시부야"),
    "osaka": ("일본", "오사카"), "大阪": ("일본", "오사카"),
    "nagoya": ("일본", "나고야"), "名古屋": ("일본", "나고야"),
    "fukuoka": ("일본", "후쿠오카"), "福岡": ("일본", "후쿠오카"),
    "taipei": ("대만", "타이베이"), "台北": ("대만", "타이베이"),
    "kaohsiung": ("대만", "가오슝"), "高雄": ("대만", "가오슝"),
    "metro manila": ("필리핀", "메트로 마닐라"), "manila": ("필리핀", "마닐라"),
    "hong kong": ("홍콩", "홍콩"), "香港": ("홍콩", "홍콩"),
    "macau": ("마카오", "마카오"), "macao": ("마카오", "마카오"),
    "bangkok": ("태국", "방콕"), "방콕": ("태국", "방콕"),
    "kuala lumpur": ("말레이시아", "쿠알라룸푸르"), "singapore": ("싱가포르", "싱가포르"), "jakarta": ("인도네시아", "자카르타"),
    "sydney": ("호주", "시드니"), "melbourne": ("호주", "멜버른"),
    "los angeles": ("미국", "로스앤젤레스"), "culver city": ("미국", "로스앤젤레스 컬버시티"),
    "orange county": ("미국", "오렌지카운티"), "buena park": ("미국", "오렌지카운티 부에나파크"),
    "new york": ("미국", "뉴욕"), "chicago": ("미국", "시카고"),
    "london": ("영국", "런던"), "paris": ("프랑스", "파리"), "berlin": ("독일", "베를린"),
}


@dataclass
class NoticeRaw:
    artist: str
    company_group: str
    source_type: str
    url: str
    notice_id: str
    title: str
    body: str
    fetched_at: str
    http_status: int
    fetch_error: str = ""
    search_title: str = ""
    search_body: str = ""
    extraction_method: str = ""


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def clean_title(title: str) -> str:
    t = normalize_space(title)
    t = re.sub(r"^#+\s*", "", t)
    t = re.sub(r"^\[NOTICE\]\s*", "", t, flags=re.I)
    t = re.sub(r"\s+N$", "", t)
    t = re.sub(r"\s*Weverse\s*$", "", t, flags=re.I)
    return normalize_space(t)


def is_generic_weverse_title(title: str) -> bool:
    t = normalize_space(title).lower().strip(" -|_")
    generic = {
        "global fandom platform",
        "global fandom platform -",
        "global fandom platform - weverse",
        "weverse",
    }
    return (not t) or t in generic or t.startswith("global fandom platform")


def clean_html_text(value: str) -> str:
    if not value:
        return ""
    # Decode escaped unicode/HTML entities and remove HTML tags if present.
    value = html_lib.unescape(str(value))
    try:
        # Some JSON strings arrive double-escaped.
        value = value.encode("utf-8", errors="ignore").decode("unicode_escape", errors="ignore")
    except Exception:
        pass
    return normalize_space(BeautifulSoup(value, "html.parser").get_text(" ", strip=True))


def _decode_json_string(raw: str) -> str:
    if raw is None:
        return ""
    try:
        return json.loads('"' + raw + '"')
    except Exception:
        return clean_html_text(raw)


def _walk_json_for_text(obj: Any, title_candidates: list[str], body_candidates: list[str], parent_key: str = "") -> None:
    title_keys = {"title", "subject", "name", "noticeTitle", "notice_title", "postTitle", "post_title"}
    body_keys = {"body", "content", "contents", "description", "text", "message", "noticeBody", "notice_body", "postBody", "post_body"}
    if isinstance(obj, dict):
        for k, v in obj.items():
            key = str(k)
            if isinstance(v, (dict, list)):
                _walk_json_for_text(v, title_candidates, body_candidates, key)
            elif isinstance(v, str):
                cleaned = clean_html_text(v)
                if not cleaned:
                    continue
                if key in title_keys and not is_generic_weverse_title(cleaned):
                    title_candidates.append(cleaned)
                if key in body_keys:
                    body_candidates.append(cleaned)
                # Fallback: script JSON may use unknown keys. Preserve strings containing useful markers.
                if TITLE_POPUP_RE.search(cleaned) or re.search(r"운영\s*기간|DATE\s*:|LOCATION\s*:|Operating\s+Period|Event\s+Period|開催期間|場所", cleaned, re.I):
                    body_candidates.append(cleaned)
    elif isinstance(obj, list):
        for item in obj:
            _walk_json_for_text(item, title_candidates, body_candidates, parent_key)


def extract_script_text_candidates(soup: BeautifulSoup) -> tuple[list[str], list[str]]:
    title_candidates: list[str] = []
    body_candidates: list[str] = []
    marker_re = re.compile(r"(pop\s*[-–—]?\s*up|popup|팝업|ポップアップ|운영\s*기간|DATE\s*:|LOCATION\s*:|Operating\s+Period|Event\s+Period|開催期間|場所)", re.I)

    for script in soup.find_all("script"):
        txt = script.string or script.get_text(" ", strip=False) or ""
        if not txt:
            continue

        # 1) Parse JSON scripts such as __NEXT_DATA__ or application/json.
        if script.get("type") in {"application/json", "application/ld+json"} or script.get("id") in {"__NEXT_DATA__", "__NUXT_DATA__"}:
            try:
                obj = json.loads(txt)
                _walk_json_for_text(obj, title_candidates, body_candidates)
            except Exception:
                pass

        # 2) Generic regex extraction for embedded JSON values.
        for key in ["title", "subject", "name", "noticeTitle", "postTitle"]:
            pat = rf'"{key}"\s*:\s*"((?:\\\\.|[^"\\\\])*)"'
            for m in re.finditer(pat, txt):
                val = clean_html_text(_decode_json_string(m.group(1)))
                if val and not is_generic_weverse_title(val):
                    title_candidates.append(val)

        for key in ["body", "content", "contents", "description", "text", "message", "noticeBody", "postBody"]:
            pat = rf'"{key}"\s*:\s*"((?:\\\\.|[^"\\\\])*)"'
            for m in re.finditer(pat, txt):
                val = clean_html_text(_decode_json_string(m.group(1)))
                if val:
                    body_candidates.append(val)

        # 3) Last fallback: keep snippets around popup/date/location markers in raw script text.
        if marker_re.search(txt):
            for m in marker_re.finditer(txt):
                st = max(0, m.start() - 1200)
                en = min(len(txt), m.end() + 2400)
                snip = clean_html_text(txt[st:en])
                if snip:
                    body_candidates.append(snip)

    # De-duplicate while preserving order.
    def dedup(items: list[str]) -> list[str]:
        out, seen = [], set()
        for x in items:
            x = normalize_space(x)
            if x and x not in seen:
                seen.add(x)
                out.append(x)
        return out

    return dedup(title_candidates), dedup(body_candidates)


def parse_notice_id(url: str) -> str:
    m = re.search(r"/notice/(\d+)", url)
    return m.group(1) if m else ""


def canonicalize_community_url(url: str, artist_cfg: dict[str, Any]) -> str:
    if not url:
        return ""
    parsed = urlparse(url)
    # Only accept weverse community notice URLs, never shop.weverse.io.
    if parsed.netloc and parsed.netloc != "weverse.io":
        return ""
    if not parsed.netloc:
        return ""
    slug = artist_cfg["community_slug"]
    m = re.search(rf"/({re.escape(slug)})/notice/(\d+)", parsed.path)
    if not m:
        return ""
    return f"https://weverse.io/{slug}/notice/{m.group(2)}"


def make_community_url(artist_cfg: dict[str, Any], notice_id: int) -> str:
    return f"https://weverse.io/{artist_cfg['community_slug']}/notice/{notice_id}"


def request_html(url: str, timeout: int = 20) -> tuple[int, str, str]:
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        return r.status_code, r.text, ""
    except Exception as e:
        return 0, "", repr(e)


def extract_title_and_body(html: str) -> tuple[str, str, str]:
    """Extract title/body from Weverse HTML.

    Weverse often serves a JS shell where visible HTML title is only
    "Global Fandom Platform -". v8 therefore inspects script JSON before
    deleting scripts and uses discovered JSON strings as fallback body/title.
    """
    soup = BeautifulSoup(html, "html.parser")

    json_titles, json_bodies = extract_script_text_candidates(soup)

    title_candidates: list[str] = []
    for tag_name, attrs in [
        ("meta", {"property": "og:title"}),
        ("meta", {"name": "twitter:title"}),
        ("meta", {"name": "title"}),
    ]:
        el = soup.find(tag_name, attrs=attrs)
        if el and el.get("content"):
            title_candidates.append(clean_html_text(el.get("content", "")))

    for selector in ["h1", "h2", "title"]:
        el = soup.find(selector)
        if el:
            title_candidates.append(clean_html_text(el.get_text(" ", strip=True)))

    title_candidates.extend(json_titles)
    title = ""
    for cand in title_candidates:
        cand = clean_title(cand)
        if cand and not is_generic_weverse_title(cand):
            title = cand
            break
    if not title and title_candidates:
        title = clean_title(title_candidates[0])

    # Visible text after removing non-content tags.
    visible_soup = BeautifulSoup(html, "html.parser")
    for tag in visible_soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    visible_body = normalize_space(visible_soup.get_text(" ", strip=True))

    body_parts = []
    if visible_body and visible_body.lower() not in {"global fandom platform - weverse", "global fandom platform weverse", "weverse"}:
        body_parts.append(visible_body)
    body_parts.extend(json_bodies)
    body = normalize_space(" ".join([x for x in body_parts if x]))

    method = "html"
    if json_titles or json_bodies:
        method = "html+script_json"
    if is_generic_weverse_title(title) and not body:
        method = "generic_shell_only"
    return clean_title(title), body, method


def fetch_notice(
    url: str,
    artist: str,
    artist_cfg: dict[str, Any],
    source_type: str,
    sleep_sec: float = 0.0,
    search_title: str = "",
    search_body: str = "",
) -> NoticeRaw:
    if sleep_sec:
        time.sleep(sleep_sec)
    status, html, err = request_html(url)
    title, body, method = ("", "", "")
    if html:
        title, body, method = extract_title_and_body(html)

    search_title_clean = clean_title(search_title)
    search_body_clean = clean_html_text(search_body)

    # Critical v8 fallback: if requests only sees Weverse's JS shell, use search-result
    # title/snippet so popup notices are not discarded as "Global Fandom Platform -".
    if is_generic_weverse_title(title) and search_title_clean:
        title = search_title_clean
        method = (method + "+search_title_fallback").strip("+")

    if (not body or body.lower() in {"global fandom platform - weverse", "global fandom platform weverse", "weverse"}) and (search_title_clean or search_body_clean):
        body = normalize_space(f"{search_title_clean} {search_body_clean}")
        method = (method + "+search_body_fallback").strip("+")
    elif search_body_clean and search_body_clean not in body:
        body = normalize_space(f"{body} {search_body_clean}")
        method = (method + "+search_body_append").strip("+")

    return NoticeRaw(
        artist=artist,
        company_group=artist_cfg["company_group"],
        source_type=source_type,
        url=url,
        notice_id=parse_notice_id(url),
        title=title,
        body=body,
        fetched_at=datetime.now().isoformat(timespec="seconds"),
        http_status=status,
        fetch_error=err,
        search_title=search_title_clean,
        search_body=search_body_clean,
        extraction_method=method,
    )


def build_search_queries(artist_cfg: dict[str, Any], start_year: int, end_year: int) -> list[str]:
    slug = artist_cfg["community_slug"]
    group = artist_cfg["group"]
    popup_terms = ["POP-UP", "POP UP", "popup", "팝업", "ポップアップ"]
    queries: list[str] = []
    for term in popup_terms:
        queries.append(f'site:weverse.io/{slug}/notice intitle:"{term}"')
        queries.append(f'site:weverse.io/{slug}/notice "{term}"')
        queries.append(f'site:weverse.io/{slug}/notice "{group}" "{term}"')
        for y in range(start_year, end_year + 1):
            queries.append(f'site:weverse.io/{slug}/notice "{term}" {y}')
            queries.append(f'site:weverse.io/{slug}/notice "{group}" "{term}" {y}')
    return list(dict.fromkeys(queries))


def discover_search_urls(artist_cfg: dict[str, Any], start: date, end: date, max_results_per_query: int, sleep_sec: float) -> dict[str, dict[str, str]]:
    try:
        from ddgs import DDGS
    except Exception:
        print("[search] ddgs package not installed. Skip search discovery. Install with: pip install ddgs", file=sys.stderr)
        return {}

    slug = artist_cfg["community_slug"]
    queries = build_search_queries(artist_cfg, start.year, end.year)
    urls: dict[str, dict[str, str]] = {}
    with DDGS() as ddgs:
        for i, q in enumerate(queries, start=1):
            print(f"[search] {i}/{len(queries)} {q}")
            try:
                for r in ddgs.text(q, max_results=max_results_per_query):
                    href = r.get("href") or r.get("url") or ""
                    if f"weverse.io/{slug}/notice/" not in href:
                        continue
                    clean = canonicalize_community_url(href, artist_cfg)
                    if not clean:
                        continue
                    st = clean_title(r.get("title") or "")
                    sb = clean_html_text(r.get("body") or r.get("snippet") or r.get("description") or "")
                    if clean not in urls:
                        urls[clean] = {"source_type": "weverse_notice_search", "search_title": st, "search_body": sb}
                    else:
                        urls[clean]["source_type"] = merge_candidate_sources(urls[clean].get("source_type", ""), "weverse_notice_search")
                        if st and not urls[clean].get("search_title"):
                            urls[clean]["search_title"] = st
                        if sb and sb not in urls[clean].get("search_body", ""):
                            urls[clean]["search_body"] = normalize_space(urls[clean].get("search_body", "") + " " + sb)
            except Exception as e:
                print(f"[search] error: {repr(e)}", file=sys.stderr)
            if sleep_sec:
                time.sleep(sleep_sec)
    return urls


def discover_community_sweep_urls(artist_cfg: dict[str, Any], min_id: Optional[int], max_id: Optional[int]) -> dict[str, dict[str, str]]:
    if min_id is None or max_id is None:
        return {}
    if min_id > max_id:
        min_id, max_id = max_id, min_id
    return {make_community_url(artist_cfg, i): {"source_type": "weverse_notice_sweep", "search_title": "", "search_body": ""} for i in range(min_id, max_id + 1)}


def title_has_popup(title: str) -> bool:
    return bool(TITLE_POPUP_RE.search(title or ""))


def title_is_secondary(title: str) -> bool:
    return bool(SECONDARY_TITLE_RE.search(title or ""))


# ---------- Date parsing ----------

def _to_date(y: int, m: int, d: int) -> Optional[date]:
    try:
        return date(y, m, d)
    except ValueError:
        return None


def _parse_with_dateparser(s: str) -> Optional[date]:
    if dateparser is None:
        raise RuntimeError("dateparser is required. Install with: pip install dateparser")
    dt = dateparser.parse(
        s,
        languages=["en", "ko", "ja"],
        settings={"PREFER_DAY_OF_MONTH": "first", "RELATIVE_BASE": datetime(2026, 6, 29)},
    )
    return dt.date() if dt else None


def _strip_weekday_noise(text: str) -> str:
    # Remove weekday/time noise that often breaks regex ranges.
    text = re.sub(r"\((월|화|수|목|금|토|일|Mon|Tue|Wed|Thu|Fri|Sat|Sun|Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\)", " ", text, flags=re.I)
    text = re.sub(r"\b(월|화|수|목|금|토|일)요일\b", " ", text)
    text = re.sub(r"\b(Mon|Tue|Wed|Thu|Fri|Sat|Sun|Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\b", " ", text, flags=re.I)
    return normalize_space(text)


def _extract_period_contexts(text: str) -> list[str]:
    """Return snippets likely to contain actual popup operating period."""
    clean = _strip_weekday_noise(text)
    markers = [
        "운영 기간", "운영기간", "진행 기간", "진행기간", "행사 기간", "행사기간", "팝업 기간", "팝업기간",
        "기간", "일정", "운영 일시", "운영일시", "오픈 기간", "오픈기간",
        "operating period", "operation period", "event period", "popup period", "period", "dates", "date",
        "開催期間", "運営期間", "実施期間", "期間", "日程",
    ]
    snippets: list[str] = []
    lower = clean.lower()
    for marker in markers:
        start = 0
        marker_l = marker.lower()
        while True:
            idx = lower.find(marker_l, start)
            if idx < 0:
                break
            snippets.append(clean[idx: idx + 450])
            start = idx + len(marker)
    # Also include title+first body region as fallback because some notices put period early.
    snippets.append(clean[:2000])
    return list(dict.fromkeys(snippets))


def _dates_from_numeric_ranges(text: str) -> list[tuple[date, date, str]]:
    t = _strip_weekday_noise(text)
    results: list[tuple[date, date, str]] = []

    # 2024.01.12 ~ 2024.01.18 / 2024-01-12 - 2024-01-18
    pat_full = r"(20\d{2})\s*[.\-/년]\s*(\d{1,2})\s*[.\-/월]\s*(\d{1,2})\s*(?:일)?\s*[~\-–—]\s*(20\d{2})\s*[.\-/년]\s*(\d{1,2})\s*[.\-/월]\s*(\d{1,2})\s*(?:일)?"
    for m in re.finditer(pat_full, t):
        s = _to_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        e = _to_date(int(m.group(4)), int(m.group(5)), int(m.group(6)))
        if s and e:
            results.append((s, e, m.group(0)))

    # 2024.01.12 ~ 01.18 / 2024년 1월 12일 ~ 1월 18일
    pat_short = r"(20\d{2})\s*[.\-/년]\s*(\d{1,2})\s*[.\-/월]\s*(\d{1,2})\s*(?:일)?\s*[~\-–—]\s*(\d{1,2})\s*[.\-/월]\s*(\d{1,2})\s*(?:일)?"
    for m in re.finditer(pat_short, t):
        s = _to_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        e = _to_date(int(m.group(1)), int(m.group(4)), int(m.group(5)))
        if s and e:
            results.append((s, e, m.group(0)))

    # 2024.01.12 ~ 18 / 2024년 1월 12일 ~ 18일
    pat_day = r"(20\d{2})\s*[.\-/년]\s*(\d{1,2})\s*[.\-/월]\s*(\d{1,2})\s*(?:일)?\s*[~\-–—]\s*(\d{1,2})\s*(?:일)?"
    for m in re.finditer(pat_day, t):
        s = _to_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        e = _to_date(int(m.group(1)), int(m.group(2)), int(m.group(4)))
        if s and e:
            results.append((s, e, m.group(0)))

    # Single numeric date. Use as one-day period when no range exists.
    pat_single = r"(20\d{2})\s*[.\-/년]\s*(\d{1,2})\s*[.\-/월]\s*(\d{1,2})\s*(?:일)?"
    for m in re.finditer(pat_single, t):
        s = _to_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if s:
            results.append((s, s, m.group(0)))
    return results


def _dates_from_english_ranges(text: str) -> list[tuple[date, date, str]]:
    t = _strip_weekday_noise(text)
    results: list[tuple[date, date, str]] = []
    months = r"Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?"

    # March 7, 2026 - March 17, 2026 / March 7 - March 17, 2026 / March 7 to 17, 2026
    pat = rf"(({months})\.?\s+\d{{1,2}}(?:,\s*20\d{{2}})?)\s*(?:~|-|–|—|to)\s*((?:{months})?\.?\s*\d{{1,2}},\s*20\d{{2}}|\d{{1,2}},\s*20\d{{2}})"
    for m in re.finditer(pat, t, flags=re.I):
        whole = m.group(0)
        year_match = re.search(r"20\d{2}", whole)
        if not year_match:
            continue
        year = year_match.group(0)
        first_raw = m.group(1)
        second_raw = m.group(3)
        first_month = re.search(months, first_raw, flags=re.I)
        second_month = re.search(months, second_raw, flags=re.I)
        if not first_month:
            continue
        if not second_month:
            second_raw = f"{first_month.group(0)} {second_raw}"
        if "20" not in first_raw:
            first_raw = f"{first_raw}, {year}"
        s = _parse_with_dateparser(first_raw)
        e = _parse_with_dateparser(second_raw)
        if s and e:
            results.append((s, e, whole))

    # Single English date.
    single = rf"(?:{months})\.?\s+\d{{1,2}},\s*20\d{{2}}"
    for m in re.finditer(single, t, flags=re.I):
        s = _parse_with_dateparser(m.group(0))
        if s:
            results.append((s, s, m.group(0)))
    return results


def _dates_from_japanese_ranges(text: str) -> list[tuple[date, date, str]]:
    t = _strip_weekday_noise(text)
    results: list[tuple[date, date, str]] = []
    # 2024年1月12日 ~ 2024年1月18日 / 2024年1月12日 ~ 1月18日 / 2024年1月12日 ~ 18日
    results.extend(_dates_from_numeric_ranges(t))
    return results


def _score_period_candidate(s: date, e: date, snippet: str, context_index: int) -> int:
    score = 0
    sl = snippet.lower()
    positive = [
        "운영 기간", "운영기간", "진행 기간", "진행기간", "행사 기간", "행사기간", "팝업 기간", "팝업기간",
        "operating period", "operation period", "event period", "popup period", "開催期間", "運営期間", "実施期間",
    ]
    negative = [
        "reservation", "pickup", "pre-order", "preorder", "online sales", "shipping", "delivery", "refund", "exchange",
        "예약", "수령", "픽업", "배송", "교환", "환불", "온라인", "販売", "予約", "配送", "交換", "返金",
    ]
    if any(p in sl for p in positive):
        score += 100
    if any(n in sl for n in negative):
        score -= 25
    duration = (e - s).days + 1
    if 1 <= duration <= 60:
        score += 20
    elif 61 <= duration <= 120:
        score += 5
    else:
        score -= 30
    # earlier contexts are usually closer to the actual event period.
    score -= context_index
    return score


def parse_event_period(title: str, body: str) -> tuple[str, str, Optional[int], list[str], str]:
    """Return start, end, duration, notes, evidence snippet."""
    if dateparser is None:
        raise RuntimeError("dateparser is required. Install with: pip install dateparser")
    text = f"{title} {body}"
    notes: list[str] = []
    candidates: list[tuple[int, date, date, str]] = []
    contexts = _extract_period_contexts(text)
    for idx, ctx in enumerate(contexts):
        pairs: list[tuple[date, date, str]] = []
        pairs.extend(_dates_from_numeric_ranges(ctx))
        pairs.extend(_dates_from_english_ranges(ctx))
        pairs.extend(_dates_from_japanese_ranges(ctx))
        for s, e, evidence in pairs:
            candidates.append((_score_period_candidate(s, e, ctx, idx), s, e, normalize_space(evidence)))

    # De-duplicate by date pair and evidence.
    seen = set()
    unique: list[tuple[int, date, date, str]] = []
    for item in sorted(candidates, key=lambda x: x[0], reverse=True):
        key = (item[1], item[2], item[3])
        if key not in seen:
            seen.add(key)
            unique.append(item)

    if not unique:
        return "", "", None, ["팝업스토어 기간 자동 추출 실패"], ""

    best_score, s, e, evidence = unique[0]
    duration = (e - s).days + 1
    if duration <= 0:
        notes.append("날짜 역전: 수동 확인 필요")
        duration = None
    elif duration > 120:
        notes.append("진행 일 수 과다: 실제 운영 기간 수동 확인 필요")

    if len(unique) >= 2:
        alt = "; ".join([f"{x[1].isoformat()}~{x[2].isoformat()} ({x[3]})" for x in unique[1:5]])
        if alt:
            notes.append(f"대체 날짜 후보: {alt}")
    notes.append(f"기간 근거: {evidence}; score={best_score}")
    return s.isoformat(), e.isoformat(), duration, notes, evidence


# ---------- Location/product/type parsing ----------

def infer_location(title: str, body: str) -> tuple[str, str, list[str]]:
    text = f"{title} {body}"
    text_lower = text.lower()
    hits: list[tuple[str, str, int]] = []
    notes: list[str] = []
    for key, value in CITY_COUNTRY_MAP.items():
        pos = text_lower.find(key.lower())
        if pos >= 0 or key in text:
            hits.append((value[0], value[1], pos if pos >= 0 else 999999))

    if hits:
        region1, city = sorted(hits, key=lambda x: x[2])[0][:2]
    else:
        region1, city = "", ""
        notes.append("지역 자동 매핑 실패")

    venue = ""
    patterns = [
        r"(?:Location|Venue|Place|Address)\s*[-:：]?\s*([^\[]+?)(?=\s*(?:\[|\*|Important|Payment|How to|Operating|Operation|Period|Dates|$))",
        r"(?:장소|위치|주소)\s*[-:：]?\s*([^\[]+?)(?=\s*(?:\[|\*|유의|안내|운영|기간|일정|$))",
        r"(?:会場|場所|住所)\s*[-:：]?\s*([^\[]+?)(?=\s*(?:\[|\*|注意|期間|$))",
    ]
    for pat in patterns:
        m = re.search(pat, text, flags=re.I)
        if m:
            venue = normalize_space(m.group(1))[:180]
            break
    return region1, venue or city, notes


def estimate_item_count(text: str) -> tuple[Optional[int], str]:
    text_lower = text.lower()
    hits = {w for w in PRODUCT_WORDS if w.lower() in text_lower}
    if not hits:
        return None, "본문 텍스트 기준 품목 수 산출 불가: 이미지 배너/상품 페이지 확인 필요"
    return len(hits), f"상품 키워드 기반 추정치: {sorted(hits)}"


def classify_popup_type(title: str, body: str) -> str:
    text = f"{title} {body}".lower()
    if "artist-made collection" in text or "artist made collection" in text:
        return "아티스트메이드 팝업"
    if "miniteen" in text or "enchin" in text or "official character" in text or "monstiez" in text:
        return "캐릭터/IP 팝업"
    if "the city" in text:
        return "THE CITY 팝업/이벤트"
    if "album" in text or "mini album" in text or "single" in text:
        return "앨범 팝업스토어"
    return "팝업스토어"


def date_overlaps_range(start: str, end: str, range_start: date, range_end: date) -> bool:
    if not start and not end:
        return True
    try:
        s = date.fromisoformat(start) if start else date.fromisoformat(end)
        e = date.fromisoformat(end) if end else date.fromisoformat(start)
    except Exception:
        return True
    return not (e < range_start or s > range_end)


def build_popup_row(raw: NoticeRaw, artist_cfg: dict[str, Any]) -> dict[str, Any]:
    title = clean_title(raw.title)
    body = raw.body
    text = f"{title} {body}"
    notes: list[str] = []
    verify: list[str] = []

    try:
        start_s, end_s, duration, date_notes, date_evidence = parse_event_period(title, body)
        notes.extend(date_notes)
    except Exception as e:
        start_s, end_s, duration, date_evidence = "", "", None, ""
        notes.append(f"기간 파싱 오류: {repr(e)}")

    if not start_s or not end_s:
        verify.append("팝업스토어 기간 확인 필요")
    elif duration is None or (isinstance(duration, int) and duration > 120):
        verify.append("팝업스토어 기간 수동 확인 필요")

    region1, region2, loc_notes = infer_location(title, body)
    notes.extend(loc_notes)
    if not region1 or not region2:
        verify.append("지역/장소 확인 필요")

    item_count, item_note = estimate_item_count(text)
    notes.append(item_note)
    if item_count is None:
        verify.append("품목 수 확인 필요")

    return {
        "소속사": artist_cfg["company"],
        "소속사 구분": artist_cfg["company_group"],
        "그룹명": artist_cfg["group"],
        "종류": classify_popup_type(title, body),
        "행사명": title,
        "지역(1)": region1,
        "지역(2)": region2,
        "시작일": start_s,
        "종료일": end_s,
        "진행 일 수": duration,
        "품목 수": item_count,
        "출처(접속 가능한 URL)": raw.url,
        "notice_id": raw.notice_id,
        "source_type": raw.source_type,
        "공지 제목": title,
        "기간 근거": date_evidence,
        "검증 필요": "; ".join(sorted(set(verify))) if verify else "",
        "파싱 메모": " || ".join(notes),
    }


# ---------- Cache/export ----------

def load_cache(path: Path) -> dict[str, NoticeRaw]:
    cache: dict[str, NoticeRaw] = {}
    if not path.exists():
        return cache
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                d = json.loads(line)
                raw = NoticeRaw(**d)
                cache[raw.url] = raw
            except Exception:
                continue
    return cache


def append_cache(path: Path, raw: NoticeRaw) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(raw), ensure_ascii=False) + "\n")


def export_excel(popup_df: pd.DataFrame, raw_df: pd.DataFrame, excluded_df: pd.DataFrame, params_df: pd.DataFrame, out_path: Path) -> None:
    # Ensure the first sheet is the analysis-ready sheet.
    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        popup_df.to_excel(writer, sheet_name="popup_notices", index=False)
        raw_df.to_excel(writer, sheet_name="raw_notice", index=False)
        excluded_df.to_excel(writer, sheet_name="excluded", index=False)
        params_df.to_excel(writer, sheet_name="run_params", index=False)

        for sheet_name, df in [
            ("popup_notices", popup_df),
            ("raw_notice", raw_df),
            ("excluded", excluded_df),
            ("run_params", params_df),
        ]:
            ws = writer.sheets[sheet_name]
            ws.freeze_panes = "A2"
            if ws.max_row > 1 and ws.max_column > 1:
                ws.auto_filter.ref = ws.dimensions
            for i, col in enumerate(df.columns, start=1):
                letter = ws.cell(row=1, column=i).column_letter
                sample = df[col].head(300).fillna("").astype(str).tolist() if not df.empty else []
                max_len = max([len(str(col))] + [len(x) for x in sample])
                ws.column_dimensions[letter].width = min(max(max_len + 2, 10), 70)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect HYBE/SM/YG artist Weverse Community NOTICE pages whose title contains popup terms. No Weverse Shop collection."
    )
    parser.add_argument("--company", choices=COMPANY_CHOICES, default="all", help="Company group filter. Default: all")
    parser.add_argument("--artist", choices=sorted(ARTISTS.keys()) + ["all"], default="all", help="Artist filter. Default: all artists within --company")
    parser.add_argument("--start-date", default="2024-01-01", help="YYYY-MM-DD. Filters by extracted popup period; unknown-date rows are kept for manual check.")
    parser.add_argument("--end-date", default="2026-06-29", help="YYYY-MM-DD")
    parser.add_argument("--out", default=None, help="Output xlsx path")
    parser.add_argument("--use-search", action="store_true", help="Discover Weverse Community NOTICE URLs through search engine results.")
    parser.add_argument("--search-results", type=int, default=25)
    parser.add_argument("--sweep-min", type=int, default=None, help="Optional Weverse Community notice_id sweep lower bound.")
    parser.add_argument("--sweep-max", type=int, default=None, help="Optional Weverse Community notice_id sweep upper bound.")
    parser.add_argument("--sleep", type=float, default=0.3)
    parser.add_argument("--cache", default=None)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--include-secondary", action="store_true", help="Include title-level secondary/update/guide notices. Default: exclude them.")
    return parser.parse_args()


def resolve_artists(args: argparse.Namespace) -> list[str]:
    if args.artist != "all":
        return [args.artist]
    if args.company == "all":
        return sorted(ARTISTS.keys())
    company_upper = args.company.upper()
    return sorted([k for k, cfg in ARTISTS.items() if cfg["company_group"].upper() == company_upper])


def resolve_cache_path(args: argparse.Namespace, artist: str) -> Path:
    if args.cache:
        p = Path(args.cache)
        if args.artist == "all" or args.company != "all":
            suffix = p.suffix or ".jsonl"
            return p.with_name(f"{p.stem}_{artist}{suffix}")
        return p
    return Path(f"{artist}_weverse_notice_popup_cache_v8.jsonl")


def merge_candidate_sources(a: str, b: str) -> str:
    parts = []
    for x in (a, b):
        for p in x.split("+"):
            if p and p not in parts:
                parts.append(p)
    return "+".join(parts)


def collect_artist(args: argparse.Namespace, artist: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, Path]:
    artist_cfg = ARTISTS[artist]
    start = date.fromisoformat(args.start_date)
    end = date.fromisoformat(args.end_date)
    cache_path = resolve_cache_path(args, artist)

    print("\n" + "=" * 90)
    print(f"[config] company_group={artist_cfg['company_group']} artist={artist} group={artist_cfg['group']} slug={artist_cfg['community_slug']}")
    print("[config] source=Weverse Community NOTICE only. Weverse Shop is excluded.")
    print(f"[config] policy=TITLE contains popup terms only; exclude secondary={not args.include_secondary}")
    print(f"[config] period={start.isoformat()}~{end.isoformat()} cache={cache_path}")

    candidate_urls: dict[str, dict[str, str]] = {}

    if args.use_search:
        print("[1/3] Discovering Weverse Community NOTICE URLs from search results...")
        for url, meta in discover_search_urls(artist_cfg, start, end, args.search_results, args.sleep).items():
            if url not in candidate_urls:
                candidate_urls[url] = meta
            else:
                candidate_urls[url]["source_type"] = merge_candidate_sources(candidate_urls[url].get("source_type", ""), meta.get("source_type", ""))
                if meta.get("search_title") and not candidate_urls[url].get("search_title"):
                    candidate_urls[url]["search_title"] = meta.get("search_title", "")
                if meta.get("search_body") and meta.get("search_body") not in candidate_urls[url].get("search_body", ""):
                    candidate_urls[url]["search_body"] = normalize_space(candidate_urls[url].get("search_body", "") + " " + meta.get("search_body", ""))
    else:
        print("[1/3] Search discovery skipped. Use --use-search to enable.")

    sweep_urls = discover_community_sweep_urls(artist_cfg, args.sweep_min, args.sweep_max)
    if sweep_urls:
        print(f"[2/3] Adding Weverse Community NOTICE ID sweep URLs: {len(sweep_urls)}")
        for url, meta in sweep_urls.items():
            if url not in candidate_urls:
                candidate_urls[url] = meta
            else:
                candidate_urls[url]["source_type"] = merge_candidate_sources(candidate_urls[url].get("source_type", ""), meta.get("source_type", ""))
    else:
        print("[2/3] Community NOTICE ID sweep skipped. Add --sweep-min/--sweep-max only when needed.")

    if not candidate_urls:
        print("[warning] No candidate URLs found. Use --use-search and/or --sweep-min/--sweep-max.", file=sys.stderr)

    print(f"[discover] total candidate Weverse NOTICE URLs={len(candidate_urls)}")

    cache = load_cache(cache_path) if args.resume else {}
    raws: list[NoticeRaw] = []
    rows: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []

    print("[3/3] Fetching, title-filtering, and parsing popup periods...")
    sorted_items = sorted(candidate_urls.items())
    for i, (url, meta) in enumerate(sorted_items, start=1):
        source_type = meta.get("source_type", "")
        search_title = meta.get("search_title", "")
        search_body = meta.get("search_body", "")
        if args.resume and url in cache:
            raw = cache[url]
            raw.source_type = merge_candidate_sources(raw.source_type, source_type)
            # Upgrade old/weak cache entries with current search fallback metadata.
            if search_title and not raw.search_title:
                raw.search_title = search_title
            if search_body and not raw.search_body:
                raw.search_body = search_body
            if is_generic_weverse_title(raw.title) and search_title:
                raw.title = clean_title(search_title)
                raw.extraction_method = (raw.extraction_method + "+cache_search_title_fallback").strip("+")
            if (not raw.body or raw.body.lower() in {"global fandom platform - weverse", "global fandom platform weverse", "weverse"}) and (search_title or search_body):
                raw.body = normalize_space(f"{search_title} {search_body}")
                raw.extraction_method = (raw.extraction_method + "+cache_search_body_fallback").strip("+")
        else:
            raw = fetch_notice(url, artist, artist_cfg, source_type, sleep_sec=args.sleep, search_title=search_title, search_body=search_body)
            append_cache(cache_path, raw)
        raw.artist = artist
        raw.company_group = artist_cfg["company_group"]
        raws.append(raw)

        title = clean_title(raw.title)
        reason = ""
        if raw.http_status != 200:
            reason = f"fetch failed/http_status={raw.http_status}"
        elif not title:
            reason = "title empty"
        elif not title_has_popup(title):
            reason = "title does not contain popup terms"
        elif (not args.include_secondary) and title_is_secondary(title):
            reason = "secondary/update/guide notice excluded by title"

        if reason:
            excluded.append({
                "소속사 구분": artist_cfg["company_group"],
                "그룹명": artist_cfg["group"],
                "artist": raw.artist,
                "source_type": raw.source_type,
                "url": raw.url,
                "notice_id": raw.notice_id,
                "title": title,
                "http_status": raw.http_status,
                "fetch_error": raw.fetch_error,
                "reason": reason,
            })
        else:
            row = build_popup_row(raw, artist_cfg)
            if not date_overlaps_range(row["시작일"], row["종료일"], start, end):
                excluded.append({
                    "소속사 구분": artist_cfg["company_group"],
                    "그룹명": artist_cfg["group"],
                    "artist": raw.artist,
                    "source_type": raw.source_type,
                    "url": raw.url,
                    "notice_id": raw.notice_id,
                    "title": title,
                    "http_status": raw.http_status,
                    "fetch_error": raw.fetch_error,
                    "reason": "outside extracted popup-period range",
                })
            else:
                rows.append(row)

        if i % 50 == 0 or i == len(sorted_items):
            print(f"[progress] {i}/{len(sorted_items)} accepted={len(rows)} excluded={len(excluded)}")

    popup_df = pd.DataFrame(rows)
    if not popup_df.empty:
        popup_df = popup_df.drop_duplicates(subset=["출처(접속 가능한 URL)"])
        popup_df = popup_df.sort_values(["소속사 구분", "그룹명", "시작일", "행사명"], na_position="last")

    raw_df = pd.DataFrame([asdict(r) for r in raws])
    if not raw_df.empty:
        raw_df["body_preview"] = raw_df["body"].fillna("").str.slice(0, 2500)
        raw_df = raw_df.drop(columns=["body"])

    excluded_df = pd.DataFrame(excluded)
    print(f"[result] {artist} popup rows={len(popup_df)} raw rows={len(raw_df)} excluded rows={len(excluded_df)}")
    return popup_df, raw_df, excluded_df, cache_path


def concat_frames(frames: list[pd.DataFrame]) -> pd.DataFrame:
    frames = [df for df in frames if df is not None and not df.empty]
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def main() -> None:
    args = parse_args()
    artists_to_run = resolve_artists(args)
    if not artists_to_run:
        raise SystemExit("No artists selected. Check --company/--artist.")

    if args.out:
        out_path = Path(args.out)
    else:
        suffix = args.company if args.artist == "all" else args.artist
        out_path = Path(f"weverse_notice_popup_v8_{suffix}.xlsx")

    popup_frames: list[pd.DataFrame] = []
    raw_frames: list[pd.DataFrame] = []
    excluded_frames: list[pd.DataFrame] = []
    cache_paths: list[Path] = []

    print(f"[run] selected artists={', '.join(artists_to_run)}")
    for artist in artists_to_run:
        popup_df, raw_df, excluded_df, cache_path = collect_artist(args, artist)
        popup_frames.append(popup_df)
        raw_frames.append(raw_df)
        excluded_frames.append(excluded_df)
        cache_paths.append(cache_path)

    popup_all = concat_frames(popup_frames)
    raw_all = concat_frames(raw_frames)
    excluded_all = concat_frames(excluded_frames)
    if not popup_all.empty:
        popup_all = popup_all.sort_values(["소속사 구분", "그룹명", "시작일", "행사명"], na_position="last")

    params = pd.DataFrame([
        {"parameter": k, "value": str(v)} for k, v in vars(args).items()
    ] + [
        {"parameter": "selected_artists", "value": ", ".join(artists_to_run)},
        {"parameter": "source_policy", "value": "Weverse Community NOTICE only: https://weverse.io/{artist_slug}/notice/{notice_id}. Weverse Shop excluded."},
        {"parameter": "title_policy", "value": "include only notices whose title contains POP-UP/POP UP/POPUP/팝업/ポップアップ"},
        {"parameter": "secondary_exclusion", "value": "default excludes update/change/correction/T&C/guide/reservation/pickup titles unless --include-secondary is used"},
        {"parameter": "period_parse_policy", "value": "prioritizes snippets near 운영기간/Operating Period/Event Period/etc.; fallback dates kept with verification flags"},
        {"parameter": "cache_paths", "value": " | ".join(str(p.resolve()) for p in cache_paths)},
    ])

    print("\n[export] Writing Excel...")
    export_excel(popup_all, raw_all, excluded_all, params, out_path)

    print("\nDone.")
    print(f"- Output Excel:      {out_path.resolve()}")
    print(f"- Raw caches:        {' | '.join(str(p.resolve()) for p in cache_paths)}")
    print(f"- popup rows:        {len(popup_all)}")
    print(f"- raw_notice rows:   {len(raw_all)}")
    print(f"- excluded rows:     {len(excluded_all)}")

    if not popup_all.empty:
        cols = ["소속사 구분", "그룹명", "종류", "행사명", "지역(1)", "지역(2)", "시작일", "종료일", "진행 일 수", "출처(접속 가능한 URL)"]
        cols = [c for c in cols if c in popup_all.columns]
        print("\nPopup notice preview:")
        print(popup_all[cols].head(50).to_string(index=False))


if __name__ == "__main__":
    main()
