// 관리자 API 계약 확정 후 이 파일의 주소·응답 매핑만 연결한다.
// 구매자 본인 조회 API를 관리자 전체 조회에 사용하지 않는다.
function createAdminBookingApi({ listUrl = null, detailUrl = null } = {}) {
    async function read(url) {
        return requestApi(url, { headers: accountSession.headers(), cache: "no-store" });
    }
    return {
        connected: Boolean(listUrl && detailUrl),
        async list({ page, size, query, reservation_status, payment_status }) {
            if (!listUrl) throw new Error("관리자 예매·결제 조회 API가 아직 연결되지 않았습니다.");
            const params = new URLSearchParams({ page, size });
            for (const [key, value] of Object.entries({ query, reservation_status, payment_status })) {
                if (value) params.set(key, value);
            }
            const data = await read(`${listUrl}${listUrl.includes("?") ? "&" : "?"}${params}`);
            if (!Array.isArray(data?.items) || !Number.isSafeInteger(data.total) || data.total < 0) {
                throw new Error("관리자 목록 응답 형식을 확인해 주세요.");
            }
            return data;
        },
        async detail(reservationId) {
            if (!detailUrl) throw new Error("관리자 상세 조회 API가 아직 연결되지 않았습니다.");
            return read(detailUrl(reservationId));
        },
    };
}
const adminBookingApi = createAdminBookingApi();
