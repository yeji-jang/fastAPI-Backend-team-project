# 공연·공연회차 조회 캐시

`fastapi-cache2`의 `InMemoryBackend`로 공개 조회 결과를 프로세스 메모리에 보관한다.
별도 Redis 서버나 Redis 접속 환경변수는 사용하지 않는다.

## 적용 위치

- `main.py`: lifespan에서 `init_catalog_cache(app)` 실행, 종료 시 해당 앱 키 정리.
- 공연·회차 표현 계층: 공개 `data`를 만드는 함수에 `@cache` 적용.
- 조회 라우터: 매 요청에 공통 `APIResponse`를 새로 만들어 `responded_at` 유지.
- 생성·수정·삭제 라우터: 서비스의 DB commit 성공 후 관련 조회 캐시 무효화.

도메인·저장소·공통 인증·DB 트랜잭션·응답 스키마는 기존 구현을 사용한다.
권한과 행 잠금에 쓰이는 `find_by_id()`는 캐시로 바꾸지 않는다.
회차 목록은 cache hit이어도 부모 공연의 존재를 DB에서 확인한다.

## TTL

| 공개 API | TTL |
| --- | --- |
| `GET /v1/shows` | 30초 |
| `GET /v1/shows/{show_id}` | 60초 |
| `GET /v1/shows/{show_id}/performances` | 10초 |
| `GET /v1/performances/{perf_id}` | 10초 |

TTL은 조회 결과의 유효기간이다. 응답을 그 시간만큼 기다리거나 일정 간격으로
DB를 자동 조회한다는 의미는 아니다. 이 값은 시작 설정이며 실제 부하와 표시 최신성
요구에 맞춰 조정한다. InMemory 방식에는 Redis socket timeout 설정이 없다.

## 키와 변경 후 처리

키는 앱 scope, 도메인, 변경 세대, 조회 함수, 검증된 조회 조건을 구분한다.
요청마다 새로 만들어지는 서비스 객체는 키에서 제외한다.

- 공연 목록: page/size/keyword/type/venues_id.
- 공연 상세: show_id.
- 회차 목록: show_id/date, 기존 KST 날짜 해석 유지.
- 회차 상세: perf_id.

공연 생성·수정은 shows 캐시를, 공연 삭제는 shows/performances 캐시를 무효화한다.
회차 생성·수정·삭제는 performances 캐시를 무효화한다.
DB 저장이 실패하면 캐시 세대를 바꾸지 않는다. 성공 후 먼저 세대를 올리고
이전 키를 정리하므로, 이전 조회가 늦게 저장한 결과는 다음 요청에서 사용하지 않는다.
캐시 삭제 실패도 이미 성공한 DB 저장을 실패로 바꾸지 않는다.

## 실행과 확인

```sh
uv sync --frozen
uv run uvicorn asyncticket.main:app --host 127.0.0.1 --port 8000
```

기존 DB/JWT 설정과 서버 시작 절차를 따른다. API 경로·요청·응답 필드와
CORS 설정은 변경하지 않는다. 인위적인 대기 코드는 추가하지 않는다.

테스트용 SQLite 의존성을 임시로 포함한 검사 예시:

```sh
uv run --frozen --with aiosqlite python -m unittest discover -s tests -v
uv run --frozen --with aiosqlite python -m unittest discover -s tests/seat_queries -v
```

`test_catalog_cache.py`는 miss/hit, 조건별 키, TTL, 변경 후 무효화, 앱 격리,
응답 시각 갱신, 삭제 실패와 늦은 재저장, 캐시 없는 앱을 검사한다.
루트 discover가 자동 수집하지 않는 다른 도메인 폴더는 각각 별도 검사한다.
실제 PostgreSQL·부하·배포 환경 검증과 이 로컬 테스트를 구분한다.

## 범위와 한계

- 캐시는 프로세스별로 분리된다. 여러 worker 사이에 데이터·무효화가 공유되지 않는다.
- 서버를 재시작하면 캐시를 다시 채운다.
- 앱 밖의 직접 DB 변경이나 다른 프로세스의 변경은 TTL 동안 이전 값으로 보일 수 있다.
- `InMemoryBackend`는 만료 값을 조회 시 정리한다. 임의의 검색 조건을 많이 만드는
  장시간 시험에서는 저장 공간 사용량도 관찰한다.
- 동시에 같은 키가 miss이면 DB 조회가 여러 번 실행될 수 있다. 이 구현이
  cache stampede 방지나 실제 처리량 개선을 입증한 것은 아니다.

기술 참고: [fastapi-cache 공식 저장소](https://github.com/long2ice/fastapi-cache).
