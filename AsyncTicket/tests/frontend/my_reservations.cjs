// 실행: node tests/frontend/my_reservations.cjs
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

class Element {
    constructor(tag = 'div') {
        this.tag = tag; this.children = []; this.handlers = {}; this.dataset = {};
        this.attributes = {}; this.textContent = ''; this.value = ''; this.hidden = true;
    }
    append(...children) { this.children.push(...children); }
    replaceChildren(...children) { this.children = children; }
    addEventListener(name, callback) { this.handlers[name] = callback; }
    setAttribute(name, value) { this.attributes[name] = value; }
}

function descendants(element) { return [element, ...element.children.flatMap(descendants)]; }
function fixture(options = {}) {
    const source = fs.readFileSync(path.join(__dirname, '../../src/asyncticket/static/venue/my_reservations.js'), 'utf8');
    const elements = new Map();
    const get = id => { if (!elements.has(id)) elements.set(id, new Element()); return elements.get(id); };
    const filters = ['ALL', 'PENDING', 'CONFIRMED', 'CLOSED'].map(filter => {
        const button = new Element('button'); button.dataset.filter = filter; return button;
    });
    const calls = [];
    const resumed = [];
    let ready;
    const records = options.records || ['PENDING', 'CONFIRMED', 'CANCELED', 'EXPIRED'].map((status, index) => ({
        reserv_id: 7 + index, perf_id: 1, perf_seat_id: 11, status,
        order_number: 'ORD-' + (7 + index), total_amount: '1000.00',
    }));
    vm.runInNewContext(source, {
        document: {
            getElementById: get, querySelectorAll: () => filters,
            createElement: tag => new Element(tag),
            addEventListener: (name, callback) => { ready = callback; },
        },
        accountSession: { current: async () => options.user === undefined ? { role: 'BUYER' } : options.user, headers: () => ({}) },
        requestApi: async url => {
            calls.push(url);
            if (url === '/v1/reservations') {
                if (options.listFailure) throw new Error('목록 조회 실패');
                return records;
            }
            if (options.detailFailure) throw new Error('상세 조회 실패');
            if (url === '/v1/performances/1') return { perf_id: 1, show_id: 2, round_number: 1, starts_at: '2026-11-17T10:00:00+09:00' };
            if (url === '/v1/shows/2') return { show_id: 2, venues_id: 3, title: '밤의 재즈' };
            if (url === '/v1/venues?venues_id=3') return { name: '서울 작은 극장' };
            if (url === '/v1/performances/1/seats') return { items: [{ perf_seat_id: 11, grade: 'R석', seat_seq: 'R01' }] };
            throw new Error('예상하지 못한 API: ' + url);
        },
        formatDate: () => '2026. 11. 17. 오전 10:00',
        bookingGateway: { resumePayment: async id => {
            resumed.push(id);
            if (options.onPayment) await options.onPayment();
        } },
    });
    return { ready: () => ready(), get, filters, calls, resumed };
}

async function run() {
    const passed = [];
    {
        const test = fixture(); await test.ready();
        const list = test.get('reservation-list');
        assert.equal(list.children.length, 4);
        assert.equal(test.get('ticket-total').textContent, '04');
        assert.equal(test.get('ticket-pending').textContent, '01');
        assert.equal(test.get('ticket-confirmed').textContent, '01');
        const nodes = descendants(list.children[0]);
        assert.equal(nodes.find(node => node.className === 'ticket-title').textContent, '밤의 재즈');
        assert.equal(nodes.find(node => node.className === 'ticket-seat').textContent, 'R석 · R01');
        assert.equal(nodes.find(node => node.className === 'ticket-price').textContent, '1,000원');
        for (const url of ['/v1/performances/1', '/v1/shows/2', '/v1/venues?venues_id=3', '/v1/performances/1/seats']) {
            assert.equal(test.calls.filter(call => call === url).length, 1);
        }
        assert.equal(descendants(list.children[1]).some(node => node.tag === 'button'), false);
        assert.equal(list.attributes['aria-busy'], 'false');
        passed.push('공연·일시·좌석·금액·상태 렌더링과 상세 조회 중복 방지');
        test.filters[3].handlers.click();
        assert.equal(list.children.filter(item => !item.hidden).length, 2);
        test.filters[0].handlers.click();
        test.get('ticket-search').value = 'ORD-8';
        test.get('ticket-search').handlers.input();
        assert.equal(list.children.filter(item => !item.hidden).length, 1);
        assert.equal(list.children[1].hidden, false);
        passed.push('취소·만료 상태 필터와 예매번호 검색');
    }
    {
        const test = fixture({ records: [] }); await test.ready();
        assert.equal(test.get('ticket-total').textContent, '00');
        assert.equal(test.get('ticket-empty').hidden, false);
        assert.match(test.get('reservation-status').textContent, /아직 예매/);
        passed.push('빈 예매 목록 안내');
    }
    for (const user of [null, { role: 'SELLER' }]) {
        const test = fixture({ user }); await test.ready();
        assert.equal(test.calls.length, 0);
        assert.equal(test.get('reservation-list').children.length, 0);
    }
    passed.push('미로그인·판매자에게 예매 조회 요청하지 않음');
    {
        const test = fixture({ detailFailure: true }); await test.ready();
        assert.equal(test.get('reservation-list').children.length, 4);
        assert.equal(descendants(test.get('reservation-list').children[0]).some(node => node.tag === 'button'), true);
        passed.push('공연 상세 조회 실패해도 예매·결제 버튼 유지');
    }
    {
        const test = fixture({ listFailure: true }); await test.ready();
        assert.equal(test.get('reservation-retry').hidden, false);
        assert.equal(test.get('reservation-list').attributes['aria-busy'], 'false');
        passed.push('예매 API 오류의 재시도 안내');
    }
    {
        const test = fixture({ onPayment: async () => { throw Object.assign(new Error('USER_CANCEL'), { code: 'USER_CANCEL' }); } });
        await test.ready();
        const nodes = descendants(test.get('reservation-list').children[0]);
        const button = nodes.find(node => node.tag === 'button');
        assert.equal(button.href, undefined);
        await button.handlers.click();
        assert.deepEqual(test.resumed, [7]);
        assert.equal(button.disabled, false);
        assert.match(nodes.find(node => node.attributes.role === 'status').textContent, /결제창을 닫았어요/);
        passed.push('결제 이어하기 직접 호출과 취소 후 버튼 복구');
    }
    {
        let entered, release;
        const opened = new Promise(resolve => { entered = resolve; });
        const done = new Promise(resolve => { release = resolve; });
        const records = [7, 8].map(reserv_id => ({ reserv_id, perf_id: 1, perf_seat_id: 11, total_amount: '1000.00', status: 'PENDING' }));
        const test = fixture({ records, onPayment: async () => { entered(); await done; } });
        await test.ready();
        const buttons = descendants(test.get('reservation-list')).filter(node => node.tag === 'button');
        const payment = buttons[0].handlers.click(); await opened;
        assert.equal(buttons.every(button => button.disabled), true);
        await buttons[1].handlers.click();
        assert.deepEqual(test.resumed, [7]);
        release(); await payment;
        assert.equal(buttons.every(button => !button.disabled), true);
        passed.push('결제창 진행 중 다른 예매의 결제 버튼도 잠금');
    }
    return passed;
}

module.exports = { run };
if (require.main === module) run().then(results => console.log(results.length + ' checks passed')).catch(error => { console.error(error); process.exitCode = 1; });
