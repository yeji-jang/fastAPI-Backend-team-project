# 프론트 화면 ↔ 백엔드 정보 매칭

PR #75의 연결과 기존 화면을 함께 설명한다. 아래 API는 기존 팀 API이며, 이번 프론트 작업에서 새 업무 API나 SQL 조회를 만들지 않았다.
일반 API 응답은 `APIResponse.data`를 읽는다. `/web/config`만 `toss_client_key`를 바로 반환한다.
로그인이 필요한 요청에는 기존 `accountSession.headers()`의 토큰을 전달한다. 예매자 ID는 프론트에서 지정하지 않고 백엔드가 토큰으로 확인한다.

## 1. 화면에서 읽어 표시하는 정보

| 화면 | 호출하는 기존 API | 받은 값 → 화면 |
|---|---|---|
| 계정 메뉴·내 정보 `/me` | GET `/v1/users/me` | `user_id`, `name`, `email`, `phone_number` → 회원 정보. `role` → 구매자/관리 메뉴 표시 |
| 공연장 목록·상세 `/venues`, `/venues/{id}` | GET `/v1/venues/list`, GET `/v1/venues?venues_id={id}` | `venues_id`, `name`, `address`, `address_detail`, `post_no` → 공연장 이름·주소·상세 링크 |
| 공연 목록·상세 `/shows`, `/shows/{id}` | GET `/v1/shows`, GET `/v1/shows/{id}` | `show_id`, `title`, `performer`, `type`, `runtime`, `description`, `venues_id` → 공연 소개·출연진·장르·공연 시간·공연장 연결 |
| 회차 선택 | GET `/v1/shows/{show_id}/performances`, GET `/v1/performances/{id}` | `perf_id`, `round_number`, `starts_at`, `booking_opens_at`, `booking_closes_at` → 회차·공연 일시·예매 기간 안내 |
| 좌석표 | GET `/v1/performances/{perf_id}/seats` | `items[].perf_seat_id`, `grade`, `seat_seq`, `price`, `status` → 선택할 좌석 ID·등급·좌석명·현재 가격·선택 가능 표시 |
| 내 예매 `/me/reservations` | GET `/v1/reservations` | `reserv_id`, `order_number`, `perf_id`, `perf_seat_id`, `total_amount`, `status` → 예매번호·연결 정보·구매 당시 금액·예매 상태 |
| 내 예매의 공연 정보 | 회차 → 공연 → 공연장 상세 API | 예매의 `perf_id` → 회차의 `show_id` → 공연의 `venues_id`를 따라가 공연명·일시·공연장 표시 |
| 내 예매의 결제 정보 | GET `/v1/reservations/{reserv_id}/payment` | `status`, `amount`, `order_id`, `paid_at`, `refunded_at` → 결제 상태·결제 금액·토스 주문번호·승인/환불 일시. 404면 결제 내역 없음 |
| 예매 상세 펼치기 | GET `/v1/reservations/{reserv_id}` | `quantity`, `created_at`, `confirmed_at`, `canceled_at`, `status`, `order_number` → 수량·생성/확정/취소 일시·현재 예매 상태 |
| 예매 상세의 본인 좌석 | GET `/v1/reservations/{reserv_id}/seats` | `items[].grade`, `seat_seq` → 본인 예매에 연결된 좌석. 연결이 없으면 좌석 정보가 없다고 표시 |
| 결제 확인 `/checkout/{reserv_id}` | 예매 상세 + 회차 + 공연 + 공연장 + 좌석 목록 | 예매의 `total_amount` → 총 결제 금액. `perf_seat_id`와 좌석 목록을 매칭해 등급·좌석명 표시 |
| 결제 확인의 포스터 | 공연 상세 + 기존 정적 이미지 | `title`, `performer`, `type` → 포스터 문구. 이미지 자체는 정적 연출 이미지이며 API의 실제 포스터 필드가 아님 |

공연·회차 시각은 화면에서 한국 시간으로 포맷한다. 좌석의 현재 `price`를 예매 당시 `total_amount`로 대체하지 않는다.
`order_number`는 예매의 주문번호이고, 결제창에 전달하는 토스 주문번호는 결제 API의 `order_id`다. 서로 대신 사용하지 않는다.

## 2. 버튼을 눌렀을 때 보내는 요청

| 사용자 동작 | 기존 API와 요청 | 응답 이후 화면 동작 |
|---|---|---|
| 회원가입 | POST `/v1/users` | 성공·실패 안내 후 로그인으로 연결 |
| 로그인·로그아웃 | POST `/v1/auth/login`, POST `/v1/auth/logout` | 기존 토큰 저장·삭제와 메뉴 갱신 |
| 비밀번호 변경 | PATCH `/v1/users/me/password`, `{old_password, new_password}` | 서버 성공 응답을 확인하고 입력 초기화 |
| 회원 탈퇴 | DELETE `/v1/users/me` | 체크·최종 확인 후 요청. `USER_WITHDRAWN` 성공이면 토큰 삭제·로그인 이동. 결과 불명확 시 즉시 중복 요청하지 않음 |
| 좌석 예매 | POST `/v1/reservations`, `{perf_id, perf_seat_id}` | 같은 좌석의 기존 대기 예매를 먼저 확인. 생성/재사용한 `reserv_id`로 결제 확인 화면 이동 |
| 결제 이어하기 | API 변경 요청 없이 `/checkout/{reserv_id}` 이동 | 공연·좌석·금액을 먼저 확인 |
| 결제하기 | POST `/v1/payments`, `{reserv_id}` | 서버의 `order_id`, `amount`, `status=READY`를 확인한 뒤 토스 SDK에 전달. 서버 금액과 예매 금액을 비교 |
| 토스 성공 콜백 | GET 본인 결제 → READY일 때 POST `/v1/payments/approve`, `{payment_key, order_id, amount}` | 이미 DONE이면 재승인하지 않음. 승인 후 예매 상세를 다시 읽어 CONFIRMED 여부 확인. DONE 확인 후 콜백 키를 URL에서 제거 |
| 예매 취소·환불 | POST `/v1/reservations/{reserv_id}/cancel` | 사용자 최종 확인 후 호출. 예매 취소·좌석 해제·토스 환불·DB 저장은 기존 백엔드의 책임. 프론트는 목록과 결제 정보를 재조회 |
| 최신 상태 조회 | GET `/v1/reservations` 및 연결된 조회 API | 서버에서 새로 읽고 마지막 조회 시각 표시. 자동 만료 상태를 프론트에서 생성하지 않음 |

공연장·공연·회차·좌석 관리의 기존 등록/수정/삭제 폼은 기존 API를 그대로 사용한다. PR #75가 관리 업무 규칙을 새로 추가하지는 않는다.

## 3. 상태의 출처와 화면의 책임

- 예매 상태: 예매 API의 `PENDING / CONFIRMED / CANCELED / EXPIRED`를 표시한다.
- 결제 상태: 결제 API의 `READY / DONE / FAIL / REFUND`를 별도로 표시한다.
- 예매가 만료됐다고 결제 실패를 만들어내거나, 취소됐다고 환불 완료를 추측하지 않는다.
- 전체/대기/확정 건수는 본인 예매 목록 응답에서 프론트가 집계한다. 현재 검색·상태 필터도 받은 본인 목록을 대상으로 한다.
- 취소 버튼은 CONFIRMED 예매에 노출하되, 실제 본인 여부·현재 상태·공연 시작 전 여부·환불 가능 여부는 서버가 최종 판단한다.
- 결제 성공 표시는 토스 화면을 닫았다는 사실이 아니라 서버 응답으로 확인한다.
- 키·비밀번호·결제 로그 원문을 화면에 출력하거나 문서에 기록하지 않는다.

## 4. 관리자 화면의 현재 경계

`/manage/bookings`는 HTML/CSS와 GET 호출 어댑터만 준비한 화면이다.
현재 팀에 관리자 전체 예매·결제 조회 API가 없어서 `admin_booking_api.js`의 기본 주소는 null이다.
운영 화면은 실제 데이터 대신 API 미연결 안내를 표시한다. 구매자 본인 조회 API로 다른 회원 내역을 가져오지 않는다.
향후 관리자 API가 제공되면 주소와 응답 매핑만 연결한다. 별도 제안 형식은 `ADMIN_BOOKING_UI_KO.md`에 있으며, 구현된 API 계약으로 오해하면 안 된다.

## 5. 연결 코드 위치

- `static/venue/my_reservations.js`: 예매 목록·상세·결제 조회, 취소 요청, 재조회
- `static/venue/checkout.js`, `booking.js`: 결제 확인 정보·결제 시작·토스 SDK
- `static/venue/payment_result.js`: 서버 승인 요청·결과 확인·재시도
- `templates/profile.html`, `static/venue/profile_withdraw.js`: 회원 정보·비밀번호 변경·탈퇴
- `static/venue/admin_booking_api.js`, `manage_bookings.js`: 관리자 조회 화면·미연결 어댑터

테스트는 모의 API와 로컬 예시 데이터로 확인했다. 이 문서는 실제 토스 결제·환불 E2E 검증 완료를 의미하지 않는다.
