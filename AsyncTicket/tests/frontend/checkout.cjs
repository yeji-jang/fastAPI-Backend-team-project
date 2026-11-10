const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../../src/asyncticket/static/venue/checkout.js'), 'utf8');
async function setup(options = {}) {
    const elements = new Map();
    function get(id) {
        if (!elements.has(id)) elements.set(id, {textContent: '', hidden: id === 'checkout-summary', disabled: true, handlers: {}, addEventListener(e,f) { this.handlers[e]=f; }});
        return elements.get(id);
    }
    for (const id of ['checkout-date','checkout-venue','checkout-seat']) get(id).textContent='확인 중…';
    let ready, calls=[];
    vm.runInNewContext(source, {
        document: {addEventListener(e,f) { ready=f; },getElementById:get,querySelector() {return {dataset:{reservationId:'2'}};}},
        formatDate: ()=>'2026. 11. 17. 오후 7:00',
        bookingGateway: {
            buyer: async()=>{ if(options.noUser) throw new Error('로그인 필요'); },
            request: async()=>({reserv_id:2,perf_id:1,perf_seat_id:11,status:options.status||'PENDING',order_number:'ORD-2',total_amount:'500.00'}),
            config: async()=>{if(options.configFailure) throw new Error('결제 설정 오류');return {toss_client_key:options.noKey?null:'fake'};},
            resumePayment: async id=>{calls.push(id);if(options.cancel) throw {code:'USER_CANCEL'};},
        },
        requestApi: async url=>{
            if(options.detailFailure) throw new Error('상세 조회 실패');
            if(url.includes('/seats')) return {items:[{perf_seat_id:11,grade:'S석',seat_seq:'S06'}]};
            if(url.includes('/performances/')) return {show_id:1,starts_at:'2026-11-17',round_number:1};
            if(url.includes('/shows/')) return {title:'Blue Hour',performer:'콰르텟',type:'CONCERT',venues_id:2};
            return {name:'ASYNC ROOM'};
        },
    });
    await ready();return {get,calls};
}
async function run() {
    let t=await setup();assert.equal(t.get('checkout-title').textContent,'Blue Hour');assert.equal(t.get('poster-title').textContent,'Blue Hour');assert.equal(t.get('checkout-seat').textContent,'S석 · S06');assert.equal(t.get('checkout-amount').textContent,'500원');assert.equal(t.get('pay').disabled,false);
    await t.get('pay').handlers.click();assert.equal(t.calls[0],'2');
    for(const status of ['CONFIRMED','CANCELED','EXPIRED']) {t=await setup({status});assert.equal(t.get('pay').disabled,true);}
    t=await setup({noKey:true});assert.equal(t.get('pay').disabled,true);
    t=await setup({detailFailure:true});assert.equal(t.get('pay').disabled,false);assert.match(t.get('checkout-detail-status').textContent,/일부/);
    t=await setup({configFailure:true});assert.equal(t.get('checkout-title').textContent,'Blue Hour');assert.equal(t.get('pay').disabled,true);
    t=await setup({cancel:true});await t.get('pay').handlers.click();assert.match(t.get('checkout-status').textContent,/닫았어요/);assert.equal(t.get('pay').disabled,false);
    t=await setup({noUser:true});assert.equal(t.get('pay').disabled,true);assert.equal(t.get('checkout-summary').hidden,true);
    return 'Checkout: 공연·포스터·좌석 표시 / 기존 결제 호출 / 예매 상태·키 차단 / 상세·설정 오류 / 취소·로그인 검사 통과';
}
module.exports={run};
if(require.main===module) run().then(console.log).catch(e=>{console.error(e);process.exitCode=1;});
