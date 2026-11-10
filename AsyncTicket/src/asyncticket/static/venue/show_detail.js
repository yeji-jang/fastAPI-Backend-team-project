(() => {
    const root = document.querySelector('[data-show-id]');
    const get = id => document.getElementById(id);
    const url = `/v1/shows/${root.dataset.showId}`;
    const day = new Intl.DateTimeFormat('ko-KR', { year: 'numeric', month: 'long', day: 'numeric', weekday: 'short', timeZone: 'Asia/Seoul' });
    const text = (id, value) => { get(id).textContent = value; };
    const time = value => formatDate(value);
    let currentShow;
    let roundsPending = false;

    function selectRound(round) {
        text('selected-round-title', `${round.round_number}회차 · ${day.format(new Date(round.starts_at))}`);
        text('selected-round-time', `${time(round.starts_at)} ~ ${time(round.ends_at)}`);
        text('selected-booking-time', `${time(round.booking_opens_at)} ~ ${time(round.booking_closes_at)}`);
        text('selected-round-policy', `1인당 최대 ${round.max_tickets_per_user}매 · 운영 상태 ${round.status}`);
        get('show-seat-link').href = `/?performance_id=${round.perf_id}`;
        get('show-round-link').href = `/performances/${round.perf_id}`;
        get('selected-performance').hidden = false;
    }

    async function loadRounds() {
        if (roundsPending) return;
        roundsPending = true;
        text('performance-status', '회차를 불러오는 중…');
        get('rounds-retry').hidden = true;
        get('round-options').hidden = true;
        get('selected-performance').hidden = true;
        get('performance-list').replaceChildren();
        try {
            const { items } = await requestApi(`${url}/performances`);
            const rounds = [...items].sort((a, b) => new Date(a.starts_at) - new Date(b.starts_at));
            for (const [index, round] of rounds.entries()) {
                const label = document.createElement('label');
                label.className = 'show-round-option';
                const choice = document.createElement('input');
                choice.type = 'radio';
                choice.name = 'show-performance';
                choice.value = round.perf_id;
                choice.checked = index === 0;
                const copy = document.createElement('span');
                const title = document.createElement('strong');
                title.textContent = `${round.round_number}회차 · ${time(round.starts_at)}`;
                const period = document.createElement('small');
                const now = Date.now();
                const opens = new Date(round.booking_opens_at).getTime();
                const closes = new Date(round.booking_closes_at).getTime();
                const state = now < opens ? '예매 시작 전' : now >= closes ? '예매 기간 종료' : '예매 기간 내';
                period.textContent = `${state} · 좌석 조회 가능`;
                copy.append(title, period);
                label.append(choice, copy);
                choice.addEventListener('change', () => selectRound(round));
                get('performance-list').append(label);
            }
            get('round-options').hidden = !rounds.length;
            text('performance-status', rounds.length ? '' : '등록된 회차가 없습니다. 공연 일정이 등록되면 여기서 확인할 수 있어요.');
            text('show-date-range', rounds.length ? (rounds.length === 1 ? day.format(new Date(rounds[0].starts_at)) : `${day.format(new Date(rounds[0].starts_at))} ~ ${day.format(new Date(rounds.at(-1).starts_at))}`) : '일정 미등록');
            if (rounds.length) selectRound(rounds[0]);
        } catch (error) {
            text('performance-status', error.message);
            text('show-date-range', '일정을 불러오지 못했습니다.');
            get('rounds-retry').hidden = false;
        } finally {
            roundsPending = false;
        }
    }

    async function loadVenue(show) {
        const link = get('show-venue');
        link.href = `/venues/${show.venues_id}`;
        text('show-venue', '공연장 정보 보기 ↗');
        text('show-venue-name', '공연장 정보');
        text('show-venue-address', '주소를 불러오는 중…');
        get('show-venue-details').href = link.href;
        try {
            const venue = await requestApi(`/v1/venues?venues_id=${show.venues_id}`);
            if (currentShow !== show) return;
            text('show-venue', `${venue.name} ↗`);
            text('show-venue-name', venue.name);
            text('show-venue-address', [venue.address, venue.address_detail, venue.post_no].filter(Boolean).join(' · ') || '주소 미등록');
        } catch (error) {
            if (currentShow === show) text('show-venue-address', '주소를 불러오지 못했습니다. 공연장 상세에서 다시 확인해주세요.');
        }
    }

    async function loadShow() {
        get('show-retry').hidden = true;
        text('show-status', '공연을 불러오는 중…');
        try {
            const show = await requestApi(url);
            currentShow = show;
            text('show-title', show.title);
            document.title = `${show.title} | AsyncTicket`;
            text('show-type', show.type || '공연');
            text('show-performer-lead', show.performer || '함께 만나는 라이브 무대');
            text('show-performer', show.performer || '미등록');
            text('show-runtime', show.runtime == null ? '미등록' : `${show.runtime}분`);
            text('show-description', show.description || '공연 소개가 아직 등록되지 않았습니다. 일정과 공연장 정보를 먼저 확인해보세요.');
            get('show-content').hidden = false;
            text('show-status', '');
            await Promise.all([loadVenue(show), loadRounds()]);
        } catch (error) {
            text('show-status', error.status === 404 ? '공연을 찾을 수 없습니다. 공연 목록에서 다른 공연을 선택해주세요.' : error.message);
            get('show-retry').hidden = error.status === 404;
        }
    }
    get('show-retry').addEventListener('click', loadShow);
    get('rounds-retry').addEventListener('click', loadRounds);
    loadShow();
})();
