# v2.x에서 v3.0으로 교체

가장 간단한 방법은 기존 저장소의 Secret을 유지한 채 파일을 전부 v3.0으로
교체하는 것입니다.

## 교체 전에 다운로드할 파일

기존 일정이 필요하면 다음 파일을 먼저 내려받습니다.

```text
data/events_history.csv
data/daily_collected.csv
```

기존 결과의 오탐이 많아 새로 시작하려면 백업만 하고 v3.0의 빈 파일을
그대로 사용합니다.

## 교체 후 확인

```text
.github/workflows/daily.yml
.github/workflows/backfill.yml
.github/workflows/review.yml
config/activity_entities.json
data/review_queue.csv
data/review_log.csv
docs/review_queue.json
```

## 실행 순서

1. `Daily K-pop activity tracker` 수동 실행
2. Pages 화면 확인
3. `Backfill K-pop calendar`을 회사별로 실행
4. 웹 검토 대기에서 확정·제외
5. GitHub 이슈를 제출해 반영

