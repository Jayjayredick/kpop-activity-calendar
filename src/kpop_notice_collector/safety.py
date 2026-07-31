from __future__ import annotations

from typing import Any
from urllib.parse import urlparse


SPREADSHEET_FORMULA_PREFIXES = ("=", "+", "-", "@")


def spreadsheet_safe(value: Any) -> Any:
    """Excel/CSV에서 외부 문자열이 수식으로 실행되지 않도록 보호한다."""
    if not isinstance(value, str) or not value:
        return value
    stripped = value.lstrip(" \t\r\n")
    if not stripped.startswith(SPREADSHEET_FORMULA_PREFIXES):
        return value
    if value.startswith("'"):
        return value
    return f"'{value}"


def spreadsheet_restore(value: Any) -> Any:
    """내부 CSV를 다시 읽을 때 보호용 작은따옴표만 제거한다."""
    if not isinstance(value, str) or not value.startswith("'"):
        return value
    stripped = value[1:].lstrip(" \t\r\n")
    if stripped.startswith(SPREADSHEET_FORMULA_PREFIXES):
        return value[1:]
    return value


def safe_row_for_spreadsheet(row: dict) -> dict:
    return {key: spreadsheet_safe(value) for key, value in row.items()}


def restore_spreadsheet_row(row: dict) -> dict:
    return {key: spreadsheet_restore(value) for key, value in row.items()}


def safe_http_url(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    try:
        parsed = urlparse(value)
    except ValueError:
        return ""
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return ""
    return value
