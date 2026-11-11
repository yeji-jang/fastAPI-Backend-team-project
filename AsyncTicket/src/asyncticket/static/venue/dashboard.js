// 고정된 화면 경로만 열고, ID는 정밀도 손실 없이 검증한다.
document.querySelector("#dashboard-direct").addEventListener("submit", event => {
    event.preventDefault();
    const form = event.currentTarget;
    const page = form.elements.page.value;
    const id = form.elements.record_id.value.trim();
    const status = document.querySelector("#dashboard-direct-status");
    if (!["venues", "shows", "performances", "checkout"].includes(page) ||
        !/^[1-9][0-9]{0,18}$/.test(id) || BigInt(id) > 9223372036854775807n) {
        status.textContent = "1부터 9223372036854775807 사이의 ID를 입력하세요.";
        return;
    }
    window.location.assign(`/${page}/${id}`);
});
