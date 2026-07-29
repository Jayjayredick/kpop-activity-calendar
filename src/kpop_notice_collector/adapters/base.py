from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

try:
    import requests
except ImportError:  # 테스트에서 가짜 세션을 주입할 때만 허용
    requests = None

from ..models import Artist, Notice, Source


HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; KpopOfficialNoticeCollector/1.0)",
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8,ja;q=0.7",
}


class BaseAdapter(ABC):
    def __init__(self, session: Any = None, timeout: int = 25):
        if session is None and requests is None:
            raise RuntimeError("requests 패키지가 필요합니다.")
        self.session = session or requests.Session()
        self.timeout = timeout

    def get(self, url: str) -> Any:
        response = self.session.get(url, headers=HEADERS, timeout=self.timeout)
        response.raise_for_status()
        return response

    @abstractmethod
    def collect(
        self, source: Source, artists: list[Artist], fetched_at: datetime
    ) -> list[Notice]:
        raise NotImplementedError
