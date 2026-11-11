// 금액과 주문번호는 브라우저에서 만들지 않고 예매·결제 API 응답을 사용한다.
const bookingGateway = (() => {
    let sdkRequest;
    let paymentOpening = false;
    // 결제 화면에서 뒤로 돌아오면 오래된 예매 상태와 비활성 버튼을 새로 읽는다.
    window.addEventListener("pageshow", event => {
        if (event.persisted) location.reload();
    });
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

    function loadToss() {
        if (window.TossPayments) return Promise.resolve();
        if (!sdkRequest) {
            sdkRequest = new Promise((resolve, reject) => {
                const script = document.createElement("script");
                script.src = "https://js.tosspayments.com/v2/standard";
                script.onload = resolve;
                script.onerror = () => {
                    script.remove();
                    reject(new Error("결제창을 불러오지 못했습니다."));
                };
                document.head.append(script);
            }).catch(error => { sdkRequest = null; throw error; });
        }
        return sdkRequest;
    }

    async function resumePayment(reservationId) {
        if (paymentOpening) throw new Error("이미 결제창을 여는 중입니다.");
        const id = Number(reservationId);
        if (!Number.isSafeInteger(id) || id <= 0) throw new Error("예매 번호를 확인해 주세요.");
        paymentOpening = true;
        try {
            const user = await buyer();
            // 목록에 남은 예매라도 결제 시작 직전에 서버의 현재 상태를 확인한다.
            const reservation = await request(`/v1/reservations/${id}`);
            if (reservation.status !== "PENDING") {
                throw new Error(reservation.status === "CONFIRMED" ? "이미 확정된 예매입니다." : "결제를 진행할 수 없는 예매입니다.");
            }
            const clientKey = (await config()).toss_client_key;
            if (!clientKey) throw new Error("현재 온라인 결제를 이용할 수 없습니다.");
            await loadToss();
            // READY 결제가 있으면 서버가 같은 결제를 반환한다. 예매는 새로 생성하지 않는다.
            const payment = await request("/v1/payments", {
                method: "POST", body: JSON.stringify({ reserv_id: id }),
            });
            const amount = Number(payment.amount);
            if (payment.status !== "READY" || !Number.isSafeInteger(amount) || amount <= 0
                || amount !== Number(reservation.total_amount)) {
                throw new Error("결제 상태와 금액을 다시 확인해 주세요.");
            }
            const storageKey = `asyncticket_customer_${user.user_id}`;
            let customerKey;
            try {
                customerKey = localStorage.getItem(storageKey);
                if (!customerKey) {
                    customerKey = crypto.randomUUID();
                    localStorage.setItem(storageKey, customerKey);
                }
            } catch {
                customerKey = crypto.randomUUID();
            }
            const toss = window.TossPayments(clientKey).payment({ customerKey });
            await toss.requestPayment({
                method: "CARD", amount: { value: amount, currency: "KRW" },
                orderId: payment.order_id, orderName: "AsyncTicket 좌석 예매",
                successUrl: `${location.origin}/payment/success`, failUrl: `${location.origin}/payment/fail`,
            });
        } finally {
            paymentOpening = false;
        }
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

    return { request, config, buyer, startPayment, resumePayment };
})();
