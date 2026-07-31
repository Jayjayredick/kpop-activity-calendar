# 4사 K-pop 활동 추적기 v3.2

HYBE·SM·JYP·YG의 그룹, 등록된 솔로·유닛을 NAVER 뉴스 검색 API로 점검하고
확정 캘린더와 검토 대기 목록을 GitHub Pages에 갱신합니다.

업그레이드는 `UPGRADE_V3_2.md`, 검증 내역은 `VALIDATION_V3_2.md`를
참고하세요.

## v3.2 진단 후 안정성 개선

- `3일간`, `3일 후`, `3일 만에`를 월중 날짜로 오인하지 않음
- 가운데점(`·`)으로 나열된 서로 다른 날짜를 기간으로 합치지 않음
- 같은 날짜·도시라도 행사명이 다르면 별도 일정으로 유지
- 기사 URL에서 `utm_*` 등 추적값만 제거하고 `article_id`, `aid` 등 식별값 보존
- 행사명 추출 로직이 바뀌어도 URL 기준 검토 후보 ID 유지
- Reject한 후보는 `candidate_id`와 `event_key`를 모두 확인해 재등장 억제
- Excel·내부 CSV에서 외부 문구가 수식으로 실행되지 않도록 보호
- 캘린더·검토 링크는 `http`와 `https`만 허용
- 캘린더의 오늘 날짜를 한국 시간으로 계산
- 검토 목록을 30건씩 페이지로 표시하고, 개별·전체 결정 취소 지원
- GitHub 이슈 URL 길이를 줄이기 위해 변경된 필드만 제출
- 검토 반영은 한 요청당 최대 30건이며 URL 길이도 제출 전 검사
- v3.0 형식의 과거 이력은 추가 회차 판정에서도 제외

## v3.1 날짜 안전성 개선

- 제목의 명시 날짜를 기사 설명문 날짜보다 우선
- 제목의 단일 일자와 설명문의 동일 시작일 범위만 제한적으로 결합
- 서로 다른 날짜가 충돌하면 날짜를 비우고 `DATE_CONFLICT` 검토 대기로 이동
- 과거 월을 다음 해로 자동 변경하지 않음
- 중복 기사의 날짜를 합집합으로 만들지 않고 가장 신뢰도 높은 대표 날짜만 선택
- 날짜가 명확하게 다른 행사는 행사명이 같아도 별도 이벤트로 보존
- 날짜 보강 검색도 행사명이 강하게 일치하고 날짜 다수결이 성립할 때만 반영
- 자동 확정 기본값을 끄고 모든 수집 후보를 소유자 검토 대상으로 전환
- 백필의 날짜 미확정 후보는 아티스트·활동별 상위 2건만 유지
- 콘서트 기사 속 신곡명·무대명을 행사명으로 오인하는 사례 차단
- 검토 화면에서 회사·활동·날짜 상태·검색어 필터 제공
- 선택 항목 `일괄 승인`·`일괄 Reject` 지원

## 기존 v3.0 핵심 기능

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

v3.2는 다음 구조를 사용합니다.

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

새 저장소라면 v3.2 전체 파일을 업로드합니다. 기존 저장소를 업그레이드할
때는 실제 수집 데이터 보존 방법이 있는 `UPGRADE_V3_2.md`를 먼저 읽으세요.
다음 숨김 항목도 반드시 업로드되어야 합니다.

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
2. 회사·활동·날짜 상태·검색어 필터로 검토 범위를 축소
3. 개별 항목의 행사명·활동 유형·시작일·종료일·도시·공연장을 수정
4. 개별 확정·제외 또는 선택 항목 `일괄 승인`·`일괄 Reject` 실행
5. 여러 건을 검토한 뒤 `GitHub에 반영 요청` 클릭
6. 열린 GitHub 화면에서 `Submit new issue` 클릭
7. `Actions → Apply calendar review` 완료 확인

일괄 작업은 GitHub 이슈 URL 길이와 안전한 재검토를 위해 한 요청당 최대
30건입니다. 날짜가 없는 항목은 일괄 승인에서 자동으로 건너뜁니다.

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
- v3.0에서 생성된 검토 대기와 확정 일정은 날짜 병합 오류가 섞였을 수
  있으므로 v3.2의 빈 `data/*.csv`와 `docs/*.json`으로 초기화한 뒤 다시
  수집해야 합니다.
- 자동 확정은 기본적으로 꺼져 있습니다. 검토 대기에서 승인한 일정만
  확정 캘린더에 표시됩니다.
- 웹에서 결정을 작성한 것만으로는 저장소에 반영되지 않습니다.
  GitHub 이슈 화면에서 반드시 `Submit new issue`를 눌러야 합니다.
- 공개 저장소에서는 검토 이슈 내용도 공개됩니다. 일정 정보와 기사 URL만
  입력하고 비밀번호·API Key·개인정보를 입력하지 않습니다.
