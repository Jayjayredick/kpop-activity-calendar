# 4사 K-pop 활동 추적기 v3.0

HYBE·SM·JYP·YG의 그룹, 등록된 솔로·유닛을 NAVER 뉴스 검색 API로 점검하고
확정 캘린더와 검토 대기 목록을 GitHub Pages에 갱신합니다.

## v3.0 핵심 변경점

- `CONCERT` 활동 유형 추가
  - `팬콘`, `팬 콘서트`, `fan concert`는 팬미팅이 아니라 콘서트로 분류
- 행사명을 캘린더 제목에 표시
  - 앨범명, 투어명, 콘서트명, 팬미팅명, 팝업명을 우선 추출
- 기간형 일정 지원
  - `7월 31일부터 8월 2일까지`
  - `오는 31일부터 다음 달 2일까지`
  - 캘린더에는 하루씩 세 건이 아니라 하나의 기간 일정으로 표시
- 행사 단위 중복 제거 강화
  - 아티스트·활동 유형·앨범/투어/행사명·날짜·도시를 함께 비교
- 실적·주가·투표·화보·근황 기사 오탐 차단
- 그룹보다 등록된 솔로·유닛 이름을 우선 매칭
- 날짜가 없는 후보에 대해 `아티스트 + 행사명 + 발매일/일정` 2차 검색
- 캘린더 표시 범위: 오늘 포함 과거 14일 ~ 오늘 기준 향후 3개월
- 검토 대기 웹 화면 추가
- 웹에서 확정 일정 수정·삭제 요청 및 일정 직접 추가 가능
- 과거 180일 기사에서 이미 발표된 미래 일정을 찾는 백필 워크플로 추가

## 보안상 웹 수정이 작동하는 방식

GitHub Pages는 저장 기능이 없는 정적 사이트입니다. 페이지에 GitHub 토큰을
넣어 저장소를 직접 수정하게 만들면 토큰 유출 위험이 있습니다.

v3.0은 다음 구조를 사용합니다.

1. 캘린더 사이트에서 후보를 수정하고 `확정` 또는 `제외` 선택
2. 결정 내용은 현재 브라우저의 로컬 저장소에 임시 보관
3. `GitHub에 반영 요청` 버튼 클릭
4. GitHub의 새 이슈 작성 화면에서 `Submit new issue` 클릭
5. 저장소 소유자가 만든 `[CALENDAR REVIEW]` 이슈만 Actions가 처리
6. 확정·수정·삭제 내용을 CSV와 캘린더 JSON에 반영
7. Pages를 다시 배포하고 처리된 이슈를 자동 종료

API Key와 GitHub 토큰은 캘린더 HTML·JSON에 들어가지 않습니다.

## 추적 활동 유형

| 코드 | 화면 표시 | 주요 예 |
|---|---|---|
| `COMEBACK` | 컴백 | 신보·정규·미니·싱글 발매 |
| `TOUR_ANNOUNCEMENT` | 투어 발표 | 월드투어·아시아투어 발표 |
| `TOUR_EXPANSION` | 투어 확장 | 도시·국가·일정 추가 |
| `ADDITIONAL_SHOW` | 추가 회차 | 같은 도시 추가 공연 |
| `ENCORE` | 앙코르 | 앙코르 콘서트 |
| `CONCERT` | 콘서트 | 단독 콘서트·팬콘 |
| `FANMEETING` | 팬미팅 | 팬미팅 |
| `POPUP` | 팝업 | 팝업스토어 |

## 주요 데이터 파일

```text
config/artists.json                 부모 아티스트 59팀
config/activity_entities.json       별도 검색할 솔로·유닛
config/news_queries.json            검색·점수·백필 설정
config/site.json                    저장소 주소와 캘린더 범위

data/events_history.csv             확정 일정
data/review_queue.csv               검토 대기
data/review_log.csv                 확정·제외·수정 이력
data/daily_collected.csv             일일 수집 이력

docs/calendar_events.json           웹 확정 일정
docs/review_queue.json              웹 검토 대기
docs/index.html                     GitHub Pages 화면
```

## 최초 GitHub 설정

### 1. 저장소 파일 교체

기존 저장소 내용을 새 v3.0 파일로 교체합니다. 다음 숨김 항목도 반드시
업로드되어야 합니다.

```text
.github
.gitignore
.env.example
```

실제 `.env` 파일은 업로드하지 않습니다.

### 2. NAVER API Secret 확인

```text
Settings
→ Secrets and variables
→ Actions
```

다음 두 Secret이 있어야 합니다.

```text
NAVER_API_KEY_ID
NAVER_API_KEY
```

### 3. Issues 기능 확인

```text
Settings
→ General
→ Features
→ Issues
```

`Issues`를 활성화합니다. 웹 검토 결과가 이슈로 제출됩니다.

### 4. Pages 설정

```text
Settings
→ Pages
→ Build and deployment
→ Source
→ GitHub Actions
```

## 권장 최초 실행 순서

### 1단계: 일일 수집 테스트

```text
Actions
→ Daily K-pop activity tracker
→ Run workflow
```

확인할 항목:

- `collect`와 `deploy-pages`가 모두 초록색 체크인지
- Excel artifact가 생성됐는지
- 캘린더와 검토 대기 건수가 표시되는지

### 2단계: 회사별 백필

한 번에 전체를 실행할 수 있지만 최초에는 회사별 실행을 권장합니다.

```text
Actions
→ Backfill K-pop calendar
→ Run workflow
```

권장 입력:

```text
days_back              180
company                HYBE → SM → JYP → YG 순차 실행
publish_review_queue   true
```

백필 결과는 확정 캘린더로 직접 들어가지 않고 웹 `검토 대기`에 누적됩니다.

### 3단계: 웹 검토

1. 캘린더 사이트에서 `검토 대기 및 수정` 선택
2. 행사명·활동 유형·시작일·종료일·도시·공연장을 수정
3. `수정 내용으로 확정` 또는 `일정에서 제외` 선택
4. 여러 건을 검토한 뒤 `GitHub에 반영 요청` 클릭
5. 열린 GitHub 화면에서 `Submit new issue` 클릭
6. `Actions → Apply calendar review` 완료 확인

확정 캘린더의 일정도 클릭하면 수정·삭제 요청을 작성할 수 있습니다.

## 일일 자동 실행

`.github/workflows/daily.yml`은 매일 오전 07:35 KST에 실행됩니다.

```yaml
cron: "35 22 * * *"
```

GitHub Actions 예약 시간은 UTC 기준이며 서버 상황에 따라 몇 분 지연될 수
있습니다.

## 백필 검색 구조

NAVER 뉴스 검색 API에는 날짜 구간 요청 파라미터가 없습니다. 백필은
활동별 검색어를 나누고 응답의 `pubDate`를 직접 검사합니다.

```text
아티스트 컴백
아티스트 신보 발매
아티스트 앨범 발매
아티스트 투어 발표
아티스트 콘서트 개최
아티스트 추가 회차
아티스트 앙코르 콘서트
아티스트 팬미팅 개최
아티스트 팬콘 개최
아티스트 팝업스토어
```

같은 기사가 여러 검색어에서 발견돼도 원문 URL로 먼저 제거하고, 이후
행사명·날짜·도시 기준으로 다시 통합합니다.

## 솔로·유닛 관리

`config/activity_entities.json`에 별도 검색할 솔로·유닛을 등록합니다.

```json
{
  "artist_id": "super_junior_yesung",
  "company": "SM",
  "label": "SM Entertainment",
  "name": "YESUNG (예성)",
  "aliases": ["YESUNG", "예성", "슈퍼주니어 예성"],
  "official_url": "https://www.smentertainment.com/",
  "source_ids": []
}
```

짧고 일반적인 이름은 오탐 위험이 있으므로 `방탄소년단 진`, `샤이니 키`,
`NCT 마크`처럼 그룹명이 포함된 검색어를
`config/news_queries.json → search_name_overrides`에 추가합니다.

## 로컬 실행

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

`.env`:

```text
NAVER_API_KEY_ID=발급받은_API_Key_ID
NAVER_API_KEY=발급받은_API_Key
```

일일 실행:

```bash
PYTHONPATH=src python -m kpop_notice_collector.cli --hours 24
```

백필 시험 실행:

```bash
PYTHONPATH=src python -m kpop_notice_collector.backfill_cli \
  --days-back 180 \
  --company SM \
  --out output/backfill_review.xlsx
```

검토 대기까지 게시하려면 `--publish-review-queue`를 추가합니다.

## Excel 출력

- `daily_selected`: 이번 실행에서 행사 단위로 통합된 결과
- `calendar_events`: 확정 누적 일정
- `raw_articles`: 대표 기사 검색 패시지
- `excluded`: 제외된 대표 사례
- `source_runs`: 검색어·호출 수·오류
- `validation_queue`: 검토가 필요한 후보
- `run_params`: 실행 조건·백필 여부·건수

## 주의사항

- NAVER API는 기사 전문이 아니라 제목과 설명을 제공합니다.
- 2차 날짜 검색을 해도 날짜가 확인되지 않으면 검토 대기에 남습니다.
- 웹에서 결정을 작성한 것만으로는 저장소에 반영되지 않습니다.
  GitHub 이슈 화면에서 반드시 `Submit new issue`를 눌러야 합니다.
- 공개 저장소에서는 검토 이슈 내용도 공개됩니다. 일정 정보와 기사 URL만
  입력하고 비밀번호·API Key·개인정보를 입력하지 않습니다.
