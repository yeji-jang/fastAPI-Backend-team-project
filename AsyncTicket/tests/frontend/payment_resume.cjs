// 실행: node tests/frontend/payment_resume.cjs
// 실제 토스 호출 없이 기존 예매 재사용과 실패 후 재시도를 확인한다.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function fixture(options = {}) {
    const source = fs.readFileSync(path.join(__dirname, '../../src/asyncticket/static/venue/booking.js'), 'utf8');
    const calls = [];
    const launches = [];
    const redirects = [];
    const memory = new Map();
    const windowEvents = {};
    let reloads = 0;
    let sdkFailures = options.sdkFailures || 0;
    const context = {
        accountSession: {
            current: async () => options.user === null ? null : { user_id: 3, role: 'BUYER' },
            headers: () => ({ Authorization: 'Bearer fake-test-token' }),
        },
        location: { pathname: '/me/reservations', search: '', origin: 'https://example.com', assign: url => redirects.push(url), reload: () => { reloads++; } },
        localStorage: { getItem: key => { if (options.blockStorage) throw new Error('blocked'); return memory.get(key); }, setItem: (key, value) => memory.set(key, value) },
        crypto: { randomUUID: () => '11111111-1111-4111-8111-111111111111' },
        window: { addEventListener: (name, callback) => { windowEvents[name] = callback; } },
        fetch: async (url, init = {}) => {
            calls.push({ url, method: init.method || 'GET', body: init.body });
            if (url === '/web/config') return { ok: true, json: async () => ({ toss_client_key: options.noKey ? null : 'test_ck_fake' }) };
            let data;
            if (url === '/v1/reservations/7') data = { reserv_id: 7, status: options.reservationStatus || 'PENDING', total_amount: options.reservationAmount || '1000.00' };
            else if (url === '/v1/payments') data = { pay_id: 8, order_id: 'reserv-7', amount: options.amount || '1000.00', status: options.paymentStatus || 'READY' };
            else throw new Error('예상하지 못한 요청: ' + url);
            return { ok: true, status: 200, json: async () => ({ success: true, data }) };
        },
        document: {
            createElement: () => ({ remove() {} }),
            head: {
                append: script => Promise.resolve().then(() => {
                    if (sdkFailures-- > 0) { script.onerror(); return; }
                    context.window.TossPayments = key => ({ payment: customer => ({ requestPayment: async payment => {
                        launches.push({ key, customer, payment });
                        if (options.onPayment) await options.onPayment();
                    } }) });
                    script.onload();
                }),
            },
        },
    };
    vm.createContext(context);
    vm.runInContext(source + '\nglobalThis.gateway = bookingGateway;', context);
    return { gateway: context.gateway, calls, launches, redirects, windowEvents, get reloads() { return reloads; } };
}

async function run() {
    const passed = [];
    {
        const test = fixture();
        await test.gateway.resumePayment(7);
        assert.equal(test.launches.length, 1);
        const payment = test.launches[0].payment;
        assert.equal(payment.orderId, 'reserv-7');
        assert.equal(payment.amount.value, 1000);
        assert.equal(payment.successUrl, 'https://example.com/payment/success');
        assert.equal(payment.failUrl, 'https://example.com/payment/fail');
        assert.equal(test.calls.filter(call => call.url === '/v1/reservations').length, 0);
        assert.deepEqual(JSON.parse(test.calls.find(call => call.url === '/v1/payments').body), { reserv_id: 7 });
        assert.equal(test.redirects.length, 0);
        passed.push('기존 예매·서버 주문번호·금액으로 결제창만 열기');
    }
    for (const status of ['CONFIRMED', 'CANCELED', 'EXPIRED']) {
        const test = fixture({ reservationStatus: status });
        await assert.rejects(test.gateway.resumePayment(7));
        assert.equal(test.launches.length, 0);
        assert.equal(test.calls.some(call => call.url === '/v1/payments'), false);
        passed.push(status + ' 예매는 결제 시작 차단');
    }
    {
        const test = fixture({ paymentStatus: 'DONE' });
        await assert.rejects(test.gateway.resumePayment(7));
        assert.equal(test.launches.length, 0);
        passed.push('이미 완료된 결제는 토스창 차단');
    }
    {
        const test = fixture({ noKey: true });
        await assert.rejects(test.gateway.resumePayment(7));
        assert.equal(test.calls.some(call => call.url === '/v1/payments'), false);
        passed.push('키가 없으면 결제 시작하지 않음');
    }
    {
        const test = fixture({ user: null });
        await assert.rejects(test.gateway.resumePayment(7));
        assert.equal(test.calls.length, 0);
        assert.equal(test.redirects.length, 1);
        passed.push('로그인 없으면 복귀 경로 포함 로그인 이동');
    }
    {
        const test = fixture({ sdkFailures: 1 });
        await assert.rejects(test.gateway.resumePayment(7));
        await test.gateway.resumePayment(7);
        assert.equal(test.launches.length, 1);
        assert.equal(test.calls.filter(call => call.url === '/v1/payments').length, 1);
        passed.push('SDK 실패 후 재시도 가능');
    }
    {
        let release;
        const finished = new Promise(resolve => { release = resolve; });
        let entered;
        const opened = new Promise(resolve => { entered = resolve; });
        const test = fixture({ onPayment: async () => { entered(); await finished; } });
        const first = test.gateway.resumePayment(7);
        await opened;
        await assert.rejects(test.gateway.resumePayment(7), /이미 결제창/);
        release();
        await first;
        assert.equal(test.launches.length, 1);
        passed.push('중복 클릭은 결제창 하나만 실행');
    }
    {
        const test = fixture({ amount: 'invalid' });
        await assert.rejects(test.gateway.resumePayment(7));
        assert.equal(test.launches.length, 0);
        passed.push('잘못된 금액 차단');
    }
    {
        const test = fixture({ reservationAmount: '2000.00' });
        await assert.rejects(test.gateway.resumePayment(7));
        assert.equal(test.launches.length, 0);
        passed.push('표시 예매 금액과 다른 결제 금액 차단');
    }
    {
        const test = fixture({ blockStorage: true });
        await test.gateway.resumePayment(7);
        assert.equal(test.launches.length, 1);
        passed.push('저장소 차단 환경에서도 결제창 실행');
    }
    {
        const test = fixture();
        test.windowEvents.pageshow({ persisted: false });
        assert.equal(test.reloads, 0);
        test.windowEvents.pageshow({ persisted: true });
        assert.equal(test.reloads, 1);
        passed.push('뒤로 복귀 시 오래된 결제 진행 상태 새로 읽기');
    }
    return passed;
}

module.exports = { run };
if (require.main === module) run().then(results => console.log(results.length + ' checks passed')).catch(error => { console.error(error); process.exitCode = 1; });
