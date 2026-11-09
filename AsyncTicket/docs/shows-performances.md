# 공연·공연회차 API 명세 대응

공연 5개와 공연회차 5개, 총 10개 API를 구현한다.
[4계층과 코드 흐름 설명](four-layer-guide.md)을 먼저 읽으면 각 파일의 역할을 확인할 수 있다.

## 명세와 코드 대응표

| 기능 | Method | Path | 성공 | 라우터 → 서비스 |
| --- | --- | --- | --- | --- |
| 공연 목록 | GET | `/v1/shows` | 200 | `get_list_show` → `find_all` |
| 공연 상세 | GET | `/v1/shows/{show_id}` | 200 | `get_detail_show` → `find_by_id` |
| 공연 등록 | POST | `/v1/shows` | 201 + Location | `create_show` → `create` |
| 공연 수정 | PATCH | `/v1/shows/{show_id}` | 200 | `update_show` → `update` |
| 공연 삭제 | DELETE | `/v1/shows/{show_id}` | 204, 본문 없음 | `delete_show` → `delete` |
| 공연별 회차 목록 | GET | `/v1/shows/{show_id}/performances` | 200 | `get_list_performance` → `find_all` |
| 회차 상세 | GET | `/v1/performances/{perf_id}` | 200 | `get_detail_performance` → `find_by_id` |
| 회차 등록 | POST | `/v1/shows/{show_id}/performances` | 201 + Location | `create_performance` → `create` |
| 회차 수정 | PATCH | `/v1/performances/{perf_id}` | 200 | `update_performance` → `update` |
| 회차 삭제 | DELETE | `/v1/performances/{perf_id}` | 204, 본문 없음 | `delete_performance` → `delete` |

- 공연 목록은 `page=1`, `size=20`(1~100), `keyword`, `type`, `venues_id`를 받는다.
  `data` 안에 `{items, page, size, total}`을 반환한다. 검색어의 %와 _는 실제 문자로 검색한다.
- 회차 목록은 선택 `date=YYYY-MM-DD`를 받는다. 한국 날짜의 자정 이상~다음 자정 미만을
  조회하고 `data` 안에 `{items}`를 반환한다. 숫자·날짜+시간 문자열은 422다.
  허용 범위는 `0001-01-02`~`9999-12-30`이다. KST 자정의 UTC 변환이 Python의
  최소 연도 아래로 넘어가는 `0001-01-01`은 422로 거절하며 기존 상한도 유지한다.
- 공연 응답의 `data`는 명세의 9개 공개 필드를 반환하고 `user_id`를 제외한다.
  회차 응답은 `perf_id`부터 `status`까지 명세의 9개 필드를 반환한다.
- 공연 등록은 명세의 공연장·제목·소개·출연자·분류·시간을 받는다.
  ID·소유자·등록/수정시각은 본문에서 받지 않는다.
- 회차 등록은 URL의 공연 소속을 사용하고 명세의 시간·회차번호·매수·상태를 받는다.
  매수 생략 기본값은 3이다. status는 필수이며 예시 SCHEDULED를 Enum으로 고정하지 않는다.
- 생성 Location은 각각 `/v1/shows/{show_id}`, `/v1/performances/{perf_id}`다.
- PATCH는 최소 1개 필드, 미지정 값 유지, nullable 값의 null 허용, 불변/알 수 없는 필드 거절이다.
- 없는 대상은 404, 잘못된 입력은 422, 변경 권한 없음은 403, 연결/중복 충돌은 409다.
  성공·실패 JSON은 팀 공통 `APIResponse`를 사용한다.

## 공통 응답·예외 계약

조회·등록·수정의 성공 응답은 `APIResponse[각 DTO].ok(data=...)`다.
기존 DTO가 `data` 아래로 이동했으므로 클라이언트는 `data.show_id`,
`data.perf_id`, `data.items` 등으로 읽는다. 예를 들어 공연 목록은 다음 구조다.

```json
{
  "success": true,
  "code": "OK",
  "message": "요청이 성공적으로 처리되었습니다.",
  "errors": null,
  "data": {"items": [], "page": 1, "size": 20, "total": 0},
  "responded_at": "2026-11-04T05:00:00Z"
}
```

등록은 HTTP 201과 기존 Location을 유지한다. 삭제 성공 2개 API는 HTTP 204이며
JSON 본문이 없으므로 `APIResponse`로 감싸지 않는다. OpenAPI의 성공·오류 스키마도
이 계약을 사용하고 오류의 `data`는 null이다.

| 실패 | HTTP | 공통 응답 code | errors |
| --- | --- | --- | --- |
| 인증 없음·검증 실패 | 401 | AUTHENTICATION_REQUIRED | null |
| 권한 없음 | 403 | PERMISSION_DENIED | null |
| 대상·참조 없음 | 404 | RESOURCE_NOT_FOUND | null |
| 중복·연결 데이터 충돌 | 409 | RESOURCE_CONFLICT | null |
| 도메인 값·시간순서·정책 검증 실패 | 422 | VALIDATION_ERROR | 빈 객체 |
| 요청 형식·필드·자료형 검증 실패 | 422 | REQUEST_VALIDATION_ERROR | 필드별 메시지 배열 |
| 인증 어댑터 미연결 | 503 | INTEGRATION_UNAVAILABLE | null |
| 미처리 내부 오류 | 500 | INTERNAL_SERVER_ERROR | null |

실패는 `success=false`, `data=null`이며 예전 `detail.code/message` 대신 최상위
`code/message`를 읽는다. 요청 오류의 `errors` 키는 `query.page`, `path.perf_id`,
본문 필드명 등이다. 원본 입력·내부 예외·SQL을 응답에 추가하지 않는다.

`main.py`는 팀의 `register_exception_handlers`를 등록한다.
공연·회차의 순수 도메인 예외는 `catalog_http.py`에서 팀 공통 예외로 바꾸고,
이미 등록된 공통 처리기에 전달한다. HTTP 상태와 메시지는 공통 처리기가 생성한다.
이는 `SharedException`을 서비스/도메인에 직접 가져오지 않기 위한 표현 계층 어댑터다.
`register_catalog_errors`는 이 연결만 등록하며 요청 422 처리기를 덮어쓰지 않는다.
401의 `WWW-Authenticate: Bearer`도 이 어댑터에서 유지한다.

공통 모듈과 동일하게 프레임워크의 없는 경로 404나 직접 발생시킨 HTTPException은
FastAPI 기본 처리를 유지한다. 팀 전체 오류가 자동으로 감싸지는 것은 아니다.

## 명세의 제안·미정 사항에 적용한 값

아래는 구현 선택을 명시한 것으로 팀 최종 합의 또는 운영 검증을 의미하지 않는다.

| 항목 | 현재 구현 |
| --- | --- |
| 소유권 | SELLER는 본인 공연만, ADMIN은 전체 관리. `CatalogPolicy`에서 관리 |
| 공연 분류·회차 상태 | 비어 있지 않은 길이 제한 문자열. 최종 허용값이 정해지면 policy allowlist로 설정 |
| 공연 시간·회차번호·매수 | 양수, 매수 기본 3. 최근 회의의 1매 방향을 임의로 적용하지 않음 |
| 시간순서 | 예매 시작 < 예매 마감 ≤ 공연 시작 < 공연 종료, 시간대 필수 |
| 공연 내 회차번호 | 부모 공연 잠금 후 중복 조회, 중복 409. 새 DB UNIQUE 제약을 추가하지 않음 |
| 공연장 변경 | 연결 회차가 있으면 409 |
| 회차 상태 변경 | 좌석 구성/예매가 연결돼 있어도 상태만 변경하는 PATCH 허용. 인증·소유권·상태 허용값 검사 유지 |
| 회차 일정·회차번호·매수 변경 | 연결 좌석 구성/예매가 있으면 실제 값 변경 409. 상태 변경과 섞은 PATCH도 전체 거절. policy로 관리 |
| 삭제 | 공연은 연결 회차 없음, 회차는 연결 좌석정보·예매 없음일 때만 물리 삭제 |
| 좌석 생성·환불 | 이 두 API 영역에서 자동 수행하지 않음. 명세의 별도 처리 경계를 유지 |

예를 들어 좌석 생성 뒤 `PATCH /v1/performances/{perf_id}`에 `{"status": "ON_SALE"}`을
보내면 상태를 변경할 수 있다. `ON_SALE`은 흐름 설명용 예시이며 최종 상태 허용값과
전이 규칙은 팀 합의 후 `CatalogPolicy`에 연결한다. 상태 변경이 예매 취소·환불을
자동 실행하지는 않는다. 삭제 및 연결 데이터 변경 제한은 그대로 적용한다.

공연 목록은 등록시각·ID 내림차순, 회차 목록은 시작시각·ID 오름차순이다.
공연·회차 쓰기의 commit/rollback은 응용 서비스에서 결정하며 변경 실패는 되돌린다.
팀 공통 get_db도 정상 종료 시 commit, 실패 시 rollback한다. 서비스에서 이미 확정한
변경을 의존성 종료의 rollback으로 취소할 수 없으므로 여러 도메인의 요청 전체 원자성과
HTTP 전송 전 commit 보장은 별도 통합 검증 대상이다.
부모 공연 잠금은 이 기능의 회차 변경을 조율하지만, 다른 도메인이 같은 잠금 규약을
사용하는지 및 실제 PostgreSQL 동시성은 별도 검증 대상이다.

## 공통 인증 연결

팀 공통 인증 모듈이 검증한 사용자 ID·역할을 사용해야 한다.
앱을 조립할 때 `create_app(authenticator=팀인증어댑터)`로 연결한다.
어댑터의 비동기 `authenticate(token)`은 검증에 성공하면
`CatalogActor(user_id, role)`, 실패하면 `None`을 반환한다.

토큰 없음/검증 실패는 `401 + WWW-Authenticate: Bearer`다.
공통 인증 미연결 상태에서 Bearer 토큰을 보내면 503으로 중단한다.
테스트용 토큰·임의 사용자 헤더를 운영 인증으로 제공하지 않는다.

인증 담당 구현과 연결할 때는 검증된 토큰의 사용자 조회 결과를
`CatalogActor`로 변환한다. 서명·만료·jti 차단·사용자 존재/탈퇴 상태 확인은
공통 인증 경로에서 수행하고, 공연·회차 서비스는 역할과 공연 소유권을 검사한다.
이 연결이 완료되기 전에는 JWT 인증이나 로그아웃 차단 완료로 표시하지 않는다.
식별자는 기존 BIGINT ID를 사용하고 SELLER/ADMIN 관리 정책을 유지한다.

## 의존성 주입 구조

- `wiring/shows.py`: 공연의 서비스 주입 계약·저장소·연결 조회·UoW·정책 조립과 등록.
- `wiring/performances.py`: 회차의 서비스 주입 계약·저장소·부모 공연 서비스 조립과 등록.
- `wiring/common.py`: 공연·회차가 공유하는 `DatabaseSession`과 `get_catalog_policy` 정의.
- `performances/application/ports.py`: 회차가 요구하는 `ShowAccess` 계약. 공연 조회·소유권 확인만 포함.
- `wiring/__init__.py`: 공연·회차 바인딩을 다른 도메인의 바인딩과 함께 등록.
- `main.create_app()`: 공용 wiring과 공통 예외 처리기를 등록하고 기존 라우터·인증 설정·lifespan 유지.
- 루트 및 공연·회차 표현 계층의 별도 의존성 파일과 통합 `wiring/catalog.py`는 제거했다.

공연·회차 라우터는 자신의 도메인 wiring의 provider를 `Depends`에 사용한다.
인프라 저장소를 직접 import하거나 라우터에서 객체를 조립하지 않는다.
FastAPI의 요청 단위 DB dependency 캐시를 사용하므로 부모 공연 권한 확인과 회차 변경은
같은 세션으로 실행된다. 공용 wiring 호출이 좌석 라우터의 자동 등록을 의미하지는 않는다.
회차 응용 서비스와 wiring은 공연 응용 서비스의 구체 타입 대신 `ShowAccess`를 요구하고,
실제 객체는 기존 공연 서비스를 주입한다. 소유권 확인의 공연 `FOR UPDATE` 잠금은
회차 INSERT/UPDATE/DELETE와 같은 세션에서 실행되고, 회차의 commit/rollback까지 유지한다.
SQLite 검증에서는 실제 SQL의 PostgreSQL 컴파일 결과와 세션·실행 순서를 확인하며,
실제 PostgreSQL에서의 동시 요청 잠금 대기 검증과는 구분한다.

## 실행·검증

프로젝트 폴더에서 다음 명령을 실행한다.

```powershell
uv sync --frozen
uv run --frozen python -B -m unittest discover -s tests -v
uv run --frozen python -B -m unittest discover -s tests/shared_core -v
uv run --frozen python -B -m unittest discover -s tests/database_session -v
uv run --frozen python -B -m unittest discover -s tests/seat_queries -v
uv run --frozen uvicorn asyncticket.main:app --host 127.0.0.1 --port 8000
```

별도 `shared_core`·`seat_queries` 테스트는 `httpx`가 설치된 테스트 환경이 필요하다.
루트 discover는 이 하위 폴더를 자동 수집하지 않으므로 각각 실행한다.

공연·공연회차의 작업은 10개이며, 공용 `/docs`에는 다른 도메인의 작업도 함께 표시될 수 있다.
OpenAPI 테스트는 추가 도메인의 라우트가 있는 상태에서도 공연·회차의 경로·메서드 10개와
해당 응답 계약을 정확히 검사한다. 실제 데이터 요청에는 PostgreSQL의 명세 테이블과
공통 인증 연결이 필요하다. DB 설정은 기존 `shared/core/database.py`의 환경 변수 규칙을 따른다.
현재 공용 lifespan은 서버 기동 시 init_models와 create_all을 실행한다.
이번 응답 전환은 그 절차를 변경하지 않는다. DB 작업 없는 문서/입력 검사를 할 때는
`--lifespan off`를 명시한다. 앱 생성만으로 lifespan이 실행되지는 않는다.

테스트는 격리 SQLite에서 실제 저장소 SQL을 실행하고, ASGI 요청으로 10개 API의
정상·권한·검증·충돌·삭제·롤백·Location·응답 필드를 확인한다.
공통 6필드·UTC 응답시각·모든 성공 DTO의 data 위치·422 필드 오류·401 헤더·
실제 앱의 공통 예외 연결·미처리 500 메시지 마스킹과 rollback·OpenAPI를 검사한다.
SQLite 테스트 어댑터의 시간대·PK 처리는 PostgreSQL과의 차이를 시험 환경에서만 보정한다.
PostgreSQL DDL 컴파일 검사는 실제 DB 적용·동시성·부하 검증이 아니다.

## 팀 통합 시 남은 사항

- 공통 JWT 인증 연결은 `wiring/catalog_auth.py`에 적용돼 있다. 기존 DB의 PK·NULL 제약은
  [기존 스키마 정합성 안내](existing-schema-alignment.md)에 따라 별도로 확인한다.
- 팀 공용 앱의 좌석 라우터·wiring 연결과 좌석 생성 완료 확인은 별도 통합 작업이다.
- 공연장 관계 수정과 공통 응답·예외 적용은 PR #33·#34로 팀 dev에 반영됐다.
  기존 잘못된 관계 제거와 함께 적용한 소스에서 9모델 ORM 초기화·PostgreSQL DDL 컴파일을
  통과했다. 실제 PostgreSQL 초기화와 기존 reserv_id nullable 변경은 별도로 확인한다.
- 전체 메타데이터 DDL 통합 검증이 필요하다. 연결 조회용 Core 컬럼
  선언은 실제 테이블 조회 계약이며 대체 ORM 모델 또는 테이블 생성 코드가 아니다.
- 이번 응답 전환은 의존성/lockfile·테이블 모델·DB 데이터를 변경하지 않는다.


### 공통 JWT 인증 연결

기본 앱은 `wiring/catalog_auth.py`에서 공연·회차 인증을 공통
`AuthApplicationService.authenticate()`에 연결한다. `/v1/auth/login`에서
받은 access token을 `Authorization: Bearer <token>`으로 전달한다.
서명·만료·블랙리스트·탈퇴 여부를 검증하고 DB의 현재 사용자 ID와 역할로
공연·회차 소유권 정책을 적용한다. `JWT_SECRET_KEY`는 환경 변수로 설정한다.
토큰 없는 요청은 401, JWT 설정 누락은 503이며 공개 조회와 앱 생성에는
JWT 설정이 필요하지 않다. `create_app(authenticator=...)`로 명시한
인증기는 계속 우선 적용한다.
