# AsyncTicket

공연장·공연·회차·좌석을 관리하고, 회원이 좌석을 선택해 예매하는 티켓 예매 백엔드 팀 프로젝트입니다.

> Jinja2 웹 화면, Swagger UI, 정상 응답, 도메인 규칙 차단 및 JWT 블랙리스트 차단 캡처는 실행 결과 절에서 확인할 수 있습니다.

## 프로젝트 소개

- 회원 인증과 역할에 따른 공연 관리
- 공연별 회차와 좌석 등급·개별 좌석 관리
- 좌석 선점과 예매 생성·조회·취소
- 공통 API 응답과 예외 처리

| 항목          | 내용                                            |
| ------------- | ----------------------------------------------- |
| 개발 기간     | 26.10.26 ~ 26.11.11                             |
| 프로젝트 목표 | 공연·원데이 클래스 티켓 예약 시스템 백엔드 구현 |
| 배포 주소     | https://asyncticket.teamsparta.xyz/             |

## Use Case

프로젝트 주제는 **공연·원데이 클래스 티켓 예약 시스템**입니다. 대표 Use Case는 **공연 탐색 → 회차·좌석 선택 → 예매대기 생성 → 결제 → 본인 예매 확인**입니다.

| 사용자        | Use Case                 | 주요 처리                                          |
| ------------- | ------------------------ | -------------------------------------------------- |
| 구매자(BUYER) | 회원가입·로그인·로그아웃 | JWT 발급·인증, 로그아웃 토큰 블랙리스트 등록       |
| 구매자(BUYER) | 좌석 예매                | 공연·회차·좌석 조회, 예매대기 생성, 본인 예매 조회 |
| 구매자(BUYER) | 결제 및 예매 취소        | 결제 시작·승인·상태 조회, 확정 예매 취소           |
| 판매자·관리자 | 공연 운영                | 기능별 권한 정책에 따른 공연·회차·좌석 관리        |

## 기술 스택

| 구분               | 기술             |
| ------------------ | ---------------- |
| 언어               | Python 3.13 이상 |
| 웹 프레임워크      | FastAPI          |
| 데이터 검증        | Pydantic         |
| ORM                | SQLAlchemy       |
| 데이터베이스       | PostgreSQL       |
| 비동기 DB 드라이버 | asyncpg          |
| 인증               | JWT, bcrypt      |
| 패키지 관리        | uv               |
| ASGI 서버          | Uvicorn          |

상세 의존성은 [pyproject.toml](AsyncTicket/pyproject.toml)과 [uv.lock](AsyncTicket/uv.lock)에서 확인할 수 있습니다.

## 주요 기능

| 기능   | 구현 내용                                                    |
| ------ | ------------------------------------------------------------ |
| 회원   | 회원가입, 내 정보 조회, 비밀번호 변경, 탈퇴                  |
| 인증   | 로그인, JWT 인증, 로그아웃                                   |
| 공연장 | 이름·주소 검색, 목록·상세 조회, 등록·수정                    |
| 공연   | 검색·페이징, 상세 조회, 등록·수정·삭제                       |
| 회차   | 공연별 회차 조회, 등록·수정·삭제                             |
| 좌석   | 등급·개별 좌석 구성, 조회, 등급별 가격 변경, 예매 연결·해제  |
| 예매   | 예매대기 생성, 본인 예매 목록·상세 조회, 확정 예매 취소      |
| 결제   | 결제 시작·승인·예매 기준 조회 API, 토스 결제 게이트웨이 연동 |

회원 역할은 `BUYER`, `SELLER`, `ADMIN`으로 구분합니다. 기능별 권한과 세부 제약은 API 문서와 도메인 문서를 참고합니다.

## 프로젝트 구조

### 전체 도메인 구조도

도메인 간 호출 관계와 인증, 의존성 조립, PostgreSQL 및 외부 결제 연동을 나타낸 구조도입니다.

![AsyncTicket 전체 도메인 구조도](AsyncTicket/docs/images/asyncticket.png)

[구조도 원본 크게 보기](AsyncTicket/docs/images/asyncticket.png)

### 디렉토리와 4계층 구성

```text
AsyncTicket/
├── src/asyncticket/
│   ├── main.py             # 앱 생성, 라우터 등록, 시작·종료 처리
│   ├── auth/               # 인증
│   ├── users/              # 회원
│   ├── venues/             # 공연장
│   ├── shows/              # 공연
│   ├── performances/       # 공연 회차
│   ├── seats/              # 좌석 등급·개별 좌석
│   ├── reservations/       # 예매
│   ├── payment/            # 결제
│   ├── web.py              # Jinja2 화면 라우터
│   ├── templates/          # Jinja2 HTML 템플릿
│   ├── static/             # CSS, JavaScript, 이미지
│   ├── shared/             # 공통 응답, 예외, DB 설정 등
│   └── wiring/             # 서비스·저장소 의존성 연결
├── tests/
├── docs/
├── scripts/
├── .env.example
├── pyproject.toml
└── uv.lock
```

각 기능은 다음 4계층을 기준으로 구성합니다.

| 계층           | 역할                                     |
| -------------- | ---------------------------------------- |
| Presentation   | HTTP 요청·응답과 입력 형식 처리          |
| Application    | 기능 실행 순서와 도메인·저장소 호출 조율 |
| Domain         | 업무 개념과 규칙, 저장소 인터페이스      |
| Infrastructure | DB 모델과 저장소 구현                    |

공연장 도메인의 실제 디렉토리와 컴포넌트 구조입니다. 다른 도메인도 같은 4계층 기준을 따르되 파일명과 세부 구성은 다를 수 있습니다.

```text
src/asyncticket/venues/
├── presentation/                     # HTTP 입출력
│   ├── routers/v1/router.py          # 공연장 조회·등록·수정 API
│   ├── schemas.py                    # 요청·응답 DTO
│   └── dependencies.py               # FastAPI 의존성 연결
├── application/                      # Use Case 실행 조율
│   └── service.py                    # VenueService
├── domain/                           # 업무 규칙 및 저장소 계약
│   ├── venue.py                      # Venue: 이름·우편번호 검증
│   └── repository.py                 # 저장소 인터페이스
└── infrastructure/                   # DB 기술 구현
    ├── models.py                     # SQLAlchemy 모델
    └── repositories.py               # 저장소 인터페이스 구현
```

```text
HTTP 요청
└── Presentation: Router + 요청 DTO
    └── Application: VenueService
        ├── Domain: Venue의 업무 규칙 검증
        └── Domain: 저장소 인터페이스 호출
            └── Infrastructure: 저장소 구현 → SQLAlchemy → PostgreSQL

wiring/venues.py → 서비스와 저장소 구현 조립
HTTP 응답 ← Presentation: 응답 DTO + 공통 응답 / 예외 처리기
```

Application은 Domain의 저장소 계약을 사용하고 Infrastructure가 이를 구현합니다. 실제 구현체는 `wiring`에서 연결합니다.

구체적인 코드 흐름은 [4계층 가이드](AsyncTicket/docs/four-layer-guide.md)를 참고합니다.

## 로컬 실행

### 1. 저장소 및 의존성 준비

Python 3.13 이상, uv, 접속 가능한 PostgreSQL이 필요합니다.

```console
git clone https://github.com/yeji-jang/fastAPI-Backend-team-project.git
cd fastAPI-Backend-team-project/AsyncTicket
uv sync
```

### 2. PostgreSQL 실행

이미 실행 중인 PostgreSQL이 있다면 해당 인스턴스와 개발용 DB를 사용합니다. 새 인스턴스가 필요하면 Docker를 실행한 뒤 다음 명령을 사용합니다. 아래 계정은 로컬 개발용 예시입니다.

```console
docker run --name asyncticket-postgres -e POSTGRES_USER=asyncticket -e POSTGRES_PASSWORD=local-dev-password -e POSTGRES_DB=asyncticket -p 127.0.0.1:5432:5432 -d postgres:17
docker exec asyncticket-postgres pg_isready -U asyncticket -d asyncticket
```

`accepting connections`를 확인한 뒤 서버를 실행합니다. 만든 컨테이너를 정지한 후 재실행할 때는 `docker start asyncticket-postgres`를 사용합니다. 5432 포트를 사용 중이면 기존 DB를 사용하거나 포트 매핑과 아래 접속 주소를 함께 변경합니다.

### 3. 환경변수 설정

`AsyncTicket` 폴더에서 `.env.example`을 `.env`로 복사하고 본인의 개발 환경에 맞게 설정합니다. 기존 파일이 있으면 덮어쓰지 않고 필요한 값만 수정합니다.

```powershell
Copy-Item .env.example .env
```

```dotenv
DATABASE_URL=postgresql+asyncpg://asyncticket:local-dev-password@localhost:5432/asyncticket
JWT_SECRET_KEY=replace-with-your-own-long-random-secret
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30
```

기본 실행은 `.env`를 읽습니다. 기존 `.env.local`을 사용하려면 실행 명령 끝에 `--env-file .env.local`을 추가합니다. 실제 비밀번호와 JWT 서명키가 들어 있는 환경 파일은 Git에 올리지 않습니다.

토스 결제까지 시연하려면 별도로 발급한 테스트 키도 설정합니다. `TOSS_SECRET_KEY`는 서버 전용 키, `TOSS_CLIENT_KEY`는 결제 화면용 키이며, `TOSS_ORDER_PREFIX`로 주문번호 접두어를 구분할 수 있습니다.

### 4. 서버 실행

아래 명령은 `AsyncTicket` 폴더에서 실행합니다.

```console
uv run uvicorn asyncticket.main:app --app-dir src --reload
```

| 화면·문서  | 로컬 주소                                                  |
| ---------- | ---------------------------------------------------------- |
| Jinja2 홈  | [http://localhost:8000/](http://localhost:8000/)           |
| 공연 목록  | [http://localhost:8000/shows](http://localhost:8000/shows) |
| 로그인     | [http://localhost:8000/login](http://localhost:8000/login) |
| Swagger UI | [http://localhost:8000/docs](http://localhost:8000/docs)   |
| ReDoc      | [http://localhost:8000/redoc](http://localhost:8000/redoc) |

서버 시작 시 모델을 등록하고 없는 테이블을 생성합니다. 회원·공연 등 시연 데이터는 자동 생성되지 않으므로 화면 또는 API로 준비합니다. 기존 테이블의 컬럼·제약 변경은 별도로 확인해야 합니다. [기존 DB 정합성 가이드](AsyncTicket/docs/existing-schema-alignment.md)

## 실행 결과 캡처

### Jinja2 웹 화면

Jinja2 템플릿으로 렌더링한 공연 상세 화면입니다. 공연 정보와 회차 선택 UI를 제공합니다.

![Jinja2 공연 상세 화면](AsyncTicket/docs/images/jinja2-web.png)

### Swagger UI 문서

`/docs`에서 도메인별 API 명세와 요청·응답 스키마를 확인하고 요청을 실행할 수 있습니다.

![Swagger UI API 문서](AsyncTicket/docs/images/swagger-ui.png)

### 정상 처리 — 200 OK

공연장 목록 조회 요청을 정상 처리한 화면입니다. 개발자 도구의 Network에서 HTTP **200 OK**를 확인할 수 있습니다.

![공연장 목록 조회 200 OK](AsyncTicket/docs/images/api-200-ok.png)

### 도메인 규칙 차단 — 400 Bad Request

숫자 5자리 규칙에 맞지 않는 우편번호로 공연장 등록을 요청한 결과입니다. 도메인 검증에서 `VALIDATION_ERROR`와 “우편번호는 숫자 5자리여야 합니다.” 메시지를 반환합니다. 필드 누락 등 요청 형식 오류의 HTTP 422와 구분합니다.

![공연장 우편번호 도메인 규칙 차단](AsyncTicket/docs/images/domain-rule-400.png)

### JWT 블랙리스트 차단 — 401 Unauthorized

로그인 시 발급받은 토큰으로 내 정보 조회에 성공한 뒤 로그아웃하고, 같은 토큰으로 `GET /v1/users/me`를 다시 요청한 결과입니다. HTTP **401 Unauthorized**와 **`REVOKED_ACCESS_TOKEN`**을 반환합니다.

![JWT 블랙리스트 토큰 재사용 차단 401](AsyncTicket/docs/images/jwt-blacklist-401.png)

> 재현 환경: 이 캡처는 기존 DB의 필수 컬럼인 `blacklist.user_id`도 저장하도록 임시 수정한 상태에서 촬영했습니다. 해당 임시 코드는 촬영 후 원복했습니다. 현재 코드로 같은 DB에서 재현하려면 코드와 DB 스키마 정합성을 먼저 맞춰야 합니다. [기존 DB 정합성 가이드](AsyncTicket/docs/existing-schema-alignment.md)

재현 순서: `/v1/auth/login` → `data.access_token`을 Swagger의 Authorize에 입력 → `/v1/users/me` 조회 → `/v1/auth/logout` → 토큰을 교체하지 않고 `/v1/users/me` 재조회.

## API와 공통 응답

API는 `/v1` 경로를 사용합니다. 인증이 필요한 요청은 다음 헤더를 전달합니다.

```http
Authorization: Bearer <access_token>
```

공통 응답 예시입니다.

```json
{
  "success": true,
  "code": "OK",
  "message": "요청이 성공적으로 처리되었습니다.",
  "errors": null,
  "data": {},
  "responded_at": "2026-11-09T00:00:00Z"
}
```

일부 삭제 API는 본문 없이 `204 No Content`를 반환합니다. 엔드포인트별 요청·응답은 실행 중인 Swagger UI에서 확인합니다.

## ERD

![AsyncTicket ERD](AsyncTicket/docs/images/asyncticket-erd-20261029.png)

[ERD 원본 크게 보기](AsyncTicket/docs/images/asyncticket-erd-20261029.png)

## 팀원과 담당 역할

| 이름   | 역할 | 담당 기능                                     |
| ------ | ---- | --------------------------------------------- |
| 이정은 | 팀장 | 회차별 좌석, 예약 좌석, 서버 배포, 프론트엔드 |
| 최기혁 | 서기 | 결제 기능                                     |
| 장예지 | 팀원 | 예매 기능                                     |
| 김지현 | 팀원 | 공연, 회차 기능                               |
| 정학용 | 팀원 | 회원, 인증 기능                               |
| 정현구 | 팀원 | 공연장 기능                                   |

## 테스트

Python 표준 `unittest`를 사용하며, 비동기 로직은 `IsolatedAsyncioTestCase`로 검증합니다. 아래 내용은 저장소의 테스트 코드에 정의된 검증 범위이며, 전체 테스트 통과 결과를 의미하지 않습니다.

### 검증 범위

| 구분              | 테스트 위치                                                                                               | 주요 검증 내용                                                                                                                            |
| ----------------- | --------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| 회원              | `tests/users/`                                                                                            | 회원 생성, 이메일 정규화, 이름·전화번호·비밀번호 검증, 비밀번호 변경, 본인·관리자 탈퇴 권한                                               |
| 인증              | `tests/auth/`                                                                                             | 로그인 성공·실패, 로그아웃 토큰 블랙리스트 등록, 폐기·만료 토큰 인증 거절, 동일 토큰 로그아웃 반복                                        |
| 공연·회차         | `tests/test_catalog.py`, `tests/test_performance_dependencies.py`                                         | 조회·검색·페이징, 등록·수정·삭제, JWT·역할·소유권 검사, 예매 기간·시간대 검증, 연관 좌석·예매가 있는 회차의 변경 제한                     |
| 좌석              | `tests/test_seat_*.py`, `tests/seat_queries/`                                                             | 좌석 등급·가격·수용량 규칙, 판매 시작 전 관리 제한, 회차별 조회, 좌석 배정·해제 충돌, 이전 예매가 재배정된 좌석을 해제하지 못하는지 검증  |
| 예매              | `tests/reservations/`                                                                                     | 예매대기 생성, 예매 가능 기간, 진행 중 예매 중복 제한, 본인 조회·취소 권한, 결제 후 확정, 취소 시 좌석 해제, 저장소 조회 및 확정시각 보존 |
| 공통 API·앱       | `tests/shared_core/`, `tests/database_session/`, `tests/test_app_initialization.py`, `tests/test_cors.py` | 공통 응답·예외·입력 검증, 내부 오류 메시지 마스킹, 세션 commit·rollback, 앱 수명주기·의존성 연결, CORS                                    |
| 웹 화면           | `tests/frontend/`                                                                                         | Jinja2 화면·정적 파일 렌더링과 화면 조립에 따른 API 계약·설정 노출 회귀 검사                                                              |
| PostgreSQL 정합성 | `tests/postgres/`                                                                                         | 기존 스키마 값 보존, 새 행 저장, 재실행, 중복 토큰·예상 밖 FK 거절, 실패 시 DDL rollback                                                  |

### 실행 방법

저장소를 받은 뒤 `AsyncTicket` 폴더에서 `uv sync`를 먼저 실행합니다. 테스트 러너는 표준 라이브러리이므로 pytest 설치는 필요하지 않습니다. HTTP 테스트에 사용하는 `httpx`는 프로젝트 의존성에 포함되어 있으며, 비동기 SQLite 테스트에는 `--with aiosqlite`로 드라이버를 추가합니다.

```console
cd AsyncTicket
uv sync
```

기본 테스트는 가짜 저장소·Mock 또는 SQLite 메모리 DB를 사용합니다. 앱 설정 로딩에 사용하는 `DATABASE_URL`은 앞의 로컬 환경변수 설정을 따릅니다. 기본 테스트 실행을 위해 Uvicorn 서버를 별도로 띄울 필요는 없습니다.

테스트 하위 폴더마다 별도로 탐색합니다. `tests` 한 곳만 탐색하는 명령으로는 패키지 구성이 없는 하위 폴더가 누락될 수 있습니다.

```console
uv run --with aiosqlite python -B -m unittest discover -s tests -p "test_*.py" -v
uv run python -B -m unittest discover -s tests/users -v
uv run python -B -m unittest discover -s tests/auth -v
uv run python -B -m unittest discover -s tests/reservations -v
uv run --with aiosqlite python -B -m unittest discover -s tests/seat_queries -v
uv run python -B -m unittest discover -s tests/shared_core -v
uv run python -B -m unittest discover -s tests/database_session -v
uv run python -B -m unittest discover -s tests/frontend -v
```

특정 파일만 확인하려면 `-p`로 파일명을 지정합니다.

```console
uv run python -B -m unittest discover -s tests/reservations -p test_reservation_domain.py -v
```

### PostgreSQL 통합 테스트

별도로 생성한 로컬 테스트 DB에 대해 `ASYNCTICKET_TEST_DATABASE_URL`을 지정합니다. 접속 호스트는 `localhost`, `127.0.0.1`, `::1` 중 하나이며 DB 이름에 `test` 또는 `local`이 포함되어야 합니다. 환경변수를 지정하지 않으면 해당 테스트는 건너뜁니다.

```powershell
$env:ASYNCTICKET_TEST_DATABASE_URL = "postgresql+asyncpg://USER:PASSWORD@localhost:5432/asyncticket_test"
uv run python -B -m unittest discover -s tests/postgres -v
```

각 테스트는 임시 스키마와 데이터를 만들고 종료 시 rollback합니다. 실행 계정에는 테스트 DB 내 스키마 생성 권한이 필요합니다. 자세한 내용은 [기존 DB 정합성 가이드](AsyncTicket/docs/existing-schema-alignment.md)를 참고합니다.

### k6 좌석 예매 동시성 테스트 결과

2026-11-10 로컬 서버(`http://localhost:8000`)에서 서로 다른 테스트 회원 2명이 **같은 회차·같은 좌석**을 예매하도록 실행했습니다. 아래는 해당 실행 로그를 기준으로 정리한 결과입니다.

| 항목             | 설정·결과                                                                             |
| ---------------- | ------------------------------------------------------------------------------------- |
| 스크립트         | [reservation-concurrency.js](AsyncTicket/scripts/k6/reservation-concurrency.js)       |
| 테스트 케이스    | `same-seat`                                                                           |
| 대상 API         | `POST /v1/reservations`                                                               |
| 대상 데이터      | `perf_id=2`, `perf_seat_id=6`                                                         |
| 경쟁 요청        | 서로 다른 회원 토큰으로 예매 요청 2건 병렬 전송, 1회 실행                             |
| 요청 1           | HTTP **201**, `RESERVATION_CREATED`, `reserv_id=1`                                    |
| 요청 2           | HTTP **409**, `SEAT_RESERVATION_CONFLICT`                                             |
| 실행 후 API 조회 | 참여 회원의 해당 회차 진행 중 예매 합계 **1건**, 성공 응답의 예매 ID·좌석 연결과 일치 |
| 검사 결과        | **7/7 통과**, `checks` 성공률 **100%**                                                |

주요 실행 로그:

```text
준비 완료: case=same-seat, perf_id=2, requests=2
요청 1: HTTP 201, code=RESERVATION_CREATED, reserv_id=1
요청 2: HTTP 409, code=SEAT_RESERVATION_CONFLICT, reserv_id=-

checks_succeeded: 100.00% (7 out of 7)
checks_failed:      0.00% (0 out of 7)
```

이 스크립트는 **1 VU에서 `http.batch()`로 회원별 인증 정보를 가진 요청 2건을 병렬 전송**합니다. 출력의 `1 VUs`는 회원 한 명의 순차 요청을 의미하지 않습니다. 전체 HTTP 요청 11건에는 로그인·사전 확인·결과 조회가 포함되며, 실제 경쟁 예매 요청은 2건입니다.

이번 실행에서는 한 요청만 성공하고 다른 요청은 좌석 충돌로 거절되는 것을 확인했습니다. 병렬 전송이 DB 내부의 특정 시점에서 정확히 겹쳤다는 증거는 아니며, 단일 실행 결과로 모든 경쟁 상황의 안전성이나 서버 부하 처리 능력을 보장하지 않습니다. **최종 DB 직접 검증과 반복 실행 결과는 이 기록에 포함하지 않았습니다.** 동일 데이터로 재실행하려면 생성된 예매·좌석 점유를 정리하거나 새로운 테스트 데이터를 준비해야 합니다.

좌석 기능의 상세 검증 시나리오는 [좌석 테스트 시나리오](AsyncTicket/docs/SEATS_TEST_SCENARIOS_KO.md)를 참고합니다.

### k6 PENDING 만료 후 좌석 재예매 테스트 결과

팀원이 공유한 로컬 실행 결과를 정리했습니다. 서로 다른 회원 2명이 같은 회차·좌석을 예매할 때 **만료 전에는 충돌로 거절되고, 첫 번째 PENDING 예매가 만료된 후에는 다른 회원이 좌석을 재예매할 수 있는지** 확인했습니다.

| 항목 | 설정·결과 |
| ---- | --------- |
| 스크립트 | [reservation-expire-reuse.js](AsyncTicket/scripts/k6/reservation-expire-reuse.js) |
| 실행 환경 | 로컬 `http://127.0.0.1:8000`, 테스트 회원 2명, 1회 실행 |
| 대상 데이터 | `PERF_ID=1`, `SEAT_ID=1` (`performance_seats.perf_seat_id`) |
| 요청 1 | 첫 번째 회원: HTTP **201**, `RESERVATION_CREATED`, **PENDING** 예매 생성 |
| 요청 2 | 만료 전 두 번째 회원: HTTP **409**, `SEAT_RESERVATION_CONFLICT` |
| 대기 | 약 **6분**: PENDING 만료 시간 **5분** + 백그라운드 확인 주기 **60초** 반영 |
| 요청 3 | 만료 후 두 번째 회원: HTTP **201**, `RESERVATION_CREATED`, 같은 좌석 재예매 성공 |
| 검사 결과 | **checks 5개 모두 통과**, HTTP 요청 실패율 **0%** |

`AsyncTicket` 폴더에서 실행합니다. 스크립트의 테스트 계정 2개를 먼저 가입시키거나 계정 설정을 준비하고, 예매 기간 내 회차와 가격이 양수인 `AVAILABLE` 좌석을 사용합니다. 두 회원 모두 해당 회차의 진행 중 예매가 없어야 합니다.

```powershell
$env:PERF_ID = '1'
$env:SEAT_ID = '1'
k6 run scripts/k6/reservation-expire-reuse.js
```

현재 스크립트는 로컬 서버 주소와 계정을 파일에 설정하며, 위 동시성 스크립트의 `BASE_URL`·`ACCOUNTS_JSON` 환경변수 설정을 사용하지 않습니다. 자세한 준비·실행 방법은 파일 상단을 참고합니다.

이 테스트는 **좌석 충돌 응답과 PENDING 만료 후 좌석 재사용**을 확인하는 시나리오입니다. 두 번째 회원은 시작 5초 후 요청하고 약 6분 대기 후 재요청하므로, 여러 VU의 정확한 동시 처리 성능이나 서버 한계 부하를 검증한 결과는 아닙니다. 전체 HTTP 요청 5건은 로그인 2건과 예매 3건이며, 예상한 HTTP 409는 실패율 계산에서 허용하되 별도 check로 오류 코드를 확인합니다.

공유된 결과는 API 응답 기준이며 최종 DB 직접 검증 결과는 포함하지 않았습니다. 실행 후 두 번째 회원의 PENDING 예매가 남을 수 있으므로, 같은 데이터로 재실행하려면 만료·좌석 해제를 기다리거나 테스트 데이터를 정리해야 합니다.

## 설계 결정과 트러블슈팅

### 주요 설계 결정

회의록의 결정과 현재 체크아웃된 코드에서 확인한 구현을 함께 정리했습니다. 회의록의 제안·미확정 항목을 구현 완료로 간주하지 않습니다.

| 문제·고려 사항                                                   | 선택한 설계와 이유                                                                                                         | 현재 코드에서 확인한 적용                                                                                                |
| ---------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| 도메인 규칙에 DB·프레임워크 코드가 섞이면 변경과 테스트가 어려움 | 자체 값으로 판단하는 규칙은 엔티티·VO에 두고, 외부 조회는 추상 계약과 인프라 구현으로 분리. 응용 서비스는 실행 순서를 조율 | `Reservation.create_pending()`이 예매 기간·진행 중 예매를 검증하고, `ReservationService`가 조회·저장·좌석 연결을 조율    |
| 예매에서 회원·좌석 구현을 직접 참조하면 도메인 간 결합이 커짐    | 필요한 정보는 해당 맥락의 VO로 받고, 다른 도메인 호출은 포트·어댑터를 통해 연결                                            | `TicketHolder`, `ReservedPerformance`, `ReservedSeat`와 `SeatAllocation` 계약, `SeatAllocationAdapter` 사용              |
| 모든 의존성을 하나의 컨테이너에 모으면 구성이 커짐               | 도메인별 `wiring`으로 서비스·저장소·어댑터를 조립                                                                          | `wiring/reservations.py` 등에서 실제 구현을 생성하고 FastAPI 의존성에 연결                                               |
| 도메인마다 응답 구조가 다르면 화면에서 성공·실패 처리가 복잡해짐 | 응답의 공통 형식은 통일하고 데이터·업무 메시지는 도메인별로 유지. 공통 HTTP 예외와 도메인 특화 예외를 구분                 | `APIResponse`, 공통 예외 처리기 및 예매 도메인 예외 매핑 사용                                                            |
| 좌석 연결 실패 시 예매만 남을 위험                               | 예매 저장과 좌석 배정을 같은 요청 세션·트랜잭션으로 조립하고 실패 시 rollback                                              | `create_reservation_service()`가 같은 세션을 전달하고 `get_db()`가 commit·rollback 담당. 실제 DB 정합성은 별도 검증 필요 |

## 관련 문서

- [공통 API 가이드](AsyncTicket/docs/COMMON_API_GUIDE_KO.md)
- [4계층 가이드](AsyncTicket/docs/four-layer-guide.md)
- [공연·회차 설계 및 API](AsyncTicket/docs/shows-performances.md)
- [좌석 API 및 처리 흐름](AsyncTicket/docs/SEATS_COMMON_API_KO.md)
- [좌석 테스트 시나리오](AsyncTicket/docs/SEATS_TEST_SCENARIOS_KO.md)
- [기존 DB 정합성 확인](AsyncTicket/docs/existing-schema-alignment.md)
