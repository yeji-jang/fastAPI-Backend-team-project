document.addEventListener("DOMContentLoaded", async () => {
    const get = id => document.getElementById(id);
    const reservationId = document.querySelector(".checkout-page").dataset.reservationId;
    const payButton = get("pay");
    const status = get("checkout-status");

    // 공연 상세 조회가 실패해도 기존 결제 흐름은 유지한다.
    async function loadDetails(reservation) {
        let incomplete = false;
        try {
            const round = await requestApi(`/v1/performances/${reservation.perf_id}`, { cache: "no-store" });
            get("checkout-date").textContent = `${formatDate(round.starts_at)} · ${round.round_number}회차`;
            const show = await requestApi(`/v1/shows/${round.show_id}`, { cache: "no-store" });
            get("checkout-title").textContent = show.title;
            get("poster-title").textContent = show.title;
            get("poster-performer").textContent = show.performer || "";
            get("checkout-performer").textContent = show.performer || "";
            get("poster-genre").textContent = show.type || "LIVE";
            const venue = await requestApi(`/v1/venues?venues_id=${show.venues_id}`, { cache: "no-store" });
            get("checkout-venue").textContent = venue.name;
        } catch {
            incomplete = true;
            if (get("checkout-date").textContent === "확인 중…") get("checkout-date").textContent = "공연 일시 확인 필요";
            if (get("checkout-venue").textContent === "확인 중…") get("checkout-venue").textContent = "공연장 정보 확인 필요";
        }
        return incomplete;
    }

    async function loadSeat(reservation) {
        if (reservation.perf_seat_id == null) {
            get("checkout-seat").textContent = "좌석 정보 없음";
            return false;
        }
        get("checkout-seat").textContent = "좌석 정보 확인 필요";
        try {
            const seats = await requestApi(`/v1/performances/${reservation.perf_id}/seats`, { cache: "no-store" });
            const seat = seats.items.find(item => item.perf_seat_id === reservation.perf_seat_id);
            if (!seat) return true;
            get("checkout-seat").textContent = [seat.grade, seat.seat_seq].filter(Boolean).join(" · ");
            return false;
        } catch { return true; }
    }

    payButton.addEventListener("click", async () => {
        payButton.disabled = true;
        status.textContent = "토스 결제창을 준비하는 중…";
        try {
            await bookingGateway.resumePayment(reservationId);
            status.textContent = "결제창 안내를 확인해 주세요.";
        } catch (error) {
            status.textContent = error.code === "USER_CANCEL"
                ? "결제창을 닫았어요. 다시 이어서 결제할 수 있어요."
                : error.message || "결제 요청을 처리하지 못했습니다.";
        } finally { payButton.disabled = false; }
    });

    try {
        await bookingGateway.buyer();
        const reservation = await bookingGateway.request(`/v1/reservations/${reservationId}`);
        get("checkout-title").textContent = "공연 정보 확인 필요";
        get("checkout-order").textContent = reservation.order_number;
        const amount = Number(reservation.total_amount);
        get("checkout-amount").textContent = Number.isFinite(amount) && amount > 0 ? `${amount.toLocaleString("ko-KR")}원` : "금액 확인 필요";
        get("checkout-summary").hidden = false;
        // 공연·좌석은 표시용이며 결제 금액은 예매·결제 API 응답을 사용한다.
        const details = Promise.all([loadDetails(reservation), loadSeat(reservation)]).then(results => {
            if (results.some(Boolean)) get("checkout-detail-status").textContent = "일부 공연 정보를 불러오지 못했어요. 내 예매 목록에서도 확인할 수 있어요.";
        });
        await details;
        if (reservation.status !== "PENDING") {
            status.textContent = reservation.status === "CONFIRMED" ? "이미 확정된 예매입니다." : "결제를 진행할 수 없는 예매입니다.";
        } else if (!Number.isSafeInteger(amount) || amount <= 0) {
            status.textContent = "결제 금액을 확인할 수 없습니다.";
        } else if (!(await bookingGateway.config()).toss_client_key) {
            status.textContent = "현재 온라인 결제를 이용할 수 없습니다. 잠시 후 내 예매에서 다시 시도해 주세요.";
        } else {
            status.textContent = "공연과 좌석을 확인한 뒤 결제를 진행해 주세요.";
            payButton.disabled = false;
        }
    } catch (error) {
        if (get("checkout-summary").hidden) get("checkout-title").textContent = "예매 정보 확인 필요";
        status.textContent = error.message || "예매 정보를 불러오지 못했습니다.";
    }
}, { once: true });
