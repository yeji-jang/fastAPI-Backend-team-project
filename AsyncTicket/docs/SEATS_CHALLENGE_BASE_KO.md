# 좌석 도전과제 공통 기반 (2026-11-08)

이 문서는 좌석 담당이 제공하는 내부 함수와 협의할 연결 지점을 정리한다. 도전 A·B·C 전체 구현 완료나 예매·결제 통합 완료를 의미하지 않는다. 공통·다른 담당 코드는 수정하지 않는다.

## 현재 사용할 함수

`asyncticket.wiring.performance_seats.create_performance_seat_service(session)`에 호출부의 AsyncSession을 넘기면 동일 세션의 좌석 서비스·저장소를 만든다. 함수 호출에는 HTTP 요청이 필요하지 않다.

| 함수 | 입력 | 결과 |
| --- | --- | --- |
| get_performance_seat_by_id | perf_id, perf_seat_id (키워드 인자) | 회차·좌석 ID가 함께 일치하는 좌석의 ID, 등급, 가격(int 또는 기존 데이터의 None), 상태 등 조회 |
| assign_reservation | perf_id, perf_seat_id, reserv_id, expected_status, reserved_status | 조건이 일치하면 예매 연결과 전달받은 좌석 상태 기록, 반환 None |
| release_reservation | perf_id, perf_seat_id, reserv_id, expected_status, released_status | 현재 연결된 예매·상태·회차가 일치하면 reserv_id=NULL 및 전달받은 좌석 상태 기록, 반환 None |

조회는 선점이 아니다. 조회 이후 변경될 수 있으므로 연결 UPDATE에서 조건을 다시 확인한다. 가격이 None이면 호출자가 미설정 데이터로 처리해야 하며 무료 가격 0으로 바꾸면 안 된다. Decimal 금액이 필요한 호출부는 DB에서 받은 유효한 int 가격을 변환한다.

- 조회 실패: 회차 없음 PERFORMANCE_NOT_FOUND / 좌석 없음 또는 다른 회차 SEAT_NOT_FOUND (404).
- 연결·해제 조건 불일치: SEAT_RESERVATION_CONFLICT (409).
- 같은 해제 요청 반복: 충돌. 이전 예매의 늦은 요청으로 재예매 좌석을 해제하지 않는다.
- 조회·연결·해제 함수는 commit/flush/rollback을 호출하지 않는다. 최종 확정과 실패 rollback은 예매 조율부 책임이다.
- 좌석 상태 인자는 팀이 합의한 문자열을 전달한다. 결제 결과·예매 상태·권한·기간·만료 판단은 좌석 함수의 책임이 아니다.
- `assign_reservation`은 미연결 좌석 전용이다. 이미 연결된 좌석의 선점→확정 상태 변경 함수로 사용할 수 없다. 확정 때 좌석 상태를 별도로 바꾸기로 합의하면 별도 이슈로 구현한다.

## A: 동시 예매·커넥션 풀 실험 연결점

최신 Slack 방향은 예매 PENDING을 먼저 저장하고 결제 결과에 따라 확정하는 흐름이다. 한 요청 안에서는 예매 저장·flush 후 같은 세션의 assign을 호출하며, 그 요청의 트랜잭션은 예매 측이 확정/취소한다. 브라우저 결제를 기다리는 동안 DB 트랜잭션을 열어두지 않는다.

현재 PostgreSQL 좌석 경쟁 검사는 미리 만든 예매들의 좌석 연결 경쟁이다. 다음은 예매 담당과 함께할 통합 검증이며 아직 완료하지 않았다.

- 정상 PENDING 생성 → 좌석 연결 → commit.
- 같은 좌석 10건 생성 요청: 성공 1건, 연결 경쟁에서 거절된 요청의 새 예매는 rollback.
- commit된 PENDING의 결제 실패·이탈 후 보존은 위 경쟁 rollback과 다른 정책이다. 해제 시점과 보존·정리 기간을 협의한다.
- 커넥션 풀 크기·대기 시간·타임아웃 실험은 별도 과제다.

## B: 후처리·CSV 연결점

좌석 목록 조회 `list_performance_seats(perf_id)`와 응답 필드는 이미 제공한다. 기존 HTTP 응답은 APIResponse를 사용한다.

- CSV 대상(좌석 재고/예매 목록 등)과 컬럼·권한·정렬을 팀에서 결정한다.
- CSV는 파일 응답이므로 JSON APIResponse로 감싸는 기존 조회 API와 별도 계약으로 다룬다.
- BackgroundTasks에 요청 세션을 그대로 넘기지 않는다. 필요하면 후처리 담당이 별도 세션과 실패 처리 방법을 구성한다.
- PENDING 만료 정리를 단순 인프로세스 BackgroundTasks만으로 보장한다고 주장하지 않는다. 실행 주체·재시작·재시도는 별도 이슈다.

## C: 캐시·배포 연결점

후보는 기존 회차별 좌석 목록/좌석 상세 조회다. 실제 키·TTL·저장소·배포 구성은 아직 추가하지 않았다.

- 후보 키는 회차·개별 좌석 ID를 포함해 다른 회차와 섞이지 않게 한다.
- 좌석 구성·가격 변경, 선점·해제, 합의된 확정 전이 후 조회 캐시 무효화를 검토한다.
- 연결·해제 함수는 commit을 소유하지 않으므로 캐시 무효화를 함수 호출 성공만으로 확정하지 않는다. commit 이후 처리 책임을 조율부와 정한다.
- 예매 연결 가능 여부의 최종 판단은 DB 조건부 UPDATE로 유지한다. 캐시로 좌석 배정 성공을 결정하지 않는다.
- 배포와 비밀 설정은 공통 담당 범위다. 이번 작업에서는 변경하지 않는다.

## 지금 해야 할 순서

1. 예매 담당과 좌석 ID(perf_seat_id), 상태 의미/전이, 선점·확정·해제·만료 호출 시점을 맞춘다. 만료 시간은 예시값으로 고정하지 않는다.
2. 이슈 1: 좌석 예매 연결 해제 함수와 검증을 PR로 정리한다.
3. 이슈 2: 예매용 좌석 ID 조회 함수와 검증을 PR로 정리한다. 같은 파일의 변경도 이슈별로 나누어 커밋한다.
4. 위 PR 반영 후 예매 담당과 정상 요청 1건을 실제 서비스로 연결·검증한다. 다른 담당 파일을 좌석 PR에 포함하지 않는다.
5. 그 기반에서 도전 A를 진행한다. B·C 담당과 CSV 대상/캐시 대상을 결정한다.

APIResponse 적용은 좌석 HTTP 6개 경로 기준이다. 실제 JWT부터 결제까지의 전체 E2E 검증은 별도다. 좌석 가격>=0과 예매 총액>0의 차이는 팀 정책 확인 대상으로 유지한다. reservation_items는 사용하지 않는다.

## 근거

- [최신 결제·예매 순서](https://2026kant.slack.com/archives/C0CC6MECVU4/p1793973094578249)
- [좌석 식별자·가격 연동 논의](https://2026kant.slack.com/archives/C0CC6MECVU4/p1793936706138939)
- [도전 A·B·C 안내](https://2026kant.slack.com/archives/C0CC6MECVU4/p1793923829292569)
- [좌석 테스트 시나리오](SEATS_TEST_SCENARIOS_KO.md)
