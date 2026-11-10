const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const assert = require('node:assert/strict');
const dir = path.join(__dirname, '../../src/asyncticket/static/venue');
class El {
    constructor(tag='div') {this.tag=tag;this.children=[];this.hidden=false;this.disabled=false;this.textContent='';this.handlers={};this.attributes={};}
    append(...items) {this.children.push(...items);}
    replaceChildren(...items) {this.children=items;}
    addEventListener(event,fn) {this.handlers[event]=fn;}
    setAttribute(k,v) {this.attributes[k]=v;}
}
async function fixture({role='ADMIN',connected=false,error=null,records=[]}={}) {
    const els=new Map();const get=id=>{if(!els.has(id))els.set(id,new El());return els.get(id);};
    const button=new El('button');const input=new El('input');const select=new El('select');
    get('panel').hidden=true;get('login').hidden=true;
    get('search').querySelector=()=>button;get('search').querySelectorAll=()=>[input,select];
    let ready, count=0, args;
    const api={connected,list:async values=>{count++;args=values;if(error)throw error;return {items:records,total:records.length};},detail:async id=>({...records.find(r=>r.reserv_id===id),venue_name:'테스트 홀'})};
    vm.runInNewContext(fs.readFileSync(path.join(dir,'manage_bookings.js'),'utf8'),{
        document:{getElementById:id=>get(id.replace('booking-admin-','')),createElement:tag=>new El(tag),addEventListener:(e,f)=>{ready=f;}},
        accountSession:{current:async()=>role?{role}:null},adminBookingApi:api,formatDate:()=> '공연 일시',FormData:class{get(){return '';}}
    });
    await ready();return {get,button,input,select,api,count:()=>count,args:()=>args};
}
async function run(){
    const checks=[];
    let requests=[];const context={URLSearchParams,accountSession:{headers:()=>({Authorization:'test-only'})},requestApi:async(url,options)=>{requests.push({url,options});return {items:[],total:0};}};
    vm.createContext(context);vm.runInContext(fs.readFileSync(path.join(dir,'admin_booking_api.js'),'utf8')+'\nglobalThis.apiFactory=createAdminBookingApi;',context);
    let api=context.apiFactory();assert.equal(api.connected,false);await assert.rejects(api.list({page:1,size:20}),/연결/);assert.equal(requests.length,0);checks.push('미연결이면 실제 API 요청하지 않음');
    api=context.apiFactory({listUrl:'/test/admin',detailUrl:id=>'/test/admin/'+id});
    await api.list({page:2,size:20,query:'공연',reservation_status:'PENDING',payment_status:'READY'});
    let parsed=new URL(requests[0].url,'http://local');assert.equal(parsed.searchParams.get('page'),'2');assert.equal(parsed.searchParams.get('query'),'공연');assert.equal(parsed.searchParams.get('payment_status'),'READY');assert.equal(requests[0].options.cache,'no-store');
    await api.detail(2);assert.equal(requests[1].url,'/test/admin/2');checks.push('검색·필터·페이지와 인증 헤더를 관리자 API로 전달');
    for(const role of [null,'BUYER','SELLER']){const f=await fixture({role,connected:true});assert.equal(f.count(),0);assert.equal(f.get('panel').hidden,true);assert.equal(f.get('login').hidden,!role?false:true);}checks.push('비관리자는 목록 API 호출하지 않음');
    let f=await fixture();assert.equal(f.count(),0);assert.equal(f.get('panel').hidden,false);assert.match(f.get('connection').textContent,/API 미연결/);assert.equal(f.button.disabled,true);assert.equal(f.input.disabled,true);checks.push('관리자 미연결 안내와 검색 비활성화');
    f=await fixture({connected:true});assert.equal(f.count(),1);assert.match(f.get('status').textContent,/없습니다/);assert.equal(f.args().page,1);checks.push('빈 목록 표시');
    f=await fixture({connected:true,error:Object.assign(new Error('접근 거부'),{status:403})});assert.equal(f.get('panel').hidden,true);assert.equal(f.get('list').children.length,0);checks.push('403 응답 시 관리 화면과 데이터 숨김');
    f=await fixture({connected:true,error:new Error('연결 실패')});assert.match(f.get('status').textContent,/연결 실패/);assert.equal(f.button.disabled,false);checks.push('조회 실패 후 다시 조회 가능');
    f=await fixture({connected:true,records:[{reserv_id:2,show_title:'<script>test</script>',order_number:'ORD-2',reservation_status:'CONFIRMED',payment_status:'DONE',total_amount:'1000.00'}]});
    const row=f.get('list').children[0];assert.equal(row.children[0].children[0].children[0].textContent,'<script>test</script>');row.open=true;row.handlers.toggle();await new Promise(resolve=>setImmediate(resolve));assert.equal(row.children[1].children[0].tag,'dl');checks.push('목록 텍스트 표시와 상세 API 응답 표시');
    const uiSource=fs.readFileSync(path.join(dir,'manage_bookings.js'),'utf8');
    assert.equal(uiSource.includes('adminBookingApi.cancel'),false);
    assert.equal(typeof context.apiFactory().cancel,'undefined');
    checks.push('관리자 상태 변경·취소·환불 호출 없음');
    f=await fixture({connected:true});await f.get('refresh').handlers.click();assert.equal(f.count(),2);assert.match(f.get('updated').textContent,/마지막 조회/);checks.push('최신 상태 재조회 및 조회 시각 표시');
    for (const [payment_status,label] of [['READY','결제 대기'],['DONE','결제 완료'],['FAIL','결제 실패'],['REFUND','환불 완료'],[null,'결제 내역 없음']]) {
        const sample={reserv_id:2,show_title:'공연',reservation_status:'EXPIRED',payment_status,total_amount:'1000'};
        f=await fixture({connected:true,records:[sample]});
        const states=f.get('list').children[0].children[0].children[1].children[0].textContent;
        assert.equal(states,`예매 만료 / ${label}`);
    }
    checks.push('예매 상태와 무관하게 결제 서비스가 응답한 상태만 표시');
    return checks;
}
module.exports={run};
if(require.main===module)run().then(console.log).catch(e=>{console.error(e);process.exitCode=1;});
