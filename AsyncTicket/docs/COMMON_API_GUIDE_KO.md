# AsyncTicket 공통 모듈 — 튜터 원문 기준

2026-11-04 사용자가 제공한 수업 자료로 교체했다.
DB 연결(database.py)·로거(logger.py)는 교체하지 않았다.

## 파일과 적용

- shared/core/schemas.py: 튜터 APIResponse 원문. 성공은 ok(data=...), 실패는 fail(...).
- shared/core/exceptions.py: 튜터 SharedException 및 400/401/403/404/409/422 예외 원문.
- shared/core/exception_handlers.py: 튜터 업무 예외·요청 검증 오류·미처리 오류 처리기 원문.
- shared/core/models.py: 튜터 Base·DateTimeBase. init_models의 import만 실제 팀A 모델로 유지.
- wiring/__init__.py·wiring/seats.py: 튜터의 공용 wire_dependencies 진입점에 기존 좌석 DI 연결을 보존.
- main.py: 공통 처리기·공용 wiring 연결. 기존 create_app·라우터·인증 설정과
  시작 실패에도 DB 풀을 정리하는 try/finally는 기존 팀 코드대로 보존.

튜터 자료의 shared.core import는 asyncticket.shared.core로 변경했다.
쇼핑몰 이름·user 단독 모델 등록은 팀A 이름과 실제 모델 등록으로 맞췄다.
pyproject.toml의 package=false는 넣지 않았다. 팀A는 src/asyncticket 패키지를
유지하며 실제 uv 실행에 사용한다. 추가 인증 라이브러리도 이 교체로 설치하지 않았다.

## 팀원 적용

성공: 자기 DTO를 APIResponse[자기DTO].ok(data=...)로 반환하고 라우터의
response_model도 APIResponse[자기DTO]로 맞춘다. 201과 Location은 유지하며
본문 없는 204는 감싸지 않는다. 성공 자동 래핑은 없다.

실패: 공통 예외를 직접 사용하거나 상속한다.

```python
from asyncticket.shared.core.exceptions import NotFoundException

# 각 담당자의 서비스에서 적용할 예시
# raise NotFoundException("공연을 찾을 수 없습니다.", error_code="SHOW_NOT_FOUND")
```

Catalog 전용 예외 변환표는 없다. 각 담당자가 자기 예외·응답·명세·테스트를
공통 형식으로 전환한다. 다른 담당자 코드는 이번 교체에서 수정하지 않았다.
main.py는 register_catalog_errors 대신 register_exception_handlers를 등록한다.
따라서 전환하지 않은 Catalog 예외는 기존 4xx 의미를 자동 유지하지 못하고
미처리 500으로 처리될 수 있다. 팀 전체 적용 완료로 간주하지 않는다.

## 튜터 원문 그대로인 동작과 한계

- errors는 Any를 포함하며, 공통 예외 파일은 fastapi.status를 사용한다.
- HTTPException과 프레임워크의 없는 경로 404는 FastAPI 기본 처리를 유지한다.
  모든 HTTP 오류가 APIResponse로 감싸지는 것은 아니다.
- SharedException 401에는 별도 WWW-Authenticate 헤더 추가 기능이 없다.
- 미처리 예외는 logger.exception으로 기록하고 일반 500 메시지로 응답한다.
- DateTimeBase의 datetime.now(...)는 원문처럼 클래스 정의 시 평가된다.
  저장마다 새 시간이 계산되는 함수 기본값과 다르다. 현재 팀 모델에는 이 믹스인을
  새로 상속시키지 않았고, updated_at을 modified_at으로 변경하지 않았다.

## 검사

```sh
uv run --with httpx python -B -m unittest discover -s tests/shared_core -v
```

별도 FastAPI 앱에서 성공·업무 상태·422·기본 HTTPException/404·500 마스킹을
검사한다. 실제 DB·JWT·전체 팀 도메인의 통합 성공을 증명하지 않는다.


## 좌석 API 적용 상태

2026-11-04: seats의 목록·상세 GET을 APIResponse로 감쌌다. data 안은 기존
SeatListResponse/SeatResponse 필드를 유지한다. 서비스의 404·409·422와 좌석 식별
중복의 500을 공통 예외에 연결했다. 다른 담당자의 라우터·모델은 변경하지 않았다.
검사는 좌석 전용 FastAPI 앱과 메모리 SQLite로 실행하며 팀 전체 DB 시작과 구분한다.

```sh
uv run --with httpx --with aiosqlite python -B -m unittest discover -s tests/seat_queries -v
```

## 좌석 도메인 분리

- `seats/`: 좌석 등급 설정(`SeatInfo`, `SeatsInfoModel`), 등급 저장소·서비스.
- `performance_seats/`: 개별 판매 좌석(`PerformanceSeat`, `PerformanceSeats`), 조회·예매 연결 서비스와 기존 좌석 API.
- `wiring/seats.py`, `wiring/performance_seats.py`에서 각각 연결한다.
- 기존 API 경로, 테이블명, 컬럼과 FK는 유지한다. 개별 좌석 저장소는 조회에 필요한 등급 ORM을 참조한다.
