# Jinja2 화면 실행

팀 API 진입점 `asyncticket.main:app`에서 화면과 API를 함께 제공한다. Docker와 systemd 실행 진입점은 변경하지 않는다.

```sh
uv sync --frozen
uv run uvicorn asyncticket.main:app --host 127.0.0.1 --port 8005
```

- 홈: http://127.0.0.1:8005/
- 회원가입·로그인: `/signup`, `/login`
- 공연·공연장: `/shows`, `/venues`
- 회차·좌석: `/performances/{perf_id}`
- 내 예매: `/me/reservations`
- 결제 이어하기: `/checkout/{reserv_id}`
- API 문서: `/docs`

기존 `.env`의 DB와 팀 앱의 시작 절차를 사용한다. 별도 목데이터나 계정은 자동으로 만들지 않는다. 이번 확인 환경은 개인 로컬 DB `127.0.0.1:5435/asyncticket_seat_local`이다. 운영·팀 DB로 실행하기 전에 접속 대상을 확인한다.

## 연결

브라우저 → 같은 서버의 `/v1` API → 기존 팀 서비스·도메인·저장소.

- 로그인 토큰은 기존 화면과 같이 sessionStorage에 보관하고 Bearer 헤더로 보낸다.
- 좌석 선택 → `POST /v1/reservations` → 결제 페이지 → `POST /v1/payments`.
- 금액과 orderId는 서버 응답을 사용한다. 브라우저 표시 가격으로 결제를 생성하지 않는다.
- 토스 인증 성공 → 결제 결과 화면에서 사용자가 승인 확인 → `POST /v1/payments/approve`.
- 실패 복귀는 승인 API를 호출하지 않는다. 내 예매에서 대기 예매의 결제를 이어갈 수 있다.
- 예매 기간·중복 예매·좌석 연결 조건·결제 승인·예매 확정은 기존 팀 API가 최종 판단한다.
- 실제 객석 좌표가 없으므로 배치도는 좌석 목록을 바탕으로 한 참고 배치다.

## 토스 설정

개인 환경에 개별 연동용 공개 클라이언트 키 `TOSS_CLIENT_KEY`를 설정한다. 결제 서버에는 PR #65의 `TOSS_SECRET_KEY`와 `TOSS_ORDER_PREFIX` 설정을 사용한다. 서로 같은 토스 프로젝트의 테스트 키를 사용해야 한다. 실제 키를 코드·Git에 넣지 않는다.

공개 설정 응답은 `TOSS_CLIENT_KEY`의 `test_ck_`/`live_ck_` 접두어만 허용한다. 시크릿 키는 화면에 전달하지 않는다. 키가 없으면 신규 예매를 만들기 전에 안내하고 중단한다.

토스 SDK는 결제 버튼을 누를 때 로드한다. 실제 결제 인증·승인 및 결제 후 예매 확정은 유효한 키와 테스트 결제 수단으로 별도 확인해야 한다. 이번 작업에서 실제 토스 결제는 실행하지 않았다.

참고: [토스 결제창 SDK](https://docs.tosspayments.com/sdk/v2/js/payment)
