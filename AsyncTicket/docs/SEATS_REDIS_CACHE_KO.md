# 좌석 표시 정보 캐시

## 범위와 호출 흐름

`GET /v1/performances/{perf_id}/seats`에서 좌석명·등급·가격만 Redis에 보관한다.
현재 예매 상태·예매 ID·구매자 정보는 캐시에 저장하지 않는다.

```text
회차 존재 확인
  → Redis 메타데이터 조회
    → 미스: 기존 DB 목록 조회 → 상태를 제외하고 10초 저장 → 결과 반환
    → 히트: DB에서 현재 좌석 ID·상태 조회 → 표시 정보와 합쳐 반환
      → 좌석 ID 목록이 다름: 기존 DB 목록 재조회 → 캐시 재저장
```

빈 목록 `[]`도 히트다. 다른 회차·중복 ID·잘못된 JSON·구버전 형식은 미스로 처리한다.
기존 응답 형식은 유지한다. 캐시 히트에서도 회차 존재와 현재 상태를 DB에서 읽으므로
DB 요청 수가 0이 되거나 응답 시간이 반드시 빨라진다는 보장은 없다.
등급·좌석명·가격 필드를 반복해서 가져오는 일을 줄이는 첫 구현이다.

## 계층별 위치

- `seats/application/ports.py`: 표시 정보 캐시 계약.
- `seats/infrastructure/cache.py`: Redis JSON 직렬화·키·TTL·통신 실패 처리.
- `seats/application/service.py`: 조회 순서와 커밋 이후 캐시 삭제 조율.
- `seats/domain/repository.py`: 현재 상태 조회 계약. 기존 구현을 위한 기본 조회 제공.
- `seats/infrastructure/repositories.py`: 현재 좌석 ID·상태 두 컬럼만 SELECT.
- `wiring/performance_seats.py`, `wiring/seats.py`: 선택적 캐시 주입과 요청 종료 시 연결 정리.

엔티티 업무 규칙, 예매·결제 코드, 공용 `get_db()`·앱 lifespan·DB 스키마는 수정하지 않는다.
패키지 의존성 때문에 `pyproject.toml`과 `uv.lock`에 `redis`만 추가한다.

## 커밋과 실패 처리

좌석 구성 생성·가격 변경은 DB 커밋에 성공한 다음 해당 회차 키를 삭제한다.
DB 작업이 실패하면 롤백하고 캐시는 삭제하지 않는다.
Redis 삭제 실패는 경고만 남기며 이미 성공한 DB 저장을 실패로 바꾸거나 롤백하지 않는다.

Redis 통신은 작업당 0.25초로 제한한다. 캐시 읽기 실패는 기존 DB 조회로 돌아간다.
키: `seats:metadata:v1:{perf_id}`, TTL: 10초.

가격·등급 정보는 삭제 실패 또는 동시 조회의 늦은 캐시 저장 때문에 TTL 동안 오래된 값일 수 있다.
커밋 후 삭제만으로 완벽한 최신 가격을 보장하는 설계는 아니다.
예매 가격 확정과 좌석 연결 가능 여부는 기존 팀 API와 PostgreSQL이 판단한다.
선점·해제 후 캐시 삭제를 다른 도메인에 요청할 필요는 없다. 상태는 매번 DB에서 읽는다.

## 개인 로컬에서 켜기

로컬 Redis 컨테이너 `asyncticket-seat-cache-1110`은 `127.0.0.1:56379`에만 공개되어 있다.
비영속 캐시이며 최대 메모리는 64MB다. 팀 EC2/RDS는 이번 작업에서 변경하지 않는다.

```sh
uv sync --frozen
SEAT_CACHE_REDIS_URL=redis://127.0.0.1:56379/0 \
  uv run uvicorn asyncticket.main:app --host 127.0.0.1 --port 8006
```

환경변수가 없거나 빈 값이면 기존 DB 조회만 사용한다. 주소는 개인 `.env`에 넣어도 된다.
앱에서 DB의 `DATABASE_URL`과 Redis의 `SEAT_CACHE_REDIS_URL`은 별개다.
Redis 연결은 좌석 요청에만 만들고 요청 종료 시 닫는다. 요청 간 풀 재사용은 이번 범위에서 제외한다.

조회 후 내 로컬 키의 실제 내용과 만료 시간을 확인한다.

```sh
docker exec asyncticket-seat-cache-1110 redis-cli GET seats:metadata:v1:10
docker exec asyncticket-seat-cache-1110 redis-cli TTL seats:metadata:v1:10
```

`10`은 실제 개인 DB의 회차 ID로 바꾼다. `status`와 `reserv_id`는 키 내용에 없어야 한다.

## 검사

```sh
SEAT_CACHE_TEST_REDIS_URL=redis://127.0.0.1:56379/9 \
  uv run --with pytest --with httpx --with aiosqlite \
  pytest -q tests/test_seat_cache.py tests/seat_queries/test_cache.py
```

실제 Redis 검사는 무작위 회차 키만 쓰고 해당 키만 정리한다. `FLUSHDB`를 호출하지 않는다.
미스·히트·빈 목록·현재 상태 변경·목록 변경·장애 대체·캐시 오염·커밋 순서·TTL 만료를 검사한다.
실제 Redis 주소가 없으면 Redis 통합 검사만 건너뛴다.

참고: [Redis 비동기 연결 정리](https://redis.readthedocs.io/en/stable/examples/asyncio_examples.html),
[Redis 운영 시 타임아웃과 재시도](https://redis.io/docs/latest/develop/clients/redis-py/produsage/).
