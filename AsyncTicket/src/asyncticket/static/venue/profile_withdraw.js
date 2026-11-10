document.addEventListener("DOMContentLoaded", () => {
    const form = document.getElementById("withdraw-form");
    const button = document.getElementById("withdraw-button");
    const status = document.getElementById("withdraw-status");
    let busy = false;
    form.addEventListener("submit", async event => {
        event.preventDefault();
        if (busy || !document.getElementById("withdraw-confirm").checked) return;
        const token = sessionStorage.getItem("asyncticket_access_token");
        if (!token) { location.replace("/login"); return; }
        if (!window.confirm("현재 로그인한 계정의 회원 탈퇴를 확정할까요?")) return;
        busy = true; button.disabled = true; status.textContent = "회원 탈퇴 요청 중…";
        let safeRetry = false;
        try {
            const response = await fetch("/v1/users/me", { method: "DELETE", headers: { Authorization: `Bearer ${token}` }, cache: "no-store" });
            if (response.status === 401) {
                sessionStorage.removeItem("asyncticket_access_token"); location.replace("/login"); return;
            }
            const body = await response.json().catch(() => null);
            safeRetry = !response.ok && response.status >= 400 && response.status < 500 && body?.success === false;
            if (!response.ok || body?.success !== true || body?.code !== "USER_WITHDRAWN") throw new Error(body?.message || "탈퇴 결과를 확인하지 못했습니다. 내 정보를 다시 조회해 주세요.");
            sessionStorage.removeItem("asyncticket_access_token");
            location.replace("/login?withdrawn=1");
        } catch (error) {
            status.textContent = error.message || "서버 연결을 확인한 뒤 내 정보를 다시 조회해 주세요.";
            // 명확한 서버 거절은 재시도할 수 있다. 통신·서버 오류는 계정 상태부터 다시 확인한다.
        } finally {
            if (safeRetry) { busy = false; button.disabled = false; }
        }
    });
}, { once: true });
