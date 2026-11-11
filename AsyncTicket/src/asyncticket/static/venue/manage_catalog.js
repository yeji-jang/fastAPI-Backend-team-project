(() => {
    const legacySections = ["venue", "show", "performance", "seat"];
    if (location.pathname === "/manage" &&
        legacySections.some(section => location.hash === `#${section}-management`)) {
        location.replace(`/manage/edit${location.search}${location.hash}`);
        return;
    }

    const status = document.querySelector("#catalog-status");
    const money = amount => amount == null ? "가격 미정" : `${amount.toLocaleString("ko-KR")}원`;
    const seatStatus = {
        AVAILABLE: "선택 가능", RESERVED: "예약 중", OCCUPIED: "사용 중",
        UNPRICED: "가격 미정", UNKNOWN: "상태 미확인",
    };

    function element(tag, text, className) {
        const node = document.createElement(tag);
        if (text) node.textContent = text;
        if (className) node.className = className;
        return node;
    }

    function link(path, label) {
        const anchor = element("a", label);
        anchor.href = path;
        return anchor;
    }

    function record(title, meta, links, load) {
        const details = element("details", "", "catalog-record");
        const summary = element("summary");
        summary.append(element("span", title, "catalog-record-title"), element("span", meta, "catalog-record-meta"));
        const body = element("div", "", "catalog-record-body");
        const content = element("div");
        const actions = element("p", "", "catalog-actions");
        actions.append(...links);
        body.append(actions, content);
        details.append(summary, body);
        let loading = false;
        let loaded = false;

        details.addEventListener("toggle", async () => {
            if (!details.open || loaded || loading) return;
            loading = true;
            content.replaceChildren(element("p", "불러오는 중…"));
            try {
                content.replaceChildren(...await load());
                loaded = true;
            } catch (error) {
                content.replaceChildren(element("p", error.message));
            } finally {
                loading = false;
            }
        });
        return details;
    }

    async function loadSeatPanel(round) {
        const panel = element("div");
        const actions = element("div", "", "catalog-actions catalog-seat-actions");
        const button = element("button", "좌석 상태 새로고침");
        button.type = "button";
        const message = element("span");
        message.setAttribute("role", "status");
        actions.append(button, message);
        const content = element("div");
        panel.append(actions, content);

        let loading = false;
        let snapshot;
        let mapExpanded = false;

        async function refresh(manual = false) {
            if (loading) return;
            loading = true;
            button.setAttribute("aria-disabled", "true");
            message.textContent = "좌석 상태를 불러오는 중…";
            try {
                const { items } = await requestApi(`/v1/performances/${round.perf_id}/seats`, { cache: "no-store" });

                const next = JSON.stringify(items);
                if (next !== snapshot) {
                    const oldMap = content.querySelector(".catalog-seat-detail");
                    if (oldMap) mapExpanded = oldMap.open;
                    const focused = document.activeElement;
                    const focusInPanel = content.contains(focused);
                    const scrollLeft = content.querySelector(".catalog-table-wrap")?.scrollLeft || 0;
                    content.replaceChildren(...renderSeats(round, items));

                    const newMap = content.querySelector(".catalog-seat-detail");
                    if (newMap) newMap.open = mapExpanded;
                    const table = content.querySelector(".catalog-table-wrap");
                    if (table) table.scrollLeft = scrollLeft;
                    if (focusInPanel) {
                        const replacement = focused.tagName === "SUMMARY"
                            ? newMap?.querySelector("summary")
                            : [...content.querySelectorAll("a")].find(anchor => anchor.href === focused.href);
                        replacement?.focus({ preventScroll: true });
                    }
                    snapshot = next;
                }
                message.textContent = manual ? "좌석 상태를 새로 불러왔어요." : "";
            } catch {
                message.textContent = snapshot === undefined
                    ? "좌석 상태를 불러오지 못했어요. 새로고침 버튼으로 다시 시도해 주세요."
                    : "최신 좌석 상태를 불러오지 못했어요. 이전 상태를 표시하고 있습니다.";
            } finally {
                loading = false;
                button.removeAttribute("aria-disabled");
            }
        }

        await refresh();
        button.addEventListener("click", () => refresh(true));
        return [panel];
    }

    function renderSeats(round, items) {
        if (!items.length) return [element("p", "등록된 좌석이 없어요.")];

        const grades = new Map();
        for (const seat of items) {
            const available = seat.status === "AVAILABLE" && seat.price != null;
            if (!grades.has(seat.seat_id)) {
                grades.set(seat.seat_id, {
                    name: seat.grade || "등급 미정", price: seat.price, total: 0, available: 0,
                });
            }
            const grade = grades.get(seat.seat_id);
            grade.total++;
            if (available) grade.available++;
        }

        const table = element("table", "", "catalog-table");
        const header = table.createTHead().insertRow();
        for (const name of ["등급", "등록 좌석", "선택 가능", "가격", "관리"]) {
            const cell = element("th", name);
            cell.scope = "col";
            header.append(cell);
        }
        const body = table.createTBody();
        for (const [id, grade] of grades) {
            const row = body.insertRow();
            for (const value of [grade.name, `${grade.total}석`, `${grade.available}석`, money(grade.price)]) {
                row.insertCell().textContent = value;
            }
            if (id != null) {
                row.insertCell().append(link(
                    `/manage/edit?performance_id=${round.perf_id}&seat_id=${id}#seat-management`, "가격 수정",
                ));
            } else {
                row.insertCell();
            }
        }

        const wrap = element("div", "", "catalog-table-wrap");
        wrap.append(table);
        const detail = element("details", "", "catalog-seat-detail");
        detail.append(element("summary", `개별 좌석 ${items.length}석 보기`), renderSeatMap(items));
        return [wrap, detail];
    }

    function renderSeatMap(items) {
        const map = element("div", "", "catalog-seat-map");
        map.append(element("p", "무대 / STAGE", "catalog-stage"));
        const states = new Set(["AVAILABLE", "RESERVED", "OCCUPIED"]);
        const gradeOf = seat => seat.grade === "R석" ? "R" : seat.grade === "S석" ? "S" : "";

        for (const row of seatLayoutRows(items, gradeOf)) {
            const line = element("div", "", "seat-row");
            line.setAttribute("role", "group");
            line.setAttribute("aria-label", `${row.label}열`);
            const label = element("span", row.label, "row-label");
            label.setAttribute("aria-hidden", "true");
            line.append(label);

            for (const { seat, column } of row.seats) {
                let state = Object.hasOwn(seatStatus, seat.status) ? seat.status : "UNKNOWN";
                if (state === "AVAILABLE" && seat.price == null) state = "UNPRICED";
                states.add(state);
                const name = seat.seat_seq || `좌석 #${seat.perf_seat_id}`;
                const description = [seat.grade || "등급 미정", seatStatus[state], money(seat.price)].join(" · ");
                const cell = element("span", name, "catalog-seat catalog-seat-status");
                cell.dataset.state = state;
                cell.style.gridColumn = column;
                cell.title = `${name} · ${description}`;
                cell.append(element("span", ` · ${description}`, "catalog-seat-sr"));
                line.append(cell);
            }
            map.append(line);
        }

        const legend = element("ul", "", "catalog-seat-legend");
        legend.setAttribute("aria-label", "좌석 상태 범례");
        for (const state of states) {
            const key = element("span", "", "catalog-seat-status");
            key.dataset.state = state;
            key.setAttribute("aria-hidden", "true");
            const item = element("li");
            item.append(key, seatStatus[state]);
            legend.append(item);
        }
        map.append(legend, element("p", "참고 배치이며, 실제 객석 위치와 다를 수 있어요.", "catalog-seat-map-note"));
        return map;
    }

    async function renderRounds(show) {
        const { items } = await requestApi(`/v1/shows/${show.show_id}/performances`, { cache: "no-store" });
        if (!items.length) return [element("p", "등록된 회차가 없어요.")];

        return items.map(round => record(
            `${round.round_number}회차`, `${formatDate(round.starts_at)} · ${round.status}`,
            [
                link(`/manage/edit?performance_id=${round.perf_id}#performance-management`, "회차 수정"),
                link(`/manage/edit?for_performance=${round.perf_id}#seat-management`, "좌석 추가"),
            ],
            () => loadSeatPanel(round),
        ));
    }

    async function load() {
        try {
            const user = await accountSession.current();
            if (!accountSession.canManage(user)) {
                status.textContent = "판매자 또는 관리자 계정으로 로그인해 주세요.";
                document.querySelector("#catalog-login").hidden = false;
                return;
            }

            const requested = Number(new URLSearchParams(location.search).get("page"));
            const page = Number.isInteger(requested) && requested > 0 ? requested : 1;
            const { items, size, total } = await requestApi(`/v1/shows?page=${page}&size=20`, { cache: "no-store" });
            const container = document.querySelector("#catalog-records");
            for (const show of items) {
                container.append(record(show.title, [show.type, show.performer].filter(Boolean).join(" · "), [
                    link(`/manage/edit?show_id=${show.show_id}#show-management`, "공연 수정"),
                    link(`/manage/edit?for_show=${show.show_id}#performance-management`, "회차 추가"),
                ], () => renderRounds(show)));
            }
            document.querySelector("#catalog-count").textContent = `등록된 공연 ${total.toLocaleString("ko-KR")}개`;
            document.querySelector("#catalog-toolbar").hidden = false;
            const pages = document.querySelector("#catalog-pages");
            if (page > 1) pages.append(link(`?page=${page - 1}`, "이전"));
            if (page * size < total) pages.append(link(`?page=${page + 1}`, "다음"));
            status.textContent = items.length ? "" : "표시할 공연이 없어요.";
        } catch (error) {
            status.textContent = error.message;
        }
    }

    load();
})();
