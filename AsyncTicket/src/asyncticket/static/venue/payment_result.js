document.addEventListener("DOMContentLoaded", async () => {
    const result = document.querySelector("[data-payment-result]").dataset.paymentResult;
    const status = document.getElementById("payment-status");
    const retry = document.getElementById("approve");
    const params = new URLSearchParams(location.search);
    const paymentKey = params.get("paymentKey"), orderId = params.get("orderId"), amount = params.get("amount");
    let busy = false;
    if (result === "fail") {
        status.textContent = "결제가 완료되지 않았습니다. 내 예매에서 상태를 확인해 주세요.";
        return;
    }
    // 승인 확인 전에는 새로고침으로 재시도할 수 있게 콜백을 유지한다. 완료 후 주소에서 제거한다.
    const idPart = /^([A-Za-z0-9_]+)-([1-9]\d*)$/.exec(orderId || "");
    const reservId = idPart ? Number(idPart[2]) : NaN;
    if (!paymentKey || !idPart || !Number.isSafeInteger(reservId) || !/^\d+$/.test(amount || "") || !Number.isSafeInteger(Number(amount)) || Number(amount) <= 0) {
        if (paymentKey) history.replaceState(null, "", "/payment/success");
        status.textContent = "결제 결과 정보를 확인할 수 없습니다. 내 예매에서 현재 상태를 조회해 주세요.";
        return;
    }
    async function approve() {
        if (busy) return;
        busy = true; retry.disabled = true; retry.hidden = true;
        status.textContent = "서버에서 결제 결과를 확인하는 중…";
        let retryable = true;
        try {
            const user = await accountSession.current();
            if (!user || user.role !== "BUYER") { retryable = false; throw new Error("구매자 로그인 후 내 예매에서 결제 상태를 확인해 주세요."); }
            // 재진입·재시도 때도 먼저 저장된 결과를 확인해 승인 요청을 중복하지 않는다.
            let payment = await bookingGateway.request(`/v1/reservations/${reservId}/payment`);
            if (payment.order_id !== orderId || Number(payment.amount) !== Number(amount)) { retryable = false; throw new Error("서버 주문번호·금액과 결제 결과가 일치하지 않습니다."); }
            if (payment.status === "READY") {
                payment = await bookingGateway.request("/v1/payments/approve", {
                    method: "POST", body: JSON.stringify({ payment_key: paymentKey, order_id: orderId, amount: Number(amount) }),
                });
            }
            if (payment.status !== "DONE") { retryable = false; throw new Error("결제가 완료 상태가 아닙니다. 내 예매에서 확인해 주세요."); }
            history.replaceState(null, "", "/payment/success");
            const reservation = await bookingGateway.request(`/v1/reservations/${reservId}`);
            status.textContent = reservation.status === "CONFIRMED"
                ? "결제가 승인되어 예매가 확정되었습니다. 내 예매에서 티켓을 확인하세요."
                : "결제는 완료되었습니다. 내 예매에서 예매 상태를 확인해 주세요.";
        } catch (error) {
            status.textContent = `${error.message || "결제 처리 결과를 확인하지 못했습니다."} 재결제하지 말고 현재 상태부터 확인해 주세요.`;
            retry.hidden = !retryable;
        } finally { busy = false; retry.disabled = false; }
    }
    retry.addEventListener("click", approve);
    await approve();
}, { once: true });
