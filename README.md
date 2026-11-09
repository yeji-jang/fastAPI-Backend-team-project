# AsyncTicket

공연장·공연·회차·좌석을 관리하고, 회원이 좌석을 선택해 예매하는 티켓 예매 백엔드 팀 프로젝트입니다.

> README 초안입니다. 개발 기간, 테스트 결과 등은 팀에서 확인한 내용으로 보완합니다.

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

| 기능   | 구현 내용                                                              |
| ------ | ---------------------------------------------------------------------- |
| 회원   | 회원가입, 내 정보 조회, 비밀번호 변경, 탈퇴                            |
| 인증   | 로그인, JWT 인증, 로그아웃                                             |
| 공연장 | 이름·주소 검색, 목록·상세 조회, 등록·수정                              |
| 공연   | 검색·페이징, 상세 조회, 등록·수정·삭제                                 |
| 회차   | 공연별 회차 조회, 등록·수정·삭제                                       |
| 좌석   | 등급·개별 좌석 구성, 조회, 등급별 가격 변경, 예매 연결·해제            |
| 예매   | 예매대기 생성, 본인 예매 목록·상세 조회, 확정 예매 취소                |
| 결제   | 결제 상태 처리 서비스 구현. 외부 결제 연동과 공개 API 범위는 추후 정리 |

회원 역할은 `BUYER`, `SELLER`, `ADMIN`으로 구분합니다. 기능별 권한과 세부 제약은 API 문서와 도메인 문서를 참고합니다.

## 프로젝트 구조

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

구체적인 코드 흐름은 [4계층 가이드](AsyncTicket/docs/four-layer-guide.md)를 참고합니다.

## 로컬 실행

### 1. 저장소 및 의존성 준비

Python 3.13 이상, uv, 접속 가능한 PostgreSQL이 필요합니다.

```console
git clone https://github.com/yeji-jang/fastAPI-Backend-team-project.git
cd fastAPI-Backend-team-project/AsyncTicket
uv sync
```

### 2. 환경변수 설정

`AsyncTicket/.env.example`을 같은 폴더의 `.env.local`로 복사하고 본인의 개발 환경에 맞게 설정합니다. 이미 환경 파일이 있으면 해당 파일을 사용합니다.

```dotenv
DATABASE_URL=postgresql+asyncpg://USER:PASSWORD@localhost:5432/DATABASE
JWT_SECRET_KEY=replace-with-your-own-long-random-secret
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30
```

실제 비밀번호와 JWT 서명키가 들어 있는 환경 파일은 Git에 올리지 않습니다.

### 3. 서버 실행

아래 명령은 `AsyncTicket` 폴더에서 실행합니다.

```console
uv run uvicorn asyncticket.main:app --reload --env-file .env.local
```

| 문서       | 로컬 주소                                                  |
| ---------- | ---------------------------------------------------------- |
| Swagger UI | [http://localhost:8000/docs](http://localhost:8000/docs)   |
| ReDoc      | [http://localhost:8000/redoc](http://localhost:8000/redoc) |

서버 시작 시 모델을 등록하고 없는 테이블을 생성합니다. 기존 테이블의 컬럼·제약 변경은 별도로 확인해야 합니다. [기존 DB 정합성 가이드](AsyncTicket/docs/existing-schema-alignment.md)

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

> 추후 작성 — 테스트 실행 방법, 개발 의존성, 실행 결과와 검증 환경을 정리합니다.

좌석 기능의 현재 검증 시나리오는 [좌석 테스트 시나리오](AsyncTicket/docs/SEATS_TEST_SCENARIOS_KO.md)에서 확인할 수 있습니다.

## 설계 결정과 트러블슈팅

> 추후 작성 — 문제 상황, 선택한 방법, 선택 이유, 검증 결과를 기록합니다.

## 관련 문서

- [공통 API 가이드](AsyncTicket/docs/COMMON_API_GUIDE_KO.md)
- [4계층 가이드](AsyncTicket/docs/four-layer-guide.md)
- [공연·회차 설계 및 API](AsyncTicket/docs/shows-performances.md)
- [좌석 API 및 처리 흐름](AsyncTicket/docs/SEATS_COMMON_API_KO.md)
- [좌석 테스트 시나리오](AsyncTicket/docs/SEATS_TEST_SCENARIOS_KO.md)
- [기존 DB 정합성 확인](AsyncTicket/docs/existing-schema-alignment.md)
