# 관리자 예매·결제 화면 — 조회 API 연결 대기

- 화면: `/manage/bookings`. ADMIN 메뉴에만 표시한다.
- 프론트 범위: 목록·상세, 검색·상태 필터·페이지 UI, 조회 API 호출·응답 표시, 로딩·빈 목록·오류 안내.
- 백엔드 업무 API·SQL 조회·DB 스키마·상태 변경·wiring은 추가하지 않는다.
- web.py의 경로는 HTML 템플릿을 렌더링할 뿐 DB나 업무 서비스를 호출하지 않는다.
- 현재 관리자 조회 API는 없으므로 호출 주소는 null이다. 기존 API가 제공되면 확정된 주소와 응답 매핑만 연결한다.
- 구매자 본인의 예매 API를 관리자 전체 조회로 대체하지 않는다.
- 프론트 메뉴 숨김은 보안 경계가 아니다. 백엔드 API가 토큰과 관리자 권한을 검사해야 한다.

## 시스템 상태 처리

예매 확정·구매자 취소·좌석 해제·기간 만료·결제 승인·환불은 기존 시스템이 처리한다.
프론트는 예매 상태와 결제 상태를 각각 조회해 표시하고 변경 요청을 보내지 않는다.
예매 상태로 결제 성공·실패·환불을 추측하지 않는다.
최신 상태 조회 버튼은 같은 검색 조건과 페이지를 다시 요청하고 마지막 조회 시각을 표시한다.
실시간 푸시는 구현하지 않았다.

## 조회 어댑터

`static/venue/admin_booking_api.js`의 `createAdminBookingApi`는 listUrl과 detailUrl을 받아 GET 요청만 보낸다.
현재 기본 어댑터는 미연결이다. 서버 주소를 임의로 정의하지 않는다.
목데이터는 별도 로컬 미리보기에만 주입한다. 운영 화면은 실제 데이터 대신 API 미연결 안내를 표시한다.

## 응답 형식 제안 — 확정된 백엔드 계약 아님

목록 입력: page, size, query(공연명·예매번호), reservation_status, payment_status.
팀 공통 응답 data: `{ "items": [...], "total": 0 }`.
각 항목: reserv_id, order_number, show_title, seat_label, reservation_status, total_amount, payment_status.
상세: 같은 필드에 venue_name, starts_at(시간대 포함 ISO 8601), payment_order_id, payment_amount.
결제 레코드가 없으면 결제 관련 값은 null이다. 해제된 좌석의 연결이 없으면 seat_label은 null이다.
결제 상태 READY/DONE/FAIL/REFUND, 예매 상태 PENDING/CONFIRMED/CANCELED/EXPIRED를 표시한다.
실제 결제 없이 완료·환불 값을 만들어내지 않는다. paymentKey·결제 로그·비밀번호는 요청하거나 표시하지 않는다.

실제 데이터 조회는 관리자 API가 제공된 뒤 연결·검증한다. 현재 화면은 PR·서버 배포 전이다.
