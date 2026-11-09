// 금액과 주문번호는 브라우저에서 만들지 않고 예매·결제 API 응답을 사용한다.
const bookingGateway = (() => {
    async function request(path, options = {}) {
        const response = await fetch(path, {
            ...options,
            headers: { ...accountSession.headers(), "Content-Type": "application/json", ...options.headers },
            cache: "no-store",
        });
        const body = await response.json().catch(() => null);
        if (!response.ok || body?.success !== true) {
            const error = new Error(body?.message || "요청을 처리하지 못했습니다.");
            error.status = response.status;
            throw error;
        }
        return body.data;
    }

    async function config() {
        const response = await fetch("/web/config", { cache: "no-store" });
        if (!response.ok) throw new Error("결제 설정을 확인하지 못했습니다.");
        return response.json();
    }

    async function buyer() {
        const user = await accountSession.current();
        if (!user) {
            const next = location.pathname + location.search;
            location.assign(`/login?next=${encodeURIComponent(next)}`);
            throw new Error("로그인 후 예매할 수 있습니다.");
        }
        if (user.role !== "BUYER") throw new Error("구매자 계정에서 예매할 수 있습니다.");
        return user;
    }

    async function startPayment({ performanceId, performanceSeatId }) {
        await buyer();
        if (!(await config()).toss_client_key) {
            throw new Error("현재 온라인 결제를 이용할 수 없습니다. 예매는 생성되지 않았습니다.");
        }
        const ids = [Number(performanceId), Number(performanceSeatId)];
        if (ids.some(id => !Number.isSafeInteger(id) || id <= 0)) throw new Error("회차와 좌석을 다시 선택해 주세요.");
        // 이미 생성한 같은 좌석의 대기 예매는 중복 생성하지 않고 결제를 이어간다.
        const records = await request("/v1/reservations");
        const pending = records.find(item => item.status === "PENDING"
            && item.perf_id === ids[0] && item.perf_seat_id === ids[1]);
        const reservation = pending || await request("/v1/reservations", {
            method: "POST", body: JSON.stringify({ perf_id: ids[0], perf_seat_id: ids[1] }),
        });
        location.assign(`/checkout/${encodeURIComponent(reservation.reserv_id)}`);
    }

    return { request, config, buyer, startPayment };
})();
