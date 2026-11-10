/**
 * 현재 API: POST /v1/reservations { perf_id, perf_seat_id }
 * 현재 정책: 1건=1좌석, 예매 생성 후 PENDING 상태로 시작한다.
 * 목적: PENDING 예매가 만료된 뒤 같은 좌석을 다시 예매할 수 있는지 검증한다.
 * 결제나 서버 한계 부하를 시험하는 스크립트가 아니다.
 *
 * 시나리오:
 * 1. 첫 번째 회원이 좌석을 PENDING으로 예매한다.
 * 2. 만료 전 두 번째 회원의 같은 좌석 예매는 충돌로 거절된다.
 * 3. PENDING 만료 시간 5분과 백그라운드 확인 주기 60초를 고려해 6분 대기한다.
 * 4. 첫 번째 예매가 만료된 뒤 두 번째 회원이 같은 좌석을 재예매한다.
 *
 * 준비:
 * - 예매 기간 내 회차
 * - 양수 가격의 AVAILABLE 좌석
 * - 아래에 설정된 두 개의 가입 계정
 * - 두 계정 모두 해당 회차에 진행 중인 PENDING/CONFIRMED 예매가 없어야 한다.
 *
 * 실행 폴더: AsyncTicket (k6 별도 설치 필요)
 *
 * macOS/Linux:
 * export PERF_ID='1'
 * export SEAT_ID='1'
 * k6 run scripts/k6/reservation-expire-reuse.js
 *
 * Windows PowerShell:
 * $env:PERF_ID = '1'
 * $env:SEAT_ID = '1'
 * k6 run scripts/k6/reservation-expire-reuse.js
 *
 * PERF_ID는 공연 ID가 아니라 공연 회차 ID다.
 * SEAT_ID는 seats_info.seat_id가 아니라 performance_seats.perf_seat_id다.
 *
 * 기대 결과:
 * - 첫 번째 회원 예매: 201 RESERVATION_CREATED, status=PENDING
 * - 만료 전 두 번째 회원 예매: 409 SEAT_RESERVATION_CONFLICT
 * - 만료 후 두 번째 회원 재예매: 201 RESERVATION_CREATED, status=PENDING
 *
 * 한 번의 실행에서 HTTP 요청 5개(로그인 2회, 예매 3회)를 보낸다.
 * checks 성공률 100%, http_req_failed 0%를 통과 기준으로 한다.
 * 정확한 부하 테스트나 여러 VU의 동시성 성능 측정은 수행하지 않는다.
 * 테스트가 끝나면 두 번째 회원의 PENDING 예매가 남을 수 있으므로,
 * 같은 좌석으로 재실행할 때는 예매 만료를 기다리거나 테스트 데이터를 정리한다.
 */
import http from "k6/http";
import { check, sleep } from "k6";

const BASE_URL = "http://127.0.0.1:8000";
const PERF_ID = Number(__ENV.PERF_ID);
const SEAT_ID = Number(__ENV.SEAT_ID);

const ACCOUNTS = [
  {
    email: "codex-k6-1@example.com",
    password: "K6test20261110!",
  },
  {
    email: "codex-k6-2@example.com",
    password: "K6test20261110!",
  },
];

export const options = {
  scenarios: {
    first_user: {
      executor: "per-vu-iterations",
      vus: 1,
      iterations: 1,
      exec: "firstUser",
    },
    second_user: {
      executor: "per-vu-iterations",
      vus: 1,
      iterations: 1,
      startTime: "5s",
      exec: "secondUser",
    },
  },
  thresholds: {
    checks: ["rate==1"],
    http_req_failed: ["rate==0"],
  },
};

function login(account) {
  const response = http.post(
    `${BASE_URL}/v1/auth/login`,
    JSON.stringify(account),
    {
      headers: {
        "Content-Type": "application/json",
      },
    },
  );

  check(response, {
    "로그인 성공": (res) => res.status === 200,
  });

  return response.json().data.access_token;
}

function reserve(token) {
  return http.post(
    `${BASE_URL}/v1/reservations`,
    JSON.stringify({
      perf_id: PERF_ID,
      perf_seat_id: SEAT_ID,
    }),
    {
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      responseCallback: http.expectedStatuses(201, 409),
    },
  );
}

export function firstUser() {
  const token = login(ACCOUNTS[0]);
  const response = reserve(token);

  check(response, {
    "첫 번째 회원이 PENDING 예매 성공": (res) =>
      res.status === 201 &&
      res.json().code === "RESERVATION_CREATED" &&
      res.json().data.status === "PENDING",
  });
}

export function secondUser() {
  const token = login(ACCOUNTS[1]);

  const firstAttempt = reserve(token);

  check(firstAttempt, {
    "만료 전에는 좌석 충돌": (res) =>
      res.status === 409 &&
      res.json().code === "SEAT_RESERVATION_CONFLICT",
  });

  // PENDING 5분 + 백그라운드 확인 주기 60초를 고려해 6분 대기
  sleep(360);

  const retry = reserve(token);

  check(retry, {
    "첫 예매 만료 후 두 번째 회원 예매 성공": (res) =>
      res.status === 201 &&
      res.json().code === "RESERVATION_CREATED" &&
      res.json().data.status === "PENDING",
  });
}
