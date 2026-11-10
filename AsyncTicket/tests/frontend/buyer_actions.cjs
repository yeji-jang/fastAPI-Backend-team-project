const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path'),assert=require('node:assert/strict');
const dir=path.join(__dirname,'../../src/asyncticket/static/venue');
async function paymentFixture(options={}) {
    const els={};const get=id=>els[id]??=( {hidden:true,disabled:false,textContent:'',handlers:{},addEventListener(e,f){this.handlers[e]=f;}} );
    let ready, reads=0, approvals=0, removed=false, current=options.status||'READY';
    const calls=[];
    const payment={order_id:'reserv-7',amount:'1000',status:current};
    vm.runInNewContext(fs.readFileSync(path.join(dir,'payment_result.js'),'utf8'),{
        document:{querySelector:()=>({dataset:{paymentResult:options.result||'success'}}),getElementById:get,addEventListener:(e,f)=>{ready=f;}},
        location:{search:options.query??'?paymentKey=fake&orderId=reserv-7&amount=1000'},history:{replaceState(){removed=true;}},URLSearchParams,
        accountSession:{current:async()=>options.noUser?null:{role:'BUYER'}},
        bookingGateway:{request:async(url,init)=>{
            calls.push({url,init});
            if(url.endsWith('/payment')){reads++;return {...payment,status:current,amount:options.amount||payment.amount};}
            if(url==='/v1/payments/approve'){approvals++;if(options.timeoutOnce&&approvals===1){current='DONE';throw new Error('network timeout');}current='DONE';return {...payment,status:'DONE'};}
            return {status:'CONFIRMED'};
        }},
    });
    await ready();return {get,calls,removed,reads:()=>reads,approvals:()=>approvals};
}
async function withdrawalFixture(options={}) {
    const els={};const get=id=>els[id]??=({checked:false,disabled:false,textContent:'',handlers:{},addEventListener(e,f){this.handlers[e]=f;}});
    let ready,calls=[],cleared=false,destination;
    vm.runInNewContext(fs.readFileSync(path.join(dir,'profile_withdraw.js'),'utf8'),{
        document:{getElementById:get,addEventListener:(e,f)=>{ready=f;}},window:{confirm:()=>options.confirm!==false},
        sessionStorage:{getItem:()=>options.noToken?null:'fake-token',removeItem(){cleared=true;}},location:{replace(url){destination=url;}},
        fetch:async(url,init)=>{calls.push({url,init});if(options.failure)throw new Error('network');if(options.refused)return {ok:false,status:409,json:async()=>({success:false,message:'서버 거절'})};return {ok:true,status:200,json:async()=>({success:true,code:'USER_WITHDRAWN'})};},
    });
    ready();get('withdraw-confirm').checked=options.checked!==false;
    return {get,calls,submit:()=>get('withdraw-form').handlers.submit({preventDefault(){}}),cleared:()=>cleared,destination:()=>destination};
}
async function run(){
    const passed=[];
    let p=await paymentFixture();assert.equal(p.approvals(),1);assert.equal(p.reads(),1);assert.match(p.get('payment-status').textContent,/확정/);assert.equal(p.removed,true);passed.push('콜백 자동 승인·서버 예매 확인·주소에서 키 제거');
    p=await paymentFixture({status:'DONE'});assert.equal(p.approvals(),0);passed.push('이미 완료된 결제 재승인 없음');
    p=await paymentFixture({amount:'2000'});assert.equal(p.approvals(),0);assert.equal(p.get('approve').hidden,true);passed.push('금액 불일치 승인 차단');
    p=await paymentFixture({timeoutOnce:true});assert.equal(p.approvals(),1);assert.equal(p.removed,false);await p.get('approve').handlers.click();assert.equal(p.approvals(),1);assert.equal(p.reads(),2);assert.match(p.get('payment-status').textContent,/확정/);passed.push('승인 통신 오류 뒤 재조회로 완료 확인, 추가 승인 없음');
    for(const options of [{noUser:true},{query:'?paymentKey=fake&orderId=wrong&amount=1000'},{result:'fail'}]){p=await paymentFixture(options);assert.equal(p.approvals(),0);}passed.push('미로그인·잘못된 콜백·실패 페이지 자동 승인 없음');
    for(const options of [{checked:false},{confirm:false}]){const w=await withdrawalFixture(options);await w.submit();assert.equal(w.calls.length,0);}passed.push('탈퇴 체크·최종 확인 없는 요청 차단');
    let w=await withdrawalFixture();await w.submit();await w.submit();assert.equal(w.calls.length,1);assert.equal(w.calls[0].init.method,'DELETE');assert.equal(w.cleared(),true);assert.equal(w.destination(),'/login?withdrawn=1');passed.push('탈퇴 성공 시 토큰 삭제·로그인 이동·중복 방지');
    w=await withdrawalFixture({failure:true});await w.submit();await w.submit();assert.equal(w.calls.length,1);assert.equal(w.cleared(),false);passed.push('탈퇴 통신 실패 시 토큰 유지·즉시 재요청 차단');
    w=await withdrawalFixture({refused:true});await w.submit();assert.equal(w.get('withdraw-button').disabled,false);await w.submit();assert.equal(w.calls.length,2);passed.push('탈퇴 서버 거절은 버튼 복구');
    return passed;
}
module.exports={run};
if(require.main===module)run().then(console.log).catch(e=>{console.error(e);process.exitCode=1;});
