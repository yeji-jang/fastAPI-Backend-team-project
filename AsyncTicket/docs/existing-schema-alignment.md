# 기존 PostgreSQL 스키마 정합성 확인

앱 시작의 `create_all()`은 이미 존재하는 테이블의 PK나 NULL 제약을 변경하지 않는다.
이전 스키마를 쓰는 개발 DB에서는 새 JWT 로그아웃 기록, 예매 전 좌석, 실패 결제 저장이
기존 제약 때문에 실패할 수 있다. 앱이 자동으로 스키마를 바꾸지 않도록 보정은 명시적으로 실행한다.

## 보정 범위

- `blacklist`: `jti_token`을 PK로 사용한다. 기존 `black_id`, `user_id` 값과 컬럼은 보존한다.
  자동 생성되는 identity는 유지하고, 새 코드가 채우지 않는 일반 legacy 컬럼의 필수값 제약만 완화한다.
- `performance_seats.reserv_id`, `payments.reserv_id`: 연결 전 행을 저장할 수 있도록 NULL을 허용한다.
- 예매의 `confirmed_at`: 명시적으로 저장한 확정시각을 이후 상태 변경에서 자동으로 덮지 않는다.

## 실행

기존 접속 환경 변수가 설정된 프로젝트 루트에서 실행한다. 대상은 명시한 이름의 로컬 PostgreSQL DB다.
실행 전 백업과 팀의 스키마 정책을 확인한다. 원격 DB에는 적용하지 않는다.

```powershell
uv run --frozen python scripts/align_existing_schema.py --expected-database asyncticket_dev
```

기본 실행은 실제 DDL을 트랜잭션 안에서 시험하고 **rollback**한다. 따라서 잠금은 발생하지만
변경은 남지 않는다. 결과를 확인한 뒤 적용할 때만 `--apply`를 추가한다.

```powershell
uv run --frozen python scripts/align_existing_schema.py --expected-database asyncticket_dev --apply
```

보정 중 세 테이블을 잠그며 CLI의 잠금 대기는 5초, 문장 제한은 30초다.
중복·NULL·500자를 넘는 토큰 ID나 지원하지 않는 PK는 자동 정리하지 않고 실패한다.
이전 PK를 참조하는 예상 밖 FK가 있으면 CASCADE 없이 실패하며 전체 트랜잭션을 rollback한다.
기존 행 삭제나 legacy 컬럼 삭제를 하지 않는다. 적용 후 재실행은 변경 없음으로 끝나야 한다.

## 검증

```powershell
uv run --frozen python -B -m unittest discover -s tests -p test_reservation_timestamps.py -v
uv run --frozen python -B -m unittest discover -s tests/postgres -v
```

PostgreSQL 테스트는 `ASYNCTICKET_TEST_DATABASE_URL`을 명시했을 때만 실행한다.
이름에 `local` 또는 `test`가 들어간 로컬 전용 DB를 사용한다. 테스트마다 임시 스키마에
기존 행을 넣어 보존·새 로그아웃 행 저장·NULL 예매 연결·재실행·중복 거절·rollback을 검사하고,
스키마 생성과 테스트 데이터를 모두 rollback한다. 실제 운영 스키마에는 적용하지 않는다.

JWT 서명키는 `JWT_SECRET_KEY` 환경 변수로 각 개발 환경에서 별도로 관리한다.
실제 키·토큰·비밀번호는 문서나 Git에 기록하지 않는다. 설정 누락 503 회귀 테스트는
현재 개발자의 JWT 설정 유무와 무관하게 실행된다.
