document.addEventListener("DOMContentLoaded", () => {
    const get = id => document.getElementById(id);
    const status = get("reservation-status");
    const list = get("reservation-list");
    const filters = [...document.querySelectorAll(".ticket-filter")];
    const labels = { PENDING: "결제 대기", CONFIRMED: "예매 확정", CANCELED: "예매 취소", EXPIRED: "예매 만료" };
    let selected = "ALL";
    let views = [];
    let loading = false;
    let cancelling = false;
    const paymentLabels = { READY: "결제 대기", DONE: "결제 완료", FAIL: "결제 실패", REFUND: "환불 완료" };
    const details = new Map();

    function text(tag, className, value) {
        const node = document.createElement(tag);
        node.className = className;
        node.textContent = value;
        return node;
    }

    function readOnce(url) {
        if (!details.has(url)) {
            const pending = requestApi(url, { cache: "no-store" }).catch(error => {
                if (details.get(url) === pending) details.delete(url);
                throw error;
            });
            details.set(url, pending);
        }
        return details.get(url);
    }

    function applyFilters() {
        const query = get("ticket-search").value.trim().toLocaleLowerCase("ko-KR");
        let visible = 0;
        for (const view of views) {
            const state = view.record.status;
            const matchesState = selected === "ALL" || selected === state
                || (selected === "CLOSED" && ["CANCELED", "EXPIRED"].includes(state));
            const matchesQuery = `${view.title.textContent} ${view.record.order_number || ""}`.toLocaleLowerCase("ko-KR").includes(query);
            view.item.hidden = !(matchesState && matchesQuery);
            if (!view.item.hidden) visible++;
        }
        get("ticket-page-label").textContent = `${visible}건 / 전체 ${views.length}건`;
        get("ticket-empty").hidden = visible > 0;
        status.textContent = !views.length ? "아직 예매 내역이 없어요. 다음 공연을 찾아보세요."
            : !visible ? "선택한 조건에 맞는 예매가 없어요." : "";
    }

    function render(record, index) {
        const item = text("li", "ticket-row", "");
        const main = text("div", "ticket-main", "");
        const top = text("div", "ticket-topline", "");
        const badge = text("span", "ticket-badge", labels[record.status] || record.status);
        badge.dataset.status = record.status;
        top.append(badge, text("span", "ticket-order", record.order_number || `예매 #${record.reserv_id}`));
        const title = text("a", "ticket-title", `공연 회차 #${record.perf_id}`);
        title.href = `/performances/${encodeURIComponent(record.perf_id)}`;
        const date = text("p", "ticket-date", "공연 일시를 확인하는 중…");
        const venue = text("p", "ticket-venue", "공연장 정보를 확인하는 중…");
        const seat = text("p", "ticket-seat", record.perf_seat_id == null ? "좌석 정보 없음" : `좌석 #${record.perf_seat_id}`);
        const note = text("p", "ticket-note", "");
        main.append(top, title, date, venue, seat, note);
        const side = text("div", "ticket-side", "");
        const amount = Number(record.total_amount);
        const amountLabel = Number.isFinite(amount) && amount >= 0 && record.total_amount != null
            ? `${amount.toLocaleString("ko-KR")}원` : "금액 확인 필요";
        side.append(text("p", "ticket-price-label", "예매 금액"), text("p", "ticket-price", amountLabel));
        const paymentLine = text("p", "ticket-payment", "결제 상태 확인 중…");
        main.append(paymentLine);
        const detailPanel = text("details", "ticket-extra", "");
        detailPanel.append(text("summary", "", "예매·결제 상세 보기"));
        const detailBody = text("div", "", ""); detailPanel.append(detailBody); main.append(detailPanel);
        const view = { item, record, title, date, venue, seat, note, paymentLine, detailBody };
        let detailLoaded = false, detailLoading = false;
        detailPanel.addEventListener("toggle", async () => {
            if (!detailPanel.open || detailLoaded || detailLoading) return;
            detailLoading = true;
            detailBody.textContent = "상세 정보를 조회하는 중…";
            try {
                const current = await requestApi(`/v1/reservations/${record.reserv_id}`, { headers: accountSession.headers(), cache: "no-store" });
                if (current.status !== view.record.status) {
                    await loadReservations();
                    status.textContent = "예매 상태가 변경되어 목록을 다시 조회했습니다.";
                    return;
                }
                const dl = text("dl", "", "");
                const fields = [["예매번호", current.order_number], ["예매 상태", labels[current.status] || current.status], ["예매 수량", current.quantity], ["예매 일시", current.created_at ? formatDate(current.created_at) : "확인 필요"], ["확정 일시", current.confirmed_at ? formatDate(current.confirmed_at) : "—"], ["취소 일시", current.canceled_at ? formatDate(current.canceled_at) : "—"]];
                for (const [label, value] of fields) dl.append(text("dt", "", label), text("dd", "", value ?? "확인 필요"));
                if (current.perf_seat_id != null) {
                    try {
                        const owned = await requestApi(`/v1/reservations/${record.reserv_id}/seats`, { headers: accountSession.headers(), cache: "no-store" });
                        dl.append(text("dt", "", "예매 좌석"), text("dd", "", owned.items.map(s => [s.grade, s.seat_seq].filter(Boolean).join(" · ")).join(", ") || "좌석 연결 없음"));
                    } catch { dl.append(text("dt", "", "예매 좌석"), text("dd", "", "좌석 상세 조회 실패")); }
                } else dl.append(text("dt", "", "예매 좌석"), text("dd", "", "좌석 연결 없음"));
                detailBody.replaceChildren(dl); detailLoaded = true;
                await loadPayment(view);
            } catch { detailBody.textContent = "상세를 불러오지 못했습니다. 닫았다가 다시 열어 주세요."; }
            finally { detailLoading = false; }
        });
        if (record.status === "PENDING") {
            const pay = text("a", "venue-button", "결제 이어하기");
            pay.href = `/checkout/${encodeURIComponent(record.reserv_id)}`;
            side.append(pay);
        }
        if (record.status === "CONFIRMED") {
            const cancel = text("button", "ticket-cancel", "예매 취소·환불"); cancel.type = "button";
            const feedback = text("p", "ticket-note", ""); feedback.setAttribute("role", "status");
            cancel.addEventListener("click", async () => {
                if (cancelling || loading) return;
                if (!window.confirm("이 예매를 취소할까요? 처리되면 좌석이 해제되고 연결된 결제가 전액 환불됩니다. 취소 가능 여부는 서버에서 확인합니다.")) return;
                cancelling = true; cancel.disabled = true;
                get("ticket-refresh").disabled = true;
                feedback.textContent = "취소·환불 처리 중입니다. 다시 요청하지 말고 기다려 주세요.";
                try {
                    await requestApi(`/v1/reservations/${record.reserv_id}/cancel`, { method: "POST", headers: accountSession.headers(), cache: "no-store" });
                    cancelling = false;
                    const refreshed = await loadReservations();
                    status.textContent = refreshed ? "취소 요청이 처리되었습니다. 최신 예매·결제 상태를 확인해 주세요." : "취소 요청 후 목록 재조회에 실패했습니다. 최신 상태를 다시 조회해 주세요.";
                } catch (error) {
                    feedback.textContent = `${error.message || "처리 결과를 확인하지 못했습니다."} 최신 상태를 조회해 주세요.`;
                    // 통신 오류는 서버 처리 여부가 불명확하므로 같은 버튼으로 즉시 재요청하지 않는다.
                } finally { cancelling = false; get("ticket-refresh").disabled = loading; }
            });
            side.append(cancel, feedback);
        }
        const detail = text("a", "ticket-detail", "회차·좌석 보기 ↗");
        detail.href = `/performances/${encodeURIComponent(record.perf_id)}`;
        side.append(detail);
        item.append(text("span", "ticket-number", String(index + 1).padStart(2, "0")), main, side);
        list.append(item);
        return view;
    }

    async function loadPayment(view) {
        try {
            const payment = await requestApi(`/v1/reservations/${view.record.reserv_id}/payment`, { headers: accountSession.headers(), cache: "no-store" });
            view.paymentLine.textContent = `${paymentLabels[payment.status] || "결제 상태 확인 필요"} · ${Number(payment.amount).toLocaleString("ko-KR")}원 · ${payment.order_id}`;
            if (payment.paid_at) view.paymentLine.textContent += ` · 승인 ${formatDate(payment.paid_at)}`;
            if (payment.refunded_at) view.paymentLine.textContent += ` · 환불 ${formatDate(payment.refunded_at)}`;
        } catch (error) {
            view.paymentLine.textContent = error.status === 404 ? "결제 내역 없음" : "결제 상태 조회 실패 · 최신 상태를 다시 조회해 주세요.";
        }
    }

    async function enrich(view) {
        try {
            const round = await readOnce(`/v1/performances/${view.record.perf_id}`);
            view.date.textContent = `${round.round_number}회차 · ${formatDate(round.starts_at)}`;
            const show = await readOnce(`/v1/shows/${round.show_id}`);
            view.title.textContent = show.title;
            view.title.href = `/shows/${encodeURIComponent(show.show_id)}`;
            const venue = await readOnce(`/v1/venues?venues_id=${show.venues_id}`);
            view.venue.textContent = venue.name;
            if (view.record.perf_seat_id != null) {
                const seats = await readOnce(`/v1/performances/${view.record.perf_id}/seats`);
                const seat = seats.items.find(item => item.perf_seat_id === view.record.perf_seat_id);
                if (seat) view.seat.textContent = [seat.grade, seat.seat_seq].filter(Boolean).join(" · ");
            }
        } catch {
            if (view.date.textContent === "공연 일시를 확인하는 중…") view.date.textContent = "공연 일시 확인 필요";
            if (view.venue.textContent === "공연장 정보를 확인하는 중…") view.venue.textContent = "공연장 정보 확인 필요";
            view.note.textContent = "일부 공연 정보를 불러오지 못했어요. 예매 정보는 확인할 수 있어요.";
        }
        applyFilters();
    }

    async function loadReservations() {
        if (loading || cancelling) return;
        loading = true;
        get("ticket-refresh").disabled = true;
        list.replaceChildren();
        list.setAttribute("aria-busy", "true");
        views = [];
        details.clear();
        for (const id of ["ticket-total", "ticket-pending", "ticket-confirmed"]) get(id).textContent = "—";
        get("ticket-page-label").textContent = "";
        get("reservation-retry").hidden = true;
        get("reservation-login").hidden = true;
        get("ticket-empty").hidden = true;
        get("ticket-controls").hidden = true;
        get("ticket-refresh").hidden = true;
        status.textContent = "예매 내역을 불러오는 중…";
        try {
            const user = await accountSession.current();
            if (!user) {
                status.textContent = "로그인하면 나의 예매와 결제 내역을 확인할 수 있어요.";
                get("reservation-login").hidden = false;
                return;
            }
            if (user.role !== "BUYER") {
                status.textContent = "구매자 계정에서 나의 예매를 확인할 수 있어요.";
                return;
            }
            const data = await requestApi("/v1/reservations", { headers: accountSession.headers(), cache: "no-store" });
            const records = Array.isArray(data) ? data : data?.items;
            if (!Array.isArray(records)) throw new Error("예매 내역을 불러오지 못했습니다.");
            views = records.map(render);
            get("ticket-total").textContent = String(records.length).padStart(2, "0");
            get("ticket-pending").textContent = String(records.filter(item => item.status === "PENDING").length).padStart(2, "0");
            get("ticket-confirmed").textContent = String(records.filter(item => item.status === "CONFIRMED").length).padStart(2, "0");
            get("ticket-controls").hidden = false;
            get("ticket-refresh").hidden = false;
            get("ticket-updated").textContent = `마지막 조회 ${new Intl.DateTimeFormat("ko-KR", { timeStyle: "medium", timeZone: "Asia/Seoul" }).format(new Date())}`;
            applyFilters();
            await Promise.allSettled(views.flatMap(view => [enrich(view), loadPayment(view)]));
            return true;
        } catch (error) {
            status.textContent = error.message || "예매 내역을 불러오지 못했습니다.";
            if (error.status === 401) get("reservation-login").hidden = false;
            get("reservation-retry").hidden = false;
            return false;
        } finally {
            loading = false;
            get("ticket-refresh").disabled = false;
            list.setAttribute("aria-busy", "false");
        }
    }

    for (const button of filters) button.addEventListener("click", () => {
        selected = button.dataset.filter;
        for (const filter of filters) filter.setAttribute("aria-pressed", String(filter === button));
        applyFilters();
    });
    get("ticket-search").addEventListener("input", applyFilters);
    get("ticket-refresh").addEventListener("click", loadReservations);
    get("reservation-retry").addEventListener("click", loadReservations);
    return loadReservations();
});
