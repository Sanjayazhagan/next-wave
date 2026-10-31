const id=location.pathname.split('/').pop();
let invitation=location.hash.slice(1),bearer=null,frame=null,expiresAt=0; 
history.replaceState(null,'',location.pathname);
const $=s=>document.querySelector(s);
async function request(path,method='GET',body){const r=await fetch(`/assist-api/${id}/${path}`,{signal:AbortSignal.timeout(20000),method,cache:'no-store',headers:{...(body?{'Content-Type':'application/json'}:{}),...(bearer?{Authorization:`Bearer ${bearer}`}:{})},body:body?JSON.stringify(body):undefined});const d=await r.json();if(!r.ok)throw Error(d.detail||'Verification unavailable');return d}
$('#open').onclick=async()=>{const b=$('#open');b.disabled=true;try{const d=await request('claim','POST',{invitation});bearer=d.bearer;expiresAt=d.expires_at;$('#help').hidden=false;invitation='';await refreshFrame();$('#challenge').hidden=false;b.hidden=true;$('#status').textContent='Complete the displayed challenge yourself.'}catch(e){$('#status').textContent=e.message;b.disabled=false}};
$('#reply').onsubmit=async e=>{e.preventDefault();const b=e.target.querySelector('button');b.disabled=true;try{const d=await request('answer','POST',{answer:$('#answer').value});$('#answer').value='';if(d.ok){$('#challenge').hidden=true;$('#done').hidden=false;$('#status').textContent='Verification completed. The workflow can continue.';finishTask()}else{$('#status').textContent=d.task_state==='failed'?'Too many attempts. Request a new verification link.':'That answer was not accepted. Please try again.';if(d.task_state!=='failed')b.disabled=false}}catch(e){$('#answer').value='';$('#status').textContent=e.message;b.disabled=false}};

async function refreshFrame(){frame=await request('view');$('#screen').src='data:image/jpeg;base64,'+frame.screenshot_base64}
let controlling=false;
async function control(payload){if(controlling)return;controlling=true;try{const d=await request('control','POST',{...payload,frame_id:frame.frame_id});if(d.completed){$('#challenge').hidden=true;$('#done').hidden=false;$('#status').textContent='Verified in the live browser. Your workflow can continue.';finishTask()}else await refreshFrame()}catch(e){$('#status').textContent=e.message;try{await refreshFrame()}catch{}}finally{controlling=false}}
$('#screen').onclick=e=>{const r=e.currentTarget.getBoundingClientRect();control({kind:'click',x:(e.clientX-r.left)/r.width,y:(e.clientY-r.top)/r.height})};
$('#refresh').onclick=()=>refreshFrame().catch(e=>$('#status').textContent=e.message);
$('#type').onclick=()=>{const text=$('#remote-text').value;$('#remote-text').value='';control({kind:'text',text})};
$('#enter').onclick=()=>control({kind:'key',key:'Enter'});

$('#tab').onclick=()=>control({kind:'key',key:'Tab'});
$('#backspace').onclick=()=>control({kind:'key',key:'Backspace'});
$('#help').onclick=async()=>{try{const d=await request('help','POST',{});$('#status').textContent=d.message}catch(e){$('#status').textContent=e.message}};
fetch('/assist-config',{cache:'no-store'}).then(r=>r.ok?r.json():Promise.reject()).then(d=>{if(d.return_url){$('#return').href=d.return_url;$('#return').hidden=false}}).catch(()=>{});
setInterval(()=>{if(!bearer||!expiresAt)return;const remaining=Math.max(0,Math.ceil(expiresAt-Date.now()/1000));$('#expiry').textContent=remaining?'Verification access expires in '+remaining+' seconds':'Access expired. Return to your conversation to request a fresh link.';if(!remaining){bearer=null;$('#challenge').hidden=true;$('#help').hidden=true}},1000);
window.addEventListener('online',()=>{if(bearer)refreshFrame().then(()=>$('#status').textContent='Reconnected to the live challenge.').catch(e=>$('#status').textContent=e.message)});
window.addEventListener('offline',()=>$('#status').textContent='Connection lost. Your browser task is paused; reconnect before continuing.');

function finishTask(){bearer=null;expiresAt=0;$('#help').hidden=true;$('#expiry').hidden=true}
