document.addEventListener("DOMContentLoaded", () => {
    const get = id => document.getElementById(id);
    const status = get("reservation-status");
    const list = get("reservation-list");
    const filters = [...document.querySelectorAll(".ticket-filter")];
    const labels = { PENDING: "결제 대기", CONFIRMED: "예매 확정", CANCELED: "예매 취소", EXPIRED: "예매 만료" };
    let selected = "ALL";
    let views = [];
    let loading = false;
    const details = new Map();

    function text(tag, className, value) {
        const node = document.createElement(tag);
        node.className = className;
        node.textContent = value;
        return node;
    }

    function readOnce(url) {
        if (!details.has(url)) details.set(url, requestApi(url, { cache: "no-store" }));
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
        const view = { item, record, title, date, venue, seat, note };
        if (record.status === "PENDING") {
            const pay = text("a", "venue-button", "결제 이어하기");
            pay.href = `/checkout/${encodeURIComponent(record.reserv_id)}`;
            side.append(pay);
        }
        const detail = text("a", "ticket-detail", "회차·좌석 보기 ↗");
        detail.href = `/performances/${encodeURIComponent(record.perf_id)}`;
        side.append(detail);
        item.append(text("span", "ticket-number", String(index + 1).padStart(2, "0")), main, side);
        list.append(item);
        return view;
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
        if (loading) return;
        loading = true;
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
            applyFilters();
            await Promise.allSettled(views.map(enrich));
        } catch (error) {
            status.textContent = error.message || "예매 내역을 불러오지 못했습니다.";
            get("reservation-retry").hidden = false;
        } finally {
            loading = false;
            list.setAttribute("aria-busy", "false");
        }
    }

    for (const button of filters) button.addEventListener("click", () => {
        selected = button.dataset.filter;
        for (const filter of filters) filter.setAttribute("aria-pressed", String(filter === button));
        applyFilters();
    });
    get("ticket-search").addEventListener("input", applyFilters);
    get("reservation-retry").addEventListener("click", loadReservations);
    return loadReservations();
});
