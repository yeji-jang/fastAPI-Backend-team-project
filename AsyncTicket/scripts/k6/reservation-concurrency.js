/**
 * 현재 API: POST /v1/reservations { perf_id, perf_seat_id }
 * 현재 정책: 1건=1좌석, 회원·회차별 PENDING/CONFIRMED 합계 최대 1건.
 * 결제나 서버 한계 부하를 시험하는 스크립트가 아니다.
 *
 * 준비: 예매 기간 내 회차, 양수 가격의 AVAILABLE 좌석, 가입된 테스트 계정.
 * 테스트 계정에는 해당 회차의 진행 중 예매가 없어야 한다.
 * 실행 폴더: AsyncTicket (k6 별도 설치 필요)
 *
 * PowerShell: 서로 다른 회원이 같은 좌석에 경쟁
 * $env:BASE_URL = 'http://localhost:8000'
 * $env:PERF_ID = '2'
 * $env:SEAT_IDS = '6'
 * $env:ACCOUNTS_JSON = '[{"email":"user1@example.com","password":"password123!"},{"email":"user2@example.com","password":"password123!"}]'
 * k6 run scripts/k6/reservation-concurrency.js
 *
 * 같은 회원이 서로 다른 좌석에 경쟁 (최소 두 좌석, 첫 계정 사용)
 * $env:CASE = 'same-user'
 * $env:SEAT_IDS = '6,7'
 * k6 run scripts/k6/reservation-concurrency.js
 *
 * 로그인 대신 이미 발급한 토큰 사용 가능 (ACCOUNTS_JSON보다 우선):
 * $env:TOKENS_JSON = '["token-a","token-b"]'
 * 테스트 후 환경변수에서 비밀번호·토큰을 제거하고 Git에 저장하지 않는다.
 *
 * 각 실행은 경쟁 한 번뿐이다. 반복할 때는 새 회차/좌석/계정을 준비하거나
 * 테스트 데이터만 복원한다. PENDING 예매는 현재 취소 API로 정리할 수 없어
 * 자동 취소·삭제를 하지 않는다. 결제·로그아웃도 호출하지 않는다.
 * 성공 예매 ID는 로그에 남긴다. 테스트 전용 환경에서 실행한다.
 *
 * API 조회는 DB 전체 불변식의 증명이 아니다. 실행 후 DB에서도 확인:
 * (아래 10을 PERF_ID로 교체)
 * SELECT user_id, count(*) FROM reservations
 * WHERE perf_id = 2 AND status IN ('PENDING','CONFIRMED')
 * GROUP BY user_id HAVING count(*) > 1; -- 현재 정책: 0행이어야 함
 *
 * SELECT r.reserv_id FROM reservations r
 * LEFT JOIN performance_seats s ON s.reserv_id = r.reserv_id
 * WHERE r.perf_id = 2 AND r.status IN ('PENDING','CONFIRMED')
 * GROUP BY r.reserv_id HAVING count(s.perf_seat_id) <> 1; -- 0행
 *
 * SELECT si.perf_id, s.seat_seq, count(*) FROM performance_seats s
 * JOIN seats_info si ON si.seat_id = s.seat_id2
 * WHERE si.perf_id = 2 AND s.reserv_id IS NOT NULL
 * GROUP BY si.perf_id, s.seat_seq HAVING count(*) > 1; -- 0행
 */
import http from "k6/http";
import { check } from "k6";

const BASE_URL = (__ENV.BASE_URL || "http://localhost:8000").replace(/\/$/, "");
const CASE = __ENV.CASE || "same-seat";
const PERF_ID = Number(__ENV.PERF_ID);
const SEAT_IDS = (__ENV.SEAT_IDS || "").split(",").map(Number);
const TOKENS = JSON.parse(__ENV.TOKENS_JSON || "[]");
const ACCOUNTS = JSON.parse(__ENV.ACCOUNTS_JSON || "[]");
const REQUEST_COUNT =
  CASE === "same-user" ? SEAT_IDS.length : TOKENS.length || ACCOUNTS.length;

if (!["same-seat", "same-user"].includes(CASE))
  throw new Error("CASE: same-seat 또는 same-user");
if (!Number.isSafeInteger(PERF_ID) || PERF_ID <= 0)
  throw new Error("PERF_ID: 양의 정수 필요");
if (SEAT_IDS.some((id) => !Number.isSafeInteger(id) || id <= 0))
  throw new Error("SEAT_IDS: 양의 정수 필요");
if (REQUEST_COUNT < 2 || REQUEST_COUNT > 100)
  throw new Error("경쟁 요청은 2~100개로 설정");
if (CASE === "same-seat" && SEAT_IDS.length !== 1)
  throw new Error("same-seat: 좌석 ID 한 개 필요");
if (CASE === "same-user" && new Set(SEAT_IDS).size !== SEAT_IDS.length)
  throw new Error("same-user: 서로 다른 좌석 필요");
if (!TOKENS.length && !ACCOUNTS.length)
  throw new Error("TOKENS_JSON 또는 ACCOUNTS_JSON 필요");

export const options = {
  // 한 VU에서 batch로 서로 다른 인증 요청을 병렬 전송하고 결과를 함께 비교한다.
  // VU 수가 아니라 batch 요청 수가 경쟁 요청 수다. 정확한 동시 도착은 보장하지 않는다.
  scenarios: {
    race: {
      executor: "shared-iterations",
      vus: 1,
      iterations: 1,
      maxDuration: "2m",
    },
  },
  batch: REQUEST_COUNT,
  batchPerHost: REQUEST_COUNT,
  setupTimeout: "5m",
  thresholds: { checks: ["rate==1"], http_req_failed: ["rate==0"] },
};

function params(token, phase) {
  return {
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    timeout: "30s",
    redirects: 0,
    tags: { phase, name: phase },
  };
}

function json(response) {
  try {
    return response.json();
  } catch (_) {
    return null;
  }
}

function requireData(response, label) {
  const body = json(response);
  if (
    response.status !== 200 ||
    !body ||
    body.success !== true ||
    body.data == null
  ) {
    throw new Error(
      `${label}: HTTP ${response.status}, code=${body ? body.code : "non-JSON"}`,
    );
  }
  return body.data;
}

function active(rows) {
  return rows.filter(
    (r) => r.perf_id === PERF_ID && ["PENDING", "CONFIRMED"].includes(r.status),
  );
}

export function setup() {
  let tokens = TOKENS;
  if (!tokens.length) {
    const accounts = CASE === "same-user" ? ACCOUNTS.slice(0, 1) : ACCOUNTS;
    tokens = accounts.map((account, i) => {
      const response = http.post(
        `${BASE_URL}/v1/auth/login`,
        JSON.stringify(account),
        {
          headers: { "Content-Type": "application/json" },
          timeout: "30s",
          redirects: 0,
          tags: { phase: "login", name: "login" },
        },
      );
      const result = requireData(response, `계정 ${i + 1} 로그인`);
      if (!result.access_token)
        throw new Error("로그인 응답에 data.access_token 없음");
      return result.access_token;
    });
  }
  if (CASE === "same-user") tokens = tokens.slice(0, 1);
  const userIds = tokens.map((token, i) => {
    const user = requireData(
      http.get(`${BASE_URL}/v1/users/me`, params(token, "preflight_user")),
      `회원 ${i + 1} 인증`,
    );
    if (!user.user_id) throw new Error("인증 응답에 user_id 없음");
    const rows = requireData(
      http.get(
        `${BASE_URL}/v1/reservations`,
        params(token, "preflight_reservations"),
      ),
      "기존 예매 확인",
    );
    if (!Array.isArray(rows) || active(rows).length !== 0)
      throw new Error(
        `회원 ${user.user_id}: 테스트 회차의 기존 예매를 먼저 정리`,
      );
    return user.user_id;
  });
  if (CASE === "same-seat" && new Set(userIds).size !== userIds.length)
    throw new Error("same-seat: 서로 다른 회원 계정 필요");
  const seats = requireData(
    http.get(`${BASE_URL}/v1/performances/${PERF_ID}/seats`, {
      timeout: "30s",
      tags: { phase: "preflight_seats" },
    }),
    "좌석 확인",
  );
  if (!Array.isArray(seats.items))
    throw new Error("좌석 응답에 data.items 없음");
  SEAT_IDS.forEach((id) => {
    const seat = seats.items.find((s) => s.perf_seat_id === id);
    if (!seat || seat.status !== "AVAILABLE")
      throw new Error(`좌석 ${id}: 해당 회차의 AVAILABLE 좌석 필요`);
  });
  console.log(
    `준비 완료: case=${CASE}, perf_id=${PERF_ID}, requests=${REQUEST_COUNT}`,
  );
  return { tokens, userIds };
}

export default function (data) {
  const requests = Array.from({ length: REQUEST_COUNT }, (_, i) => {
    const token = data.tokens[CASE === "same-user" ? 0 : i];
    return {
      method: "POST",
      url: `${BASE_URL}/v1/reservations`,
      body: JSON.stringify({
        perf_id: PERF_ID,
        perf_seat_id: SEAT_IDS[CASE === "same-user" ? i : 0],
      }),
      params: {
        ...params(token, "race"),
        responseCallback: http.expectedStatuses(201, 409),
      },
    };
  });
  const responses = http.batch(requests);
  const created = [];
  responses.forEach((response, i) => {
    const body = json(response);
    const seatId = SEAT_IDS[CASE === "same-user" ? i : 0];
    const success =
      response.status === 201 &&
      body &&
      body.success === true &&
      body.code === "RESERVATION_CREATED" &&
      body.data &&
      body.data.reserv_id > 0 &&
      body.data.perf_id === PERF_ID &&
      body.data.perf_seat_id === seatId &&
      body.data.quantity === 1 &&
      body.data.status === "PENDING";
    const conflict =
      response.status === 409 &&
      body &&
      body.success === false &&
      (CASE === "same-seat"
        ? body.code === "SEAT_RESERVATION_CONFLICT"
        : body.code === "RESERVATION_ALREADY_EXISTS");
    check(response, {
      "예매 성공 또는 의도한 경쟁 충돌": () => Boolean(success || conflict),
    });
    if (success) created.push(body.data);
    console.log(
      `요청 ${i + 1}: HTTP ${response.status}, code=${body ? body.code : "non-JSON"}, reserv_id=${success ? body.data.reserv_id : "-"}`,
    );
  });
  check(created, { "정확히 한 요청만 예매 성공": (rows) => rows.length === 1 });

  // 경쟁이 끝난 후 모든 참여 회원 조회: 실패 요청의 잔여 예매도 검사한다.
  const persisted = [];
  data.tokens.forEach((token) => {
    const response = http.get(
      `${BASE_URL}/v1/reservations`,
      params(token, "verify"),
    );
    const body = json(response);
    const valid =
      response.status === 200 &&
      body &&
      body.success === true &&
      Array.isArray(body.data);
    check(response, { "경쟁 후 예매 목록 조회 성공": () => Boolean(valid) });
    if (valid) persisted.push(...active(body.data));
  });
  check(persisted, {
    "참여 회원의 회차별 최종 예매 합계 1건": (rows) => rows.length === 1,
    "최종 예매가 성공 응답과 일치하고 좌석 연결 유지": (rows) =>
      rows.length === 1 &&
      created.length === 1 &&
      rows[0].reserv_id === created[0].reserv_id &&
      rows[0].perf_seat_id === created[0].perf_seat_id,
  });
  console.log(
    "API 검증 종료. 파일 상단의 SQL로 최종 DB 상태도 확인하세요. 재실행 전 테스트 데이터를 복원하세요.",
  );
}
