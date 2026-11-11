const venueData = (() => {
    const timezone = "Asia/Seoul";
    const date = new Intl.DateTimeFormat("ko-KR", { month: "2-digit", day: "2-digit", weekday: "short", timeZone: timezone });
    const time = new Intl.DateTimeFormat("ko-KR", { hour: "2-digit", minute: "2-digit", hour12: false, timeZone: timezone });

    async function read(path) {
        const response = await fetch(path, { cache: "no-store" });
        const body = await response.json().catch(() => null);
        if (!response.ok || body?.success !== true) {
            throw new Error(body?.message || "공연 API에 연결하지 못했습니다.");
        }
        return body.data;
    }

    async function listShows(performanceId) {
        let show;
        if (performanceId) {
            const round = await read(`/v1/performances/${performanceId}`);
            show = await read(`/v1/shows/${round.show_id}`);
        } else {
            const { items } = await read("/v1/shows?page=1&size=1");
            if (!items.length) return [];
            show = items[0];
        }
        const [{ items: performances }, venue] = await Promise.all([
            read(`/v1/shows/${show.show_id}/performances`),
            read(`/v1/venues?venues_id=${show.venues_id}`),
        ]);

        return [{
            id: show.show_id,
            title: show.title,
            poster: show.title.split(/\s+/).filter(Boolean),
            subtitle: show.performer || "",
            art: "jazz",
            genre: show.type || "LIVE",
            venue: venue.name,
            address: [venue.address, venue.address_detail].filter(Boolean).join(" · "),
            runtime: show.runtime,
            description: show.description || "공연 소개가 아직 등록되지 않았습니다.",
            performances: performances.map(round => {
                const startsAt = new Date(round.starts_at);
                return {
                    id: round.perf_id,
                    label: `${round.round_number}회차 · ${date.format(startsAt)}`,
                    time: time.format(startsAt),
                };
            }),
        }];
    }

    async function listSeats(performanceId) {
        const { items } = await read(`/v1/performances/${performanceId}/seats`);
        return items.map(seat => ({
            id: String(seat.perf_seat_id),
            label: seat.seat_seq || `좌석 ${seat.perf_seat_id}`,
            grade: seat.grade === "R석" ? "R" : seat.grade === "S석" ? "S" : "",
            price: seat.price,
            status: seat.status,
        }));
    }

    return { listShows, listSeats };
})();
