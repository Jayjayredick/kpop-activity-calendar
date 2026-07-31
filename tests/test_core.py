from __future__ import annotations

import unittest
import json
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from zoneinfo import ZoneInfo

from kpop_notice_collector.adapters.naver_news import NaverNewsAdapter
from kpop_notice_collector.calendar_feed import build_calendar_feed
from kpop_notice_collector.classifier import classify, news_rejection_reason
from kpop_notice_collector.config import load_activity_entities, load_artists
from kpop_notice_collector.event_cluster import cluster_events
from kpop_notice_collector.event_parser import parse_event_fields
from kpop_notice_collector.models import Artist, Notice
from kpop_notice_collector.news_pipeline import (
    choose_search_name,
    run_naver_news,
    title_artist_alias,
)
from kpop_notice_collector.qa import compare_manual_truth
from kpop_notice_collector.review_cli import apply_decisions
from kpop_notice_collector.schedule_compare import assess_schedule_change


class CoreTests(unittest.TestCase):
    def test_calendar_feed_keeps_previous_two_weeks_and_next_three_months(self):
        tz = ZoneInfo("Asia/Seoul")
        now = datetime(2026, 7, 28, 7, 35, tzinfo=tz)
        rows = [
            {
                "event_key": "rv-comeback",
                "company": "SM",
                "label": "SM",
                "artist": "Red Velvet",
                "activity_type": "COMEBACK",
                "event_name": "New Album",
                "event_dates": "2026-07-13|2026-07-14|2026-10-28|2026-10-29",
                "primary_url": "https://example.com/rv",
            }
        ]
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "calendar_events.json"
            build_calendar_feed(rows, path, now=now, months=3)
            payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(payload["rangeStart"], "2026-07-14")
        self.assertEqual(payload["rangeEndInclusive"], "2026-10-28")
        self.assertEqual(
            [event["start"] for event in payload["events"]],
            ["2026-07-14", "2026-10-28"],
        )

    def test_master_counts(self):
        artists = load_artists()
        self.assertEqual(len(artists), 59)
        self.assertEqual(
            {company: sum(a.company == company for a in artists) for company in ["HYBE", "SM", "JYP", "YG"]},
            {"HYBE": 22, "SM": 16, "JYP": 15, "YG": 6},
        )
        self.assertGreaterEqual(len(load_activity_entities()), 1)

    def test_priority_keyword(self):
        notice = Notice(
            source_id="test",
            company="SM",
            label="SM",
            artist_id="red_velvet",
            artist="Red Velvet",
            title="팬콘 전석 매진에 추가 회차 오픈",
            url="https://www.smentertainment.com/newsroom/test/",
            published_at=datetime.now(ZoneInfo("Asia/Seoul")),
            body="레드벨벳 팬콘의 7월 31일 추가 회차를 오픈한다.",
            fetched_at=datetime.now(ZoneInfo("Asia/Seoul")),
        )
        classify(notice)
        self.assertEqual(notice.activity_type, "ADDITIONAL_SHOW")
        self.assertGreaterEqual(notice.score, 45)
        self.assertIn("추가 회차", notice.clipped_text)

    def test_naver_adapter_and_relevance_filter(self):
        now = datetime(2026, 7, 28, 8, 0, tzinfo=ZoneInfo("Asia/Seoul"))
        artist = Artist(
            artist_id="red_velvet",
            company="SM",
            label="SM",
            name="Red Velvet",
            aliases=["레드벨벳"],
            official_url="https://example.com",
            source_ids=[],
        )

        class FakeResponse:
            def raise_for_status(self):
                return None

            def json(self):
                pub_date = (now - timedelta(hours=2)).strftime(
                    "%a, %d %b %Y %H:%M:%S %z"
                )
                return {
                    "items": [
                        {
                            "title": "<b>레드벨벳</b>, 신보 발매 확정",
                            "originallink": "https://www.yna.co.kr/view/test",
                            "link": "https://n.news.naver.com/test",
                            "description": "레드벨벳이 새 앨범으로 컴백한다.",
                            "pubDate": pub_date,
                        },
                        {
                            "title": "다른 가수 신보 발매",
                            "originallink": "https://example.net/other",
                            "link": "https://n.news.naver.com/other",
                            "description": "관련 없는 기사",
                            "pubDate": pub_date,
                        },
                        {
                            "title": "레드벨벳 과거 컴백 기사",
                            "originallink": "https://example.net/old",
                            "link": "https://n.news.naver.com/old",
                            "description": "오래된 기사",
                            "pubDate": (now - timedelta(hours=30)).strftime(
                                "%a, %d %b %Y %H:%M:%S %z"
                            ),
                        },
                    ]
                }

        class FakeSession:
            def __init__(self):
                self.last_headers = {}

            def get(self, *args, **kwargs):
                self.last_headers = kwargs["headers"]
                return FakeResponse()

        adapter = NaverNewsAdapter(
            key_id="id", key="secret", session=FakeSession()
        )
        config = {
            "hours": 24,
            "display": 100,
            "sort": "date",
            "max_pages": 1,
            "blocked_title_aliases": [],
            "default_publisher_score": 3,
            "publisher_scores": {"yna.co.kr": 10},
        }
        rows, excluded, log = run_naver_news(
            [artist], config, history=[], now=now, adapter=adapter
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].publisher, "yna.co.kr")
        self.assertEqual(rows[0].activity_type, "COMEBACK")
        self.assertEqual(rows[0].validation_status, "REVIEW_REQUIRED")
        self.assertEqual(adapter.session.last_headers["X-NCP-APIGW-API-KEY-ID"], "id")
        self.assertEqual(len(excluded), 1)
        self.assertEqual(log[0]["error"], "")
        self.assertEqual(log[0]["outside_24h"], 1)
        self.assertEqual(log[0]["api_calls"], 1)

    def test_ambiguous_korean_alias_is_blocked(self):
        artist = Artist(
            artist_id="itzy",
            company="JYP",
            label="JYP",
            name="ITZY",
            aliases=["ITZY", "있지"],
            official_url="",
            source_ids=[],
        )
        config = {
            "search_name_overrides": {"itzy": "ITZY"},
            "blocked_title_aliases": ["있지"],
        }
        self.assertEqual(choose_search_name(artist, config), "ITZY")
        self.assertEqual(
            title_artist_alias("기대할 수 있지…새 앨범 발매", artist, config),
            "",
        )
        self.assertEqual(
            title_artist_alias("ITZY, 새 앨범 발매 확정", artist, config),
            "ITZY",
        )

    def test_followup_and_recap_are_rejected(self):
        now = datetime.now(ZoneInfo("Asia/Seoul"))
        followup = Notice(
            source_id="test",
            company="SM",
            label="SM",
            artist_id="red_velvet",
            artist="Red Velvet",
            title="레드벨벳, 컴백 하이라이트 메들리 공개",
            url="https://example.com/followup",
            published_at=now,
            body="",
            fetched_at=now,
        )
        classify(followup, title_only=True)
        self.assertEqual(
            news_rejection_reason(followup),
            "티저·인터뷰·차트 등 후속 콘텐츠",
        )

        recap = Notice(
            source_id="test",
            company="SM",
            label="SM",
            artist_id="exo",
            artist="EXO",
            title="엑소, 월드투어 27회 성료",
            url="https://example.com/recap",
            published_at=now,
            body="",
            fetched_at=now,
        )
        classify(recap, title_only=True)
        self.assertEqual(
            news_rejection_reason(recap),
            "종료·성료·과거 실적 기사",
        )

    def test_financial_and_poll_context_are_rejected(self):
        now = datetime.now(ZoneInfo("Asia/Seoul"))
        financial = Notice(
            source_id="test",
            company="HYBE",
            label="BigHit",
            artist_id="bts",
            artist="BTS",
            title="BTS 컴백 효과…하이브 분기 매출 사상 최대",
            url="https://example.com/finance",
            published_at=now,
            body="",
            fetched_at=now,
        )
        classify(financial, title_only=True)
        self.assertEqual(
            news_rejection_reason(financial),
            "실적·주가·흥행 효과 등 일정 비핵심 기사",
        )

        poll = Notice(
            source_id="test",
            company="SM",
            label="SM",
            artist_id="red_velvet",
            artist="Red Velvet",
            title="레드벨벳 웬디, 컴백 앞두고 우산 씌워주고 싶은 가수 1위",
            url="https://example.com/poll",
            published_at=now,
            body="",
            fetched_at=now,
        )
        classify(poll, title_only=True)
        self.assertEqual(
            news_rejection_reason(poll),
            "투표·순위·화보·근황 등 일정 비핵심 기사",
        )

    def test_month_day_and_next_month_dates(self):
        published = datetime(2026, 7, 28, 8, 0, tzinfo=ZoneInfo("Asia/Seoul"))
        notice = Notice(
            source_id="test",
            company="SM",
            label="SM",
            artist_id="wayv",
            artist="WayV",
            title="WayV, 8월 10~11일 서울 콘서트 개최…내달 12일까지 팝업",
            url="https://example.com/date",
            published_at=published,
            body="",
            fetched_at=published,
        )
        parse_event_fields(notice)
        self.assertEqual(
            notice.event_dates,
            ["2026-08-10", "2026-08-11"],
        )

    def test_cross_month_fancon_is_concert_range(self):
        published = datetime(2026, 7, 29, 8, 0, tzinfo=ZoneInfo("Asia/Seoul"))
        notice = Notice(
            source_id="test",
            company="SM",
            label="SM",
            artist_id="red_velvet",
            artist="Red Velvet",
            title="레드벨벳, 31일 팬콘 개최",
            url="https://example.com/fancon",
            published_at=published,
            body="오는 31일부터 다음 달 2일까지 서울 고려대학교 화정체육관에서 팬콘을 개최한다.",
            fetched_at=published,
            matched_artist_alias="레드벨벳",
        )
        classify(notice)
        parse_event_fields(notice)
        self.assertEqual(notice.activity_type, "CONCERT")
        self.assertEqual(notice.event_start_date, "2026-07-31")
        self.assertEqual(notice.event_end_date, "2026-08-02")
        self.assertTrue(notice.event_is_range)
        self.assertIn("고려대학교 화정체육관", notice.venues)

    def test_title_date_wins_over_unrelated_body_dates(self):
        published = datetime(2026, 7, 30, 8, 0, tzinfo=ZoneInfo("Asia/Seoul"))
        notice = Notice(
            source_id="test",
            company="SM",
            label="SM",
            artist_id="riize",
            artist="RIIZE",
            title="라이즈, 데뷔 3주년 팬미팅 9월 12~13일 개최",
            url="https://example.com/riize",
            published_at=published,
            body="관련 기사는 과거 7월 6일부터 12일까지의 다른 일정을 함께 소개했다.",
            fetched_at=published,
            activity_type="FANMEETING",
        )
        parse_event_fields(notice)
        self.assertEqual(notice.event_start_date, "2026-09-12")
        self.assertEqual(notice.event_end_date, "2026-09-13")
        self.assertEqual(notice.date_source, "TITLE")
        self.assertEqual(notice.date_confidence, "HIGH")

    def test_past_month_is_not_rolled_into_next_year(self):
        published = datetime(2026, 7, 30, 8, 0, tzinfo=ZoneInfo("Asia/Seoul"))
        notice = Notice(
            source_id="test",
            company="HYBE",
            label="Source Music",
            artist_id="lesserafim",
            artist="LE SSERAFIM",
            title="르세라핌, 5월 22일 월드투어 개최",
            url="https://example.com/lesserafim",
            published_at=published,
            body="",
            fetched_at=published,
            activity_type="TOUR_ANNOUNCEMENT",
        )
        parse_event_fields(notice)
        self.assertEqual(notice.event_start_date, "2026-05-22")

    def test_title_bare_day_uses_publication_month_with_medium_confidence(self):
        published = datetime(2026, 7, 18, 8, 0, tzinfo=ZoneInfo("Asia/Seoul"))
        notice = Notice(
            source_id="test",
            company="SM",
            label="SM",
            artist_id="aespa",
            artist="aespa",
            title="에스파, 24일 일본 첫 미니앨범 발매",
            url="https://example.com/aespa",
            published_at=published,
            body="",
            fetched_at=published,
            activity_type="COMEBACK",
        )
        parse_event_fields(notice)
        self.assertEqual(notice.event_start_date, "2026-07-24")
        self.assertEqual(notice.date_confidence, "MEDIUM")

    def test_conflicting_title_dates_are_left_for_manual_review(self):
        published = datetime(2026, 7, 30, 8, 0, tzinfo=ZoneInfo("Asia/Seoul"))
        notice = Notice(
            source_id="test",
            company="JYP",
            label="JYP",
            artist_id="nmixx",
            artist="NMIXX",
            title="엔믹스, 8월 10일 콘서트·9월 12일 콘서트 개최",
            url="https://example.com/nmixx",
            published_at=published,
            body="",
            fetched_at=published,
            activity_type="CONCERT",
        )
        parse_event_fields(notice)
        self.assertTrue(notice.date_conflict)
        self.assertEqual(notice.date_confidence, "CONFLICT")
        self.assertEqual(notice.event_start_date, "")

    def test_song_title_is_not_used_as_fancon_name(self):
        published = datetime(2026, 7, 30, 8, 0, tzinfo=ZoneInfo("Asia/Seoul"))
        notice = Notice(
            source_id="test",
            company="SM",
            label="SM",
            artist_id="red_velvet",
            artist="Red Velvet",
            title="레드벨벳, 팬콘서트서 미발표곡 '서핀 보이' 공개",
            url="https://example.com/red-velvet-song",
            published_at=published,
            body="",
            fetched_at=published,
            activity_type="CONCERT",
            matched_artist_alias="레드벨벳",
        )
        parse_event_fields(notice)
        self.assertEqual(notice.event_name, "Red Velvet 팬콘서트")

    def test_album_name_drives_duplicate_cluster(self):
        now = datetime.now(ZoneInfo("Asia/Seoul"))
        common = {
            "source_id": "naver_news",
            "source_type": "NAVER_NEWS",
            "company": "SM",
            "label": "SM",
            "artist_id": "nct_127",
            "artist": "NCT 127",
            "published_at": now,
            "body": "",
            "fetched_at": now,
            "activity_type": "COMEBACK",
            "score": 70,
            "matched_artist_alias": "NCT 127",
        }
        first = Notice(
            title="NCT 127, 정규 7집 'BLINGY' 컴백 확정",
            url="https://example.com/nct-a",
            **common,
        )
        second = Notice(
            title="NCT 127 정규 7집 BLINGY 발매 발표",
            url="https://example.com/nct-b",
            **common,
        )
        parse_event_fields(first)
        parse_event_fields(second)
        clustered = cluster_events([first, second])
        self.assertEqual(len(clustered), 1)
        self.assertEqual(clustered[0].event_name, "BLINGY")

    def test_schedule_change_detection(self):
        now = datetime.now(ZoneInfo("Asia/Seoul"))
        history = [
            {
                "event_key": "old",
                "artist_id": "twice",
                "activity_type": "TOUR_ANNOUNCEMENT",
                "event_name": "THIS IS FOR World Tour",
                "event_dates": "2026-08-01",
                "cities": "서울",
            }
        ]
        same_city = Notice(
            source_id="test",
            company="JYP",
            label="JYP",
            artist_id="twice",
            artist="TWICE",
            title="THIS IS FOR World Tour 서울 추가 일정",
            url="https://example.com/1",
            published_at=now,
            body="",
            fetched_at=now,
            activity_type="TOUR_ANNOUNCEMENT",
            score=32,
            event_name="THIS IS FOR World Tour",
            event_dates=["2026-08-02"],
            cities=["서울"],
        )
        assess_schedule_change(same_city, history)
        self.assertEqual(same_city.activity_type, "ADDITIONAL_SHOW")
        self.assertEqual(same_city.schedule_status, "SAME_CITY_NEW_DATE")

        new_city = Notice(
            source_id="test",
            company="JYP",
            label="JYP",
            artist_id="twice",
            artist="TWICE",
            title="THIS IS FOR World Tour 도쿄",
            url="https://example.com/2",
            published_at=now,
            body="",
            fetched_at=now,
            activity_type="TOUR_ANNOUNCEMENT",
            score=32,
            event_name="THIS IS FOR World Tour",
            event_dates=["2026-08-05"],
            cities=["도쿄"],
        )
        assess_schedule_change(new_city, history)
        self.assertEqual(new_city.activity_type, "TOUR_EXPANSION")
        self.assertEqual(new_city.schedule_status, "NEW_CITY")

    def test_same_dated_event_has_one_calendar_key(self):
        now = datetime.now(ZoneInfo("Asia/Seoul"))
        common = {
            "source_id": "test",
            "company": "SM",
            "label": "SM",
            "artist_id": "aespa",
            "artist": "aespa",
            "published_at": now,
            "body": "",
            "fetched_at": now,
            "activity_type": "COMEBACK",
            "event_name": "aespa New Album",
            "event_dates": ["2026-08-10"],
        }
        first = Notice(title="aespa 새 앨범 발매", url="https://a.example", **common)
        second = Notice(title="에스파 8월 컴백 확정", url="https://b.example", **common)
        self.assertEqual(first.event_key, second.event_key)

    def test_similar_articles_cluster_to_one_event(self):
        now = datetime.now(ZoneInfo("Asia/Seoul"))
        common = {
            "source_id": "naver_news",
            "source_type": "NAVER_NEWS",
            "company": "YG",
            "label": "YG",
            "artist_id": "blackpink",
            "artist": "BLACKPINK",
            "published_at": now,
            "body": "",
            "fetched_at": now,
            "activity_type": "POPUP",
            "score": 70,
            "matched_artist_alias": "블랙핑크",
            "event_dates": ["2026-08-05"],
            "cities": ["서울"],
        }
        first = Notice(
            title="블랙핑크X다마고치 팝업스토어 오픈",
            event_name="블랙핑크X다마고치 팝업스토어",
            url="https://example.com/a",
            **common,
        )
        second = Notice(
            title="롯데백화점, 블랙핑크 다마고치 팝업 개최",
            event_name="롯데백화점 블랙핑크 다마고치 팝업",
            url="https://example.com/b",
            **common,
        )
        clustered = cluster_events([first, second])
        self.assertEqual(len(clustered), 1)
        self.assertEqual(clustered[0].supporting_article_count, 2)
        self.assertEqual(clustered[0].related_urls, ["https://example.com/b"])

    def test_different_dates_do_not_merge_even_with_same_event_name(self):
        now = datetime.now(ZoneInfo("Asia/Seoul"))
        common = {
            "source_id": "naver_news",
            "source_type": "NAVER_NEWS",
            "company": "SM",
            "label": "SM",
            "artist_id": "riize",
            "artist": "RIIZE",
            "published_at": now,
            "body": "",
            "fetched_at": now,
            "activity_type": "FANMEETING",
            "score": 75,
            "event_name": "RIIZE Anniversary Fanmeeting",
            "date_confidence": "HIGH",
            "date_source": "TITLE",
        }
        first = Notice(
            title="RIIZE 팬미팅 8월 1일 개최",
            url="https://example.com/riize-a",
            event_start_date="2026-08-01",
            event_end_date="2026-08-01",
            event_dates=["2026-08-01"],
            **common,
        )
        second = Notice(
            title="RIIZE 팬미팅 9월 12일 개최",
            url="https://example.com/riize-b",
            event_start_date="2026-09-12",
            event_end_date="2026-09-12",
            event_dates=["2026-09-12"],
            **common,
        )
        self.assertEqual(len(cluster_events([first, second])), 2)

    def test_review_page_has_safe_bulk_actions(self):
        html = (
            Path(__file__).resolve().parents[1] / "docs" / "index.html"
        ).read_text(encoding="utf-8")
        self.assertIn('id="bulk-approve"', html)
        self.assertIn('id="bulk-reject"', html)
        self.assertIn("maxBulkItems = 30", html)
        self.assertIn("reviewPageSize = 30", html)
        self.assertIn('id="clear-decisions"', html)
        self.assertIn("날짜가 없는", html)

    def test_manual_truth_uses_semantic_fields(self):
        with TemporaryDirectory() as temp_dir:
            automated = Path(temp_dir) / "automated.csv"
            manual = Path(temp_dir) / "manual.csv"
            automated.write_text(
                "event_key,artist,activity_type,event_name,event_dates,cities\n"
                "hash,TWICE,COMEBACK,Strategy,2026-08-01,서울\n",
                encoding="utf-8-sig",
            )
            manual.write_text(
                "아티스트,활동 유형,행사명,이벤트 날짜,도시\n"
                "TWICE,COMEBACK,Strategy,2026-08-01,서울\n",
                encoding="utf-8-sig",
            )
            result = compare_manual_truth(automated, manual)
            self.assertEqual(result["일치"], 1)
            self.assertEqual(result["정밀도"], 1.0)

    def test_review_approval_moves_candidate_to_history(self):
        now = datetime(2026, 7, 29, 8, 0, tzinfo=ZoneInfo("Asia/Seoul"))
        queue = [
            {
                "candidate_id": "candidate-1",
                "event_key": "old-key",
                "company": "SM",
                "label": "SM",
                "artist_id": "red_velvet",
                "artist": "Red Velvet",
                "activity_type": "CONCERT",
                "event_name": "Red Velvet FANCON",
                "event_start_date": "",
                "event_end_date": "",
                "cities": "서울",
                "venues": "",
                "primary_url": "https://example.com/rv",
                "score": "70",
                "article_title": "레드벨벳 팬콘 개최",
            }
        ]
        payload = {
            "schema": "kpop-calendar-review-v1",
            "decisions": [
                {
                    "action": "APPROVE",
                    "candidateId": "candidate-1",
                    "company": "SM",
                    "artistId": "red_velvet",
                    "artist": "Red Velvet",
                    "activityType": "CONCERT",
                    "eventName": "Red Velvet FANCON",
                    "eventStartDate": "2026-07-31",
                    "eventEndDate": "2026-08-02",
                    "cities": "서울",
                    "venues": "고려대학교 화정체육관",
                }
            ],
        }
        history, remaining, logs = apply_decisions(
            payload, [], queue, now=now
        )
        self.assertEqual(len(history), 1)
        self.assertEqual(remaining, [])
        self.assertEqual(history[0]["approval_status"], "MANUAL_CONFIRMED")
        self.assertEqual(history[0]["event_start_date"], "2026-07-31")
        self.assertEqual(history[0]["event_end_date"], "2026-08-02")
        self.assertEqual(logs[0]["action"], "APPROVE")


if __name__ == "__main__":
    unittest.main()
