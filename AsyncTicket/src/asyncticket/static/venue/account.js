const accountSession = (() => {
    const key = "asyncticket_access_token";
    const initialToken = sessionStorage.getItem(key);
    window.addEventListener("pageshow", event => {
        if (event.persisted && sessionStorage.getItem(key) !== initialToken) location.reload();
    });

    let checkedToken;
    let userRequest;

    function token() {
        return sessionStorage.getItem(key);
    }

    function headers() {
        return { Authorization: `Bearer ${token()}` };
    }

    async function current() {
        const activeToken = token();
        if (!activeToken) return null;
        if (activeToken !== checkedToken) {
            checkedToken = activeToken;
            userRequest = fetch("/v1/users/me", { headers: headers(), cache: "no-store" })
                .then(async response => {
                    if (response.status === 401) {
                        if (token() === activeToken) sessionStorage.removeItem(key);
                        return null;
                    }
                    if (!response.ok) throw new Error("로그인 정보를 확인하지 못했습니다.");
                    const { data } = await response.json();
                    return data;
                });
        }
        return userRequest;
    }

    async function logout() {
        const activeToken = token();
        if (activeToken) {
            let response;
            try {
                response = await fetch("/v1/auth/logout", {
                    method: "POST",
                    headers: { Authorization: `Bearer ${activeToken}` },
                });
            } catch {
                throw new Error("서버에 연결할 수 없습니다. 다시 시도해 주세요.");
            }
            if (!response.ok && response.status !== 401) {
                throw new Error("로그아웃에 실패했습니다. 다시 시도해 주세요.");
            }
        }
        sessionStorage.removeItem(key);
        window.location.replace("/login");
    }

    function canManage(user) {
        return ["ADMIN", "SELLER"].includes(user?.role);
    }

    return { current, headers, canManage, logout };
})();

for (const nav of document.querySelectorAll("[data-account-nav]")) {
    const guest = nav.querySelector("[data-account-guest]");
    const menu = nav.querySelector("[data-account-menu]");
    const summary = menu.querySelector("summary");

    accountSession.current().then(user => {
        if (!user) return;

        const manager = accountSession.canManage(user);
        summary.textContent = `${user.role === "ADMIN" ? "Admin" : user.name}님`;
        nav.querySelector("[data-buyer-link]").hidden = user.role !== "BUYER";
        for (const item of nav.querySelectorAll("[data-manager-link]")) item.hidden = !manager;
        for (const item of nav.querySelectorAll("[data-admin-link]")) item.hidden = user.role !== "ADMIN";
        guest.hidden = true;
        menu.hidden = false;
    }).catch(() => { /* 계정 조회가 실패하면 로그인 메뉴를 유지한다. */ });

    const logout = menu.querySelector("[data-account-logout]");
    const logoutStatus = menu.querySelector("[data-account-logout-status]");
    logout.addEventListener("click", async () => {
        logout.disabled = true;
        logoutStatus.hidden = true;
        try {
            await accountSession.logout();
        } catch (error) {
            logoutStatus.textContent = error.message;
            logoutStatus.hidden = false;
            logout.disabled = false;
        }
    });

    document.addEventListener("click", event => {
        if (!nav.contains(event.target)) menu.open = false;
    });
    menu.addEventListener("keydown", event => {
        if (event.key === "Escape" && menu.open) {
            menu.open = false;
            summary.focus();
        }
    });
}
