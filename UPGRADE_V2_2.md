# GitHub v2.2 교체 순서

1. 현재 예약 실행을 잠시 중단합니다.
   - 저장소 상단 `Actions`
   - 왼쪽 `Daily K-pop activity tracker`
   - 오른쪽 `···` 메뉴
   - `Disable workflow`
2. v2.2 ZIP을 압축 해제합니다.
3. 저장소의 기존 파일을 v2.2 파일로 덮어씁니다.
4. 점으로 시작하는 `.github`와 `.streamlit`은 누락되지 않았는지 확인합니다.
5. 아직 v2.1을 정상 실행한 적이 없거나 기존 오탐 이력이 남아 있다면, 다음
   파일을 v2.2의 빈 파일로 교체합니다.

```text
data/events_history.csv
data/daily_collected.csv
```

6. `.github/workflows/daily.yml`에서 다음 버전을 확인합니다.

```yaml
actions/checkout@v5
actions/setup-python@v6
actions/upload-artifact@v6
```

7. 기존 GitHub Secrets는 그대로 사용합니다.

```text
NAVER_API_KEY_ID
NAVER_API_KEY
```

8. `Settings → Pages → Build and deployment → Source`에서 `GitHub Actions`를 선택합니다.
9. `Actions → Daily K-pop activity tracker → Run workflow`로 수동 실행합니다.
10. 로그에서 59팀 진행 상황과 `api_errors=0`을 확인합니다.
11. Excel의 `daily_selected`, `validation_queue`, `source_runs`를 우선 검토합니다.
12. `deploy-pages` 작업에 표시되는 캘린더 URL을 엽니다.
13. 결과가 정상이라면 같은 `···` 메뉴에서 `Enable workflow`를 누릅니다.
