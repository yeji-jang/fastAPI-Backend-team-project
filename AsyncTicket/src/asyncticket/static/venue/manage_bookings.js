document.addEventListener("DOMContentLoaded", async () => {
    const get = id => document.getElementById(`booking-admin-${id}`);
    const form = get("search");
    const list = get("list");
    const status = get("status");
    const submit = form.querySelector('button[type="submit"]');
    const reservationLabels = { PENDING: "결제 대기", CONFIRMED: "예매 확정", CANCELED: "예매 취소", EXPIRED: "예매 만료" };
    // 예매 상태로 결제 결과를 추측하지 않고 결제 서비스의 응답만 표시한다.
    const paymentLabels = { READY: "결제 대기", DONE: "결제 완료", FAIL: "결제 실패", REFUND: "환불 완료" };
    let page = 1, total = 0, busy = false, authorized = false;
    let filters = { query: "", reservation_status: "", payment_status: "" };
    const size = 20;
    const money = value => value == null || value === "" || !Number.isFinite(Number(value)) ? "확인 필요" : `${Number(value).toLocaleString("ko-KR")}원`;
    function node(tag, content) {
        const el = document.createElement(tag);
        if (content != null) el.textContent = content;
        return el;
    }
    function controls() {
        submit.disabled = !authorized || !adminBookingApi.connected || busy;
        get("refresh").disabled = submit.disabled;
        get("prev").disabled = submit.disabled || page <= 1;
        get("next").disabled = submit.disabled || page * size >= total;
    }
    function deny(message, login = false) {
        authorized = false;
        list.replaceChildren();
        get("panel").hidden = true;
        get("login").hidden = !login;
        status.textContent = message;
        controls();
    }
    function handleAccess(error) {
        if (error.status === 401) { deny("로그인이 만료되었습니다. 다시 로그인해 주세요.", true); return true; }
        if (error.status === 403) { deny("관리자 조회 권한이 없습니다."); return true; }
        return false;
    }
    function render(record) {
        const row = node("details"); row.className = "admin-record";
        const heading = node("summary");
        const info = node("div");
        info.append(node("strong", record.show_title || "공연 정보 확인 필요"), node("p", `${record.order_number || "예매번호 미확인"} · ${record.seat_label || "좌석 연결 없음"}`));
        const states = node("div"); states.className = "admin-states";
        states.append(node("span", `${reservationLabels[record.reservation_status] || "예매 상태 확인 필요"} / ${record.payment_status == null ? "결제 내역 없음" : paymentLabels[record.payment_status] || "결제 상태 확인 필요"}`), node("small", `${money(record.total_amount)} · 상세 보기 ↓`));
        heading.append(info, states);
        const body = node("div"); body.className = "admin-record-body";
        row.append(heading, body);
        let loading = false, loaded = false;
        async function detail() {
            if (loading || loaded || !authorized) return;
            loading = true; body.replaceChildren(node("p", "상세 내역을 불러오는 중…"));
            try {
                const data = await adminBookingApi.detail(record.reserv_id);
                if (!data || data.reserv_id !== record.reserv_id) throw new Error("상세 응답의 예매번호를 확인해 주세요.");
                const dl = node("dl");
                for (const [label, value] of [
                    ["예매번호", data.order_number], ["공연", data.show_title], ["공연장", data.venue_name],
                    ["공연 일시", data.starts_at ? formatDate(data.starts_at) : null], ["좌석", data.seat_label || "좌석 연결 없음"],
                    ["예매 상태", reservationLabels[data.reservation_status]], ["예매 금액", money(data.total_amount)],
                    ["결제 상태", data.payment_status == null ? "결제 내역 없음" : paymentLabels[data.payment_status]],
                    ["결제 주문번호", data.payment_order_id], ["결제 금액", data.payment_amount == null ? "결제 내역 없음" : money(data.payment_amount)],
                ]) dl.append(node("dt", label), node("dd", value ?? "확인 필요"));
                body.replaceChildren(dl); loaded = true;
            } catch (error) {
                if (handleAccess(error)) return;
                const retry = node("button", "상세 다시 조회"); retry.className = "venue-button"; retry.type = "button";
                retry.addEventListener("click", detail);
                body.replaceChildren(node("p", error.message || "상세 내역을 불러오지 못했습니다."), retry);
            } finally { loading = false; }
        }
        row.addEventListener("toggle", () => { if (row.open) detail(); });
        return row;
    }
    async function load(nextPage) {
        if (busy || !authorized || !adminBookingApi.connected) return;
        busy = true; controls(); list.setAttribute("aria-busy", "true"); list.replaceChildren();
        status.textContent = "예매·결제 내역을 불러오는 중…";
        get("count").textContent = "조회 중";
        try {
            // 검색·필터·페이지·전체 건수는 관리자 백엔드가 처리한다.
            let data = await adminBookingApi.list({ page: nextPage, size, ...filters });
            const lastPage = Math.max(1, Math.ceil(data.total / size));
            if (nextPage > lastPage) {
                nextPage = lastPage;
                data = await adminBookingApi.list({ page: nextPage, size, ...filters });
            }
            page = nextPage; total = data.total;
            list.replaceChildren(...data.items.map(render));
            get("count").textContent = `전체 ${total.toLocaleString("ko-KR")}건`;
            get("updated").textContent = `마지막 조회 ${new Intl.DateTimeFormat("ko-KR", { timeStyle: "medium", timeZone: "Asia/Seoul" }).format(new Date())}`;
            get("page").textContent = `${page} / ${Math.max(1, Math.ceil(total / size))}`;
            status.textContent = data.items.length ? "" : "조건에 맞는 예매가 없습니다.";
        } catch (error) {
            total = 0; get("count").textContent = "조회 실패"; get("page").textContent = "—";
            if (!handleAccess(error)) status.textContent = error.message || "목록을 불러오지 못했습니다. 다시 조회해 주세요.";
        } finally { busy = false; list.setAttribute("aria-busy", "false"); controls(); }
    }
    form.addEventListener("submit", event => {
        event.preventDefault();
        if (busy) return;
        const fields = new FormData(form);
        filters = Object.fromEntries(["query", "reservation_status", "payment_status"].map(key => [key, String(fields.get(key) || "").trim()]));
        load(1);
    });
    get("refresh").addEventListener("click", () => load(page));
    get("prev").addEventListener("click", () => load(page - 1));
    get("next").addEventListener("click", () => load(page + 1));
    try {
        const user = await accountSession.current();
        if (!user) { deny("로그인 후 관리자 계정으로 이용해 주세요.", true); return; }
        if (user.role !== "ADMIN") { deny("관리자 계정에서 이용할 수 있습니다."); return; }
        authorized = true; get("panel").hidden = false;
        for (const input of form.querySelectorAll("input, select")) input.disabled = !adminBookingApi.connected;
        controls();
        if (!adminBookingApi.connected) {
            status.textContent = "";
            get("connection").textContent = "API 미연결 · 화면 준비가 완료되었습니다. 관리자 조회 API 연결 후 실제 예매·결제 내역이 표시됩니다.";
            list.replaceChildren(node("p", "실제 데이터는 아직 조회하지 않았습니다."));
            return;
        }
        get("connection").hidden = true;
        await load(1);
    } catch (error) {
        if (!handleAccess(error)) deny("관리 권한을 확인하지 못했습니다. 새로고침 후 다시 시도해 주세요.");
    }
}, { once: true });
