# v3.2 업그레이드 방법

v3.2는 v3.1의 진단 결과를 반영한 안정성 업데이트입니다.

## 먼저 보존할 파일

이미 실제 검토·수집 데이터가 있는 저장소라면 아래 파일은 새 ZIP의 빈
파일로 덮어쓰지 마세요.

```text
data/events_history.csv
data/review_queue.csv
data/review_log.csv
data/daily_collected.csv
docs/calendar_events.json
docs/review_queue.json
```

GitHub Desktop에서 기존 저장소 폴더를 연 뒤, v3.2 ZIP의 나머지 파일을
같은 위치에 복사하는 방식이 가장 안전합니다.

## 교체할 핵심 파일

```text
.github/workflows/
src/kpop_notice_collector/
tests/
docs/index.html
README.md
requirements.txt
config/
scripts/
```

`.env`는 복사하거나 커밋하지 않습니다. 기존 GitHub Actions Secret은
그대로 사용합니다.

## 적용 순서

1. ZIP을 풉니다.
2. 위의 실제 데이터 파일을 보존한 채 v3.2 파일로 교체합니다.
3. GitHub Desktop에서 변경 목록에 `.env`나 API Key가 없는지 확인합니다.
4. 커밋 메시지에 `Upgrade tracker to v3.2`를 입력해 커밋합니다.
5. `Push origin`을 누릅니다.
6. GitHub의 `Actions → Daily K-pop activity tracker → Run workflow`를
   한 번 수동 실행합니다.
7. `collect`와 `deploy-pages`가 모두 성공하는지 확인합니다.
8. 캘린더의 검토 화면에서 페이지 이동, 일괄 승인/Reject, 결정 취소를
   확인합니다.

## 업그레이드 직후 참고

- 기존 브라우저에 30건을 넘는 작성 결정이 남아 있으면
  `작성 결정 전체 취소`로 정리한 뒤 다시 검토하세요.
- 새 버전은 검토 목록을 30건씩 나눠 표시합니다.
- 과거 v3.0 형식 이력은 추가 회차 판정에 사용하지 않습니다.
- 기존 확정 일정과 검토 이력은 위 데이터 파일을 보존했다면 유지됩니다.
