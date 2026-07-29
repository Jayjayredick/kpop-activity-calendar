from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd
import streamlit as st
from streamlit_calendar import calendar

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from kpop_notice_collector.qa import compare_manual_truth


EVENTS_PATH = ROOT / "data" / "events_history.csv"
DAILY_PATH = ROOT / "data" / "daily_collected.csv"
XLSX_PATH = ROOT / "output" / "latest_activity_tracker.xlsx"

st.set_page_config(page_title="K-pop Activity Calendar", layout="wide")
st.title("4사 아티스트 활동 캘린더")
st.caption("HYBE · SM · JYP · YG 59팀 | NAVER 뉴스 검색 API | Asia/Seoul")


@st.cache_data(ttl=300)
def load_csv(path: Path) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    return pd.read_csv(path, encoding="utf-8-sig").fillna("")


events = load_csv(EVENTS_PATH)
daily = load_csv(DAILY_PATH)

if events.empty:
    st.info("수집된 일정이 없습니다. GitHub Actions를 먼저 실행하세요.")
    st.stop()

with st.sidebar:
    st.header("필터")
    companies = st.multiselect("회사", sorted(events["company"].unique()))
    types = st.multiselect("활동 유형", sorted(events["activity_type"].unique()))
    artists = st.multiselect("아티스트", sorted(events["artist"].unique()))

filtered = events.copy()
if companies:
    filtered = filtered[filtered["company"].isin(companies)]
if types:
    filtered = filtered[filtered["activity_type"].isin(types)]
if artists:
    filtered = filtered[filtered["artist"].isin(artists)]

tab_calendar, tab_list, tab_daily, tab_qa = st.tabs(
    ["캘린더", "일정 목록", "일일 수집", "수동 검증"]
)

COLORS = {
    "COMEBACK": "#2563EB",
    "TOUR_ANNOUNCEMENT": "#7C3AED",
    "TOUR_EXPANSION": "#9333EA",
    "ADDITIONAL_SHOW": "#DC2626",
    "ENCORE": "#EA580C",
    "FANMEETING": "#059669",
    "POPUP": "#CA8A04",
}

with tab_calendar:
    calendar_events = []
    for _, row in filtered.iterrows():
        dates = [x for x in str(row.get("event_dates", "")).split("|") if x]
        for event_date in dates:
            calendar_events.append(
                {
                    "title": f"{row['artist']} · {row['activity_type']}",
                    "start": event_date,
                    "allDay": True,
                    "backgroundColor": COLORS.get(row["activity_type"], "#64748B"),
                    "extendedProps": {
                        "행사명": row.get("event_name", ""),
                        "도시": row.get("cities", ""),
                        "관련 기사 수": row.get("supporting_article_count", ""),
                        "URL": row.get("primary_url", ""),
                    },
                }
            )
    if not calendar_events:
        st.warning("정확한 날짜가 추출된 일정이 없습니다. 일정 목록을 확인하세요.")
    else:
        calendar(
            events=calendar_events,
            options={
                "initialView": "dayGridMonth",
                "locale": "ko",
                "height": 760,
                "headerToolbar": {
                    "left": "prev,next today",
                    "center": "title",
                    "right": "dayGridMonth,listMonth",
                },
            },
            key="activity_calendar",
        )

with tab_list:
    columns = [
        "company","artist","activity_type","event_name","event_dates","cities",
        "venues","status","score","supporting_article_count","primary_url",
    ]
    st.dataframe(filtered[[c for c in columns if c in filtered]], use_container_width=True)

with tab_daily:
    if daily.empty:
        st.info("일일 수집 이력이 없습니다.")
    else:
        st.dataframe(daily.sort_values("게시일", ascending=False), use_container_width=True)
    if XLSX_PATH.exists():
        st.download_button(
            "최신 Excel 다운로드",
            XLSX_PATH.read_bytes(),
            file_name="latest_activity_tracker.xlsx",
        )

with tab_qa:
    st.write("1~2주간 수동 조사한 정답 CSV를 업로드하면 자동 수집과 대조합니다.")
    uploaded = st.file_uploader("수동 조사 CSV", type=["csv"])
    if uploaded:
        temp = ROOT / "data" / "_manual_upload.csv"
        temp.write_bytes(uploaded.getvalue())
        metrics = compare_manual_truth(EVENTS_PATH, temp)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("정밀도", f"{metrics['정밀도']:.1%}")
        c2.metric("재현율", f"{metrics['재현율']:.1%}")
        c3.metric("오탐", metrics["오탐"])
        c4.metric("누락", metrics["누락"])
        st.json(metrics)
