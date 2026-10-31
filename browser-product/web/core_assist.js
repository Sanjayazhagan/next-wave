'use strict';
const id=location.pathname.split('/')[2];
let token=decodeURIComponent(location.hash.slice(1)),expires=0,viewport={width:1180,height:760},challengeBoxes=[];
history.replaceState(null,'',location.pathname);
const $=sel=>document.querySelector(sel);
async function api(path,method='GET',body){
  if(!token)throw Error('Verification link missing or expired');
  const response=await fetch(`/core-assist/${encodeURIComponent(id)}/${path}`,{
    method,cache:'no-store',credentials:'omit',headers:{'X-Assist-Token':token,...(body?{'Content-Type':'application/json'}:{})},
    body:body?JSON.stringify(body):undefined,signal:AbortSignal.timeout(20000)
  });
  const data=await response.json();
  if(!response.ok)throw Error(data.detail||`Request failed (${response.status})`);
  return data;
}
function feedback(message){$('#message').textContent=String(message)}
function append(tag,parent,text,cls){const el=document.createElement(tag);if(cls)el.className=cls;if(text!=null)el.textContent=text;parent.appendChild(el);return el}
let busy=false;
async function control(payload){if(busy)return;busy=true;try{await api('control','POST',payload);feedback('Browser updated. Check the result and continue if needed.');await refresh()}catch(err){feedback(err.message)}finally{busy=false}}
async function refresh(){
  const data=await api('view');expires=data.expires_at||0;viewport=data.viewport||viewport;challengeBoxes=data.challenge_boxes||[];
  $('#screen').src='data:image/jpeg;base64,'+data.screenshot_base64;
  $('#url').textContent=data.url;
  const wrap=$('#controls');wrap.replaceChildren();
  if(!data.controls.length)append('p',wrap,'No editable OTP/CAPTCHA controls detected. If a challenge is inside a framed widget, click the image inside that widget.');
  for(const item of data.controls){
    const row=append('div',wrap,null,'control');
    if(item.category==='human_input'){
      const label=append('label',row,item.label||'Verification code');
      const inp=append('input',row);inp.autocomplete='one-time-code';inp.inputMode='text';inp.maxLength=100;inp.type=item.type==='password'?'password':'text';
      const btn=append('button',row,'Enter verification value');btn.type='button';
      btn.onclick=()=>{const value=inp.value;inp.value='';control({kind:'fill',target_ref:item.ref,value})};
      label.htmlFor=inp.id='auth-'+item.ref.replace(/[^a-zA-Z0-9-]/g,'');
    } else {
      append('span',row,item.label||item.category);
      const btn=append('button',row,`Click ${item.label||item.category}`);btn.type='button';
      btn.onclick=()=>control({kind:'click',target_ref:item.ref});
    }
  }
  $('#status').textContent='Human assistance active';
}
$('#screen').onclick=async event=>{
  const b=event.currentTarget.getBoundingClientRect(),x=(event.clientX-b.left)/b.width*viewport.width,y=(event.clientY-b.top)/b.height*viewport.height;
  if(!challengeBoxes.some(r=>x>=r.x&&y>=r.y&&x<=r.x+r.width&&y<=r.y+r.height)){
    feedback('Click only within the detected CAPTCHA frame, or use a verification control below.');return;
  }
  await control({kind:'challenge_click',x,y});
};
$('#refresh').onclick=()=>refresh().catch(e=>feedback(e.message));
$('#done').onclick=async()=>{try{
  const res=await api('complete','POST',{});
  $('#status').textContent='Handed back to agent';$('#done').disabled=true;token='';
  feedback(res.still_waiting_human?'Control returned. The site still displays a verification signal; the agent must inspect before proceeding.':'Control returned. The agent must verify the result before continuing.');
}catch(err){feedback(err.message)}};
setInterval(()=>{if(!expires)return;const remaining=Math.max(0,Math.ceil(expires-Date.now()/1000));$('#expiry').textContent=`Link expires in ${remaining} seconds`;if(!remaining){token='';$('#done').disabled=true;feedback('Link expired. Request a new invitation from the agent.')}},1000);
refresh().catch(e=>{feedback(e.message);$('#status').textContent='Unable to open verification'});
