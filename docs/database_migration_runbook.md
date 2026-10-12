# 운영 DB migration 실행 절차

## 목적

Alembic migration을 적용할 때 데이터 손실을 막고 실패 시 검증된 백업으로 복구하기 위한 최소 운영 절차다. 실제 운영 DB 제품과 보관 위치, 담당자는 배포 전에 별도로 확정한다.

## 적용 전

1. 배포할 애플리케이션 커밋과 목표 Alembic revision을 기록한다.
2. 스케줄러와 쓰기 요청을 중지한다.
3. DB 연결 문자열이 대상 운영 환경을 가리키는지 확인한다.
4. DB 제품에 맞는 일관된 백업을 만든다.
5. 백업 파일을 원본 DB와 다른 저장 위치에 보관한다.
6. 임시 DB에 백업을 복원해 열 수 있는지 확인한다.

SQLite는 쓰기 중지 후 `sqlite3`의 `.backup` 명령을 사용한다. PostgreSQL은 운영 버전과 호환되는 `pg_dump --format=custom`과 `pg_restore`를 사용한다. 자격 증명은 명령 기록이나 저장소에 남기지 않는다.

## migration 적용

애플리케이션이 사용하는 것과 같은 `DATABASE_URL`을 설정한 뒤 다음 진입점을 실행한다.

```powershell
uv run python -c "import os; from app.core.migrations import migrate_database; migrate_database(os.environ['DATABASE_URL'])"
```

적용 직후 다음을 확인한다.

1. `alembic_version.version_num`이 배포 목표 revision과 같다.
2. 애플리케이션 `/health`가 성공한다.
3. 로그인 세션 확인, 관심 종목 조회와 사용자별 브리핑 조회가 성공한다.
4. 다른 사용자 데이터 접근이 계속 거부된다.
5. 스케줄러를 다시 시작한 뒤 중복 브리핑이 생성되지 않는다.

## 실패 시 복구

1. 애플리케이션과 스케줄러를 계속 중지한 상태로 둔다.
2. 실패 시각, 오류와 현재 revision을 기록한다.
3. 되돌리기 migration이 검증된 경우 애플리케이션 코드를 이전 버전으로 되돌린 뒤 해당 revision으로 downgrade한다.
4. downgrade로 데이터 안전을 보장할 수 없거나 적용 중간에 실패했다면 손상된 DB를 보존하고 검증한 백업을 새 DB 위치에 복원한다.
5. 이전 애플리케이션 버전으로 smoke test를 수행한 뒤 쓰기 요청과 스케줄러를 재개한다.

운영 데이터가 있는 DB에서 검증 없이 `downgrade`를 먼저 실행하지 않는다. 최신 migration의 자동 왕복 테스트는 스키마 되돌리기 가능성을 확인할 뿐 운영 데이터 백업을 대체하지 않는다.

## 현재 자동 검증

- 빈 DB를 최신 revision으로 upgrade한다.
- 알려진 legacy DB를 데이터 손실 없이 stamp·upgrade한다.
- 알 수 없는 기존 스키마는 자동 stamp하지 않는다.
- 브리핑 migration을 이전 revision으로 downgrade한 뒤 다시 head로 upgrade한다.
- GitHub Actions에서 전체 Python·Electron 테스트를 실행한다.

## 배포 전에 채워야 할 운영 값

| 항목 | 결정 값 |
| --- | --- |
| 운영 DB 제품·버전 | 미정 |
| 백업 저장 위치·암호화 | 미정 |
| 백업 보존 기간 | 미정 |
| migration 실행 담당자 | 미정 |
| 허용 점검 시간 | 미정 |
| 복구 목표 시간 | 미정 |
| 실제 복구 훈련 일시·결과 | 미정 |
