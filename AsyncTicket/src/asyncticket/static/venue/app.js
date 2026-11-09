const get = id => document.getElementById(id);
const money = amount => amount == null ? "가격 미정" : `${amount.toLocaleString("ko-KR")}원`;
const gradeName = seat => seat.grade ? `${seat.grade}석` : "등급 미정";
const canSelectSeat = seat => seat.status === "AVAILABLE" && seat.price != null;
const browse = get("browse");
const booking = get("booking");
const openSeats = get("open-seats");
const openCheckout = get("open-checkout");
const summary = get("seat-summary");
let shows = [];
let show;
let selectedRound;
let selectedSeat;

function element(tag, className, text) {
    const item = document.createElement(tag);
    if (className) item.className = className;
    if (text) item.textContent = text;
    return item;
}

function posterTitle(target, words) {
    target.replaceChildren(...words.map(word => element("span", "", word)));
}

function renderCatalogue() {
    const index = get("index-list");
    const programme = get("programme-list");
    for (const [position, item] of shows.entries()) {
        const number = String(position + 1).padStart(2, "0");
        const entry = element("li");
        const shortcut = element("button", "index-button", `${number}  ${item.title} ↗`);
        shortcut.type = "button";
        shortcut.addEventListener("click", () => selectShow(item, true));
        entry.append(shortcut);
        index.append(entry);

        const card = element("button", "programme-card");
        card.type = "button";
        card.dataset.art = item.art;
        const artwork = element("span", "card-art");
        if (item.art === "jazz") {
            const photo = element("img");
            photo.src = get("feature-poster").querySelector("img").src;
            photo.alt = "";
            photo.loading = "lazy";
            artwork.append(photo);
        }
        const words = element("span", "card-words");
        words.setAttribute("aria-hidden", "true");
        posterTitle(words, item.poster);
        artwork.append(words);
        card.append(
            artwork,
            element("span", "card-meta", `${item.performances[0]?.label ?? "회차 미정"} / ${item.genre}`),
            element("strong", "", `${item.title} ↗`),
        );
        card.addEventListener("click", () => selectShow(item, true));
        programme.append(card);
    }
}

function selectShow(item, focus = false) {
    show = item;
    selectedRound = null;
    openSeats.disabled = true;
    get("feature-poster").dataset.art = show.art;
    get("feature-poster").querySelector("img").hidden = show.art !== "jazz";
    posterTitle(get("poster-title"), show.poster);
    get("poster-number").textContent = `${String(shows.indexOf(show) + 1).padStart(2, "0")} / ${String(shows.length).padStart(2, "0")}`;
    get("poster-date").textContent = show.performances.map(round => round.label).join(" — ");
    get("show-title").textContent = show.title;
    get("show-subtitle").textContent = show.subtitle;
    get("show-genre").textContent = show.genre;
    get("show-venue").textContent = show.venue;
    get("show-runtime").textContent = show.runtime == null ? "미정" : `${show.runtime}분`;
    get("venue-name").textContent = show.venue;
    get("venue-address").textContent = show.address;
    get("show-description").textContent = show.description;
    const rounds = get("round-list");
    rounds.replaceChildren();
    if (!show.performances.length) rounds.append(element("p", "", "등록된 회차가 없습니다."));

    for (const round of show.performances) {
        const label = element("label", "round-option");
        const input = element("input");
        input.type = "radio";
        input.name = "performance";
        input.value = round.id;
        input.addEventListener("change", () => {
            selectedRound = round;
            openSeats.disabled = false;
        });
        label.append(input, element("span", "", round.label), element("strong", "", round.time));
        rounds.append(label);
    }
    if (focus) get("show-title").focus();
}

function selectSeat(seat) {
    selectedSeat = seat;
    for (const button of get("seat-rows").querySelectorAll("button")) {
        button.setAttribute("aria-pressed", String(button.dataset.id === seat.id));
    }
    summary.textContent = `${seat.label} · ${gradeName(seat)} · ${money(seat.price)}`;
    openCheckout.disabled = false;
}

function renderSeatMap(seats) {
    const container = get("seat-rows");
    for (const row of seatLayoutRows(seats, seat => seat.grade)) {
        const line = element("div", "seat-row");
        line.append(element("span", "row-label", row.label));

        for (const { seat, column } of row.seats) {
            const button = element("button", "seat", seat.label);
            button.style.gridColumn = column;
            button.type = "button";
            button.dataset.id = seat.id;
            button.dataset.grade = seat.grade;
            button.disabled = !canSelectSeat(seat);
            button.setAttribute("aria-pressed", "false");
            button.setAttribute("aria-label", `${seat.label}, ${gradeName(seat)}, ${money(seat.price)}${button.disabled ? ", 선택 불가" : ""}`);
            button.addEventListener("click", () => selectSeat(seat));
            line.append(button);
        }
        container.append(line);
    }
}

openSeats.addEventListener("click", async () => {
    if (!selectedRound) return;
    const round = selectedRound;
    browse.hidden = true;
    booking.hidden = false;
    selectedSeat = null;
    openCheckout.disabled = true;
    summary.textContent = "배치도에서 좌석을 골라주세요.";
    get("map-venue").textContent = show.venue;
    get("booking-event").textContent = `${show.title} / ${round.label} ${round.time} / ${show.venue}`;
    get("seat-rows").replaceChildren();
    get("booking-capacity").textContent = "";
    const message = get("booking-message");
    message.hidden = false;
    message.textContent = "좌석 정보를 불러오는 중…";
    get("booking-title").focus();
    window.scrollTo(0, 0);

    try {
        const seats = await venueData.listSeats(round.id);
        if (selectedRound !== round || booking.hidden) return;
        if (seats.length) {
            renderSeatMap(seats);
            get("booking-capacity").textContent =
                `등록 좌석 ${seats.length}석 · 선택 가능 ${seats.filter(canSelectSeat).length}석`;
        }
        message.textContent = seats.length ? "" : "이 회차에 등록된 좌석이 없습니다.";
        message.hidden = seats.length > 0;
    } catch (error) {
        if (selectedRound === round && !booking.hidden) message.textContent = error.message;
    }
});

get("back-to-show").addEventListener("click", () => {
    booking.hidden = true;
    browse.hidden = false;
    openSeats.focus();
});

for (const link of document.querySelectorAll("[data-home], #programme-link, #venue-link")) {
    link.addEventListener("click", () => {
        booking.hidden = true;
        browse.hidden = false;
    });
}

openCheckout.addEventListener("click", async () => {
    if (!selectedSeat) return;

    const seat = selectedSeat;
    const message = get("booking-message");
    openCheckout.disabled = true;
    message.hidden = true;
    try {
        const user = await accountSession.current();
        if (booking.hidden || selectedSeat !== seat) return;
        if (!user) {
            window.location.assign("/login");
            return;
        }

        get("checkout-event").textContent = get("booking-event").textContent;
        get("checkout-seat").textContent = summary.textContent;
        const params = new URLSearchParams({ perf_id: selectedRound.id, perf_seat_id: seat.id });
        get("checkout-conditions").href = `/reservations?${params}`;
        const ready = typeof bookingGateway.startPayment === "function";
        get("submit-booking").disabled = !ready;
        get("submit-booking").textContent = ready ? "예매하고 결제로 이동" : "예매 준비 중";
        get("checkout-status").textContent = ready ? "" : "온라인 예매는 준비 중입니다.";
        get("checkout").showModal();
    } catch (error) {
        message.textContent = error.message;
        message.hidden = false;
    } finally {
        openCheckout.disabled = !selectedSeat;
    }
});

get("submit-booking").addEventListener("click", async event => {
    if (!selectedSeat || typeof bookingGateway.startPayment !== "function") return;

    const button = event.currentTarget;
    button.disabled = true;
    try {
        if (!await accountSession.current()) {
            window.location.assign("/login");
            return;
        }

        get("checkout-status").textContent = "예매를 확인하고 결제 페이지로 이동 중…";
        await bookingGateway.startPayment({
            showId: show.id,
            performanceId: selectedRound.id,
            performanceSeatId: selectedSeat.id,
        });
    } catch (error) {
        get("checkout-status").textContent = error.message;
        button.disabled = false;
    }
});

async function initialise() {
    try {
        const value = new URLSearchParams(location.search).get("performance_id");
        const performanceId = /^[1-9][0-9]{0,18}$/.test(value || "") ? value : null;
        shows = await venueData.listShows(performanceId);
        if (!shows.length) throw new Error("등록된 공연이 없습니다.");
        renderCatalogue();
        selectShow(shows[0]);
        if (performanceId) {
            const input = [...get("round-list").querySelectorAll("input")]
                .find(option => option.value === performanceId);
            if (input) {
                input.click();
                openSeats.click();
            }
        }
    } catch (error) {
        browse.hidden = true;
        const message = get("page-error");
        message.hidden = false;
        get("page-error-message").textContent = error.message;
    }
}

initialise();
