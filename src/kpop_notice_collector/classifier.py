from __future__ import annotations

import re

from .models import Notice


# 한 기사에 여러 활동이 언급되면 신규성·일정 변경 가치가 큰 유형을 우선한다.
RULES: list[tuple[str, int, list[str]]] = [
    (
        "ADDITIONAL_SHOW",
        60,
        ["추가 회차", "추가 공연", "회차 추가", "additional show", "extra show", "追加公演"],
    ),
    (
        "TOUR_EXPANSION",
        58,
        ["투어 확장", "도시 추가", "일정 추가", "new dates", "additional dates", "tour extension"],
    ),
    ("ENCORE", 56, ["앙코르 콘서트", "앙코르 공연", "encore concert", "encore"]),
    (
        "TOUR_ANNOUNCEMENT",
        54,
        [
            "월드투어",
            "월드 투어",
            "아시아투어",
            "아시아 투어",
            "투어 개최",
            "콘서트 투어",
            "tour announcement",
            "world tour",
            "arena tour",
            "dome tour",
        ],
    ),
    (
        "FANMEETING",
        52,
        ["팬미팅", "팬 미팅", "fan meeting", "fanmeeting", "fan concert", "팬콘"],
    ),
    (
        "POPUP",
        50,
        ["팝업스토어", "팝업 스토어", "pop-up", "pop up", "popup", "ポップアップ"],
    ),
    (
        "COMEBACK",
        48,
        [
            "신보 발매",
            "컴백",
            "새 앨범",
            "정규 앨범",
            "정규앨범",
            "미니 앨범",
            "미니앨범",
            "싱글 발매",
            "앨범 발매",
            "single album",
            "new album",
            "comeback",
        ],
    ),
]

FOLLOWUP_CONTENT = re.compile(
    r"(티저|teaser|하이라이트|하라메|콘셉트|컨셉트|트랙리스트|"
    r"뮤직비디오|뮤비|비주얼|프리뷰|선공개|인터뷰|화보|포토|"
    r"차트\s*(?:1위|진입|정상)|D-\d+)",
    re.I,
)
PAST_OR_RECAP = re.compile(
    r"(성료|마쳐|마무리|종료|막\s*내려|관객\s*동원|투어를\s*마친|"
    r"공연을\s*마친|전석\s*매진으로\s*마무리)",
    re.I,
)
CANCELLATION_OR_HEALTH = re.compile(
    r"(활동\s*(?:잠정\s*)?중단|불참|취소|연기|건강\s*(?:문제|악화)|계약\s*종료)",
    re.I,
)
NEW_ANNOUNCEMENT = re.compile(
    r"(확정|발표|개최|연다|오픈|돌입|나선다|시작|스타트|출시|발매|"
    r"일정\s*공개|추가\s*(?:회차|공연|일정)|앙코르)",
    re.I,
)


def classify(notice: Notice, *, title_only: bool = False) -> Notice:
    text = notice.title if title_only else f"{notice.title}\n{notice.body}"
    lowered = text.lower()
    best_type = "OTHER"
    best_score = 0
    hits: list[str] = []

    for activity_type, base_score, keywords in RULES:
        matched = [keyword for keyword in keywords if keyword.lower() in lowered]
        if not matched:
            continue
        score = base_score + min(12, 3 * (len(matched) - 1))
        hits.extend(matched)
        if score > best_score:
            best_type, best_score = activity_type, score

    notice.activity_type = best_type
    notice.score = best_score
    notice.matched_keywords = sorted(set(hits))
    notice.clipped_text = clip_evidence(
        notice.body or notice.title, notice.matched_keywords
    )
    return notice


def news_rejection_reason(notice: Notice) -> str:
    title = notice.title
    if notice.activity_type == "OTHER":
        return "제목에 대상 활동 키워드 없음"
    if CANCELLATION_OR_HEALTH.search(title):
        return "취소·중단·건강 이슈"
    if PAST_OR_RECAP.search(title) and not NEW_ANNOUNCEMENT.search(title):
        return "종료·성료·과거 실적 기사"
    if FOLLOWUP_CONTENT.search(title) and not NEW_ANNOUNCEMENT.search(title):
        return "티저·인터뷰·차트 등 후속 콘텐츠"
    if notice.activity_type == "TOUR_ANNOUNCEMENT" and not NEW_ANNOUNCEMENT.search(title):
        return "투어 신규 발표 문구 없음"
    if notice.activity_type in {"FANMEETING", "POPUP"} and not NEW_ANNOUNCEMENT.search(title):
        return "개최·운영 신규 문구 없음"
    return ""


def clip_evidence(text: str, keywords: list[str], max_chars: int = 320) -> str:
    clean = re.sub(r"\s+", " ", text or "").strip()
    if not clean:
        return ""
    lower = clean.lower()
    positions = [lower.find(k.lower()) for k in keywords if lower.find(k.lower()) >= 0]
    pivot = min(positions) if positions else 0
    start = max(0, pivot - 90)
    end = min(len(clean), start + max_chars)
    clipped = clean[start:end].strip()
    return ("… " if start else "") + clipped + (" …" if end < len(clean) else "")
