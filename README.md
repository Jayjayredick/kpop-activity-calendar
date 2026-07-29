# 4사 K-pop 활동 추적기 v2.2

HYBE·SM·JYP·YG 59팀의 NAVER 뉴스를 매일 검색해 신규 활동을 선별하고 Excel과 웹 캘린더를 갱신합니다.

GitHub Pages 캘린더는 컴백을 기본 표시하며 회사·활동 유형 필터를 제공합니다. 표시 기간은 실행일을 포함한 향후 3개월로 제한됩니다.

## v2.2 변경점

- 엔터사·레이블 공식 홈페이지 수집 제외
- 아티스트×활동 키워드 검색을 아티스트당 대표 검색어 1개로 축소
- NAVER 결과를 최신순으로 받아 `pubDate` 기준 직전 24시간만 처리
- 24시간 밖 기사는 Excel 행으로 저장하지 않고 검색 로그에 건수만 기록
- 기사 제목에 정확한 아티스트명과 활동 키워드가 함께 있어야 자동 선별
- `있지`, `범주`, `TEAM` 등 일반 단어와 충돌하는 별칭 차단
- 티저·인터뷰·차트·성료·종료·취소·활동 중단 기사 제외
- `8월 10일`, `8월 10~11일`, `내달 5일` 날짜 인식
- 동일 이벤트의 여러 기사를 대표 기사 1건으로 통합
- Node.js 24 대응 GitHub Actions 버전 적용
- GitHub Pages용 향후 3개월 캘린더 자동 배포

## 추적 활동

- 컴백·신보 발매
- 투어 발표
- 투어 확장·도시 추가
- 추가 회차·추가 공연
- 앙코르 콘서트
- 팬미팅·팬콘
- 팝업스토어

## NAVER의 24시간 처리 방식

NAVER 뉴스 검색 API에는 검색 화면과 같은 별도의 `24시간` 요청 파라미터가 없습니다. v2.1은 다음과 같이 처리합니다.

1. `sort=date`로 최신 기사부터 조회
2. API 응답의 `pubDate`를 Asia/Seoul로 변환
3. 실행 시각에서 24시간을 뺀 시각보다 오래된 기사는 즉시 제외
4. 한 페이지의 가장 오래된 기사가 24시간 경계를 넘으면 다음 페이지 조회 중단
5. 범위 밖 기사 수만 `source_runs`에 기록

## 로컬 설정

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

`.env`에 NAVER API HUB 값을 입력합니다.

```text
NAVER_API_KEY_ID=발급받은_API_Key_ID
NAVER_API_KEY=발급받은_API_Key
```

`.env`는 GitHub에 올리지 않습니다.

## 수집 실행

```bash
PYTHONPATH=src python -m kpop_notice_collector.cli \
  --hours 24 \
  --out output/latest_activity_tracker.xlsx
```

Windows PowerShell:

```powershell
$env:PYTHONPATH="src"
python -m kpop_notice_collector.cli --hours 24 --out output/latest_activity_tracker.xlsx
```

## Excel 시트

- `daily_selected`: 이벤트별 대표 기사
- `calendar_events`: 누적 일정 DB
- `raw_articles`: 대표 기사의 검색 패시지
- `excluded`: 최근 24시간 기사 중 제외된 대표 사례
- `source_runs`: 아티스트별 API 호출·최근 기사·24시간 밖 기사 수
- `validation_queue`: 날짜가 없거나 추가 확인이 필요한 이벤트
- `run_params`: 실행 조건

## GitHub Secrets

저장소에서 다음 경로로 등록합니다.

```text
Settings
→ Secrets and variables
→ Actions
→ New repository secret
```

등록 이름:

```text
NAVER_API_KEY_ID
NAVER_API_KEY
```

## 예약 실행

`.github/workflows/daily.yml`은 매일 오전 07:35 KST에 실행됩니다.

```yaml
cron: "35 22 * * *"
```

GitHub Actions 예약은 UTC 기준이며 서버 상황에 따라 실제 시작이 지연될 수 있습니다.

## GitHub Pages 캘린더 최초 설정

저장소에서 아래 메뉴로 이동합니다.

```text
Settings
→ Pages
→ Build and deployment
→ Source
→ GitHub Actions
```

저장 후 `Actions → Daily K-pop activity tracker → Run workflow`를 실행합니다.
완료된 실행 화면의 `deploy-pages` 작업에 표시되는 URL이 캘린더 주소입니다.

캘린더 작동 방식:

- 기본 화면에는 `컴백` 일정만 표시
- HYBE·SM·JYP·YG 및 활동 유형 버튼으로 필터
- 오늘부터 정확히 3개월 뒤까지의 날짜만 탐색
- 일정 클릭 시 해당 NAVER 검색 기사의 원문으로 이동
- 매일 수집 후 `docs/calendar_events.json`을 재생성하여 Pages에 배포

주의:

- 개인 GitHub Free 계정은 비공개 저장소의 Pages를 사용할 수 없습니다. 이 경우
  GitHub Pro 이상이 필요하거나 저장소를 공개해야 합니다.
- 일반적인 GitHub Pages 사이트는 저장소가 비공개여도 인터넷에 공개될 수 있습니다.
  비공개 Pages는 GitHub Enterprise Cloud 조직 기능입니다.
- 캘린더에는 일정과 기사 URL만 들어가며 API Key는 포함되지 않습니다.

## v2에서 업그레이드할 때

첫 실행에서 생성된 오탐 일정이 남지 않도록 다음 두 파일을 v2.1의 빈 파일로 반드시 교체합니다.

```text
data/events_history.csv
data/daily_collected.csv
```

그 후 전체 v2.1 파일을 저장소에 덮어쓰고 Actions를 수동 실행합니다.

## 검증 기준

최초 1~2주간 `data/manual_truth_template.csv`에 실제 이벤트를 누적 기록합니다.

- 정확한 아티스트가 제목에 있는가
- 활동이 새롭게 발표된 것인가
- 완료·성료·티저·인터뷰가 아닌가
- 날짜·도시·행사명이 맞는가
- 동일 이벤트가 하나로 묶였는가

Streamlit의 `수동 검증` 탭에서 정밀도와 재현율을 계산합니다.

## 보안

- API Key를 코드·CSV·Excel·채팅·커밋에 넣지 않습니다.
- 로컬은 `.env`, GitHub는 Repository Secrets만 사용합니다.
- `.env.example`에는 실제 값을 입력하지 않습니다.
