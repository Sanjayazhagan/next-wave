'use strict';
const id=location.pathname.split('/')[2];
let token=decodeURIComponent(location.hash.slice(1)),expires=0,viewport={width:1180,height:760},challengeBoxes=[];
history.replaceState(null,'',location.pathname);
const $=sel=>document.querySelector(sel);
async function api(path,method='GET',body){
  if(!token)throw Error('Verification link missing or expired');
  const response=await fetch(`/core-assist/${encodeURIComponent(id)}/${path}`,{
    method,cache:'no-store',credentials:'omit',headers:{'X-Assist-Token':token,...(body?{'Content-Type':'application/json'}:{})},
    body:body?JSON.stringify(body):undefined,signal:AbortSignal.timeout(taskReason==='submit'?60000:20000)
  });
  const data=await response.json();
  if(!response.ok)throw Error(data.detail||`Request failed (${response.status})`);
  return data;
}
function feedback(message){$('#message').textContent=String(message)}
function append(tag,parent,text,cls){const el=document.createElement(tag);if(cls)el.className=cls;if(text!=null)el.textContent=text;parent.appendChild(el);return el}
let busy=false,observationId=null,taskReason='other',capabilityEnded=false,viewGeneration=0;
function endCapability(){
  capabilityEnded=true;viewGeneration++;token='';expires=0;
  $('#expiry').textContent='';$('#expiry').hidden=true;
  $('#done').disabled=true;$('#refresh').disabled=true;
}
function closeSubmitPanels(){
  $('#screen-wrap').closest('section').hidden=true;
  $('#controls').closest('section').hidden=true;
}
function submissionOutcome(result){
  if(result.confirmed_by_portal)return {status:'Submission confirmed',message:result.receipt_number?`Portal confirmed submission. Receipt: ${result.receipt_number}`:'Portal confirmed submission. No receipt number was provided.'};
  if(result.state==='review_changed')return {status:'New review required',message:'The reviewed page changed. Ask the bot for a new review before submitting.'};
  if(['rejected','expired','cancelled'].includes(result.state))return {status:'Submission not completed',message:'This submit task ended without portal confirmation. Ask the bot to check the task before proceeding.'};
  return {status:'Submission outcome uncertain',message:'The portal has not confirmed this submission. Do not click again; ask the bot to check the outcome.'};
}
async function control(payload){
  if(busy)return;busy=true;
  const submitting=taskReason==='submit';
  if(submitting){viewGeneration++;$('#refresh').disabled=true;$('#controls').querySelectorAll('button,input').forEach(el=>el.disabled=true);}
  try{
    const result=await api('control','POST',{...payload,observation_id:observationId});
    if(submitting){
      endCapability();closeSubmitPanels();$('#controls').replaceChildren();
      const outcome=submissionOutcome(result);$('#status').textContent=outcome.status;feedback(outcome.message);
      if(result.page_text)append('p',$('#controls'),result.page_text);
      return;
    }
    feedback('Browser updated. Check the result and continue if needed.');await refresh();
  }catch(err){
    feedback(submitting?err.message+' This submit link cannot be retried. Ask the bot to check the task status.':err.message);
    if(submitting){endCapability();closeSubmitPanels();$('#controls').replaceChildren();$('#status').textContent='Check submission with the bot';}
  }finally{busy=false}
}
async function refresh(){
  if(capabilityEnded||(busy&&taskReason==='submit'))return;
  const generation=++viewGeneration;
  let data;
  try{data=await api('view')}catch(err){if(capabilityEnded||generation!==viewGeneration)return;throw err}
  if(capabilityEnded||generation!==viewGeneration)return;
  $('#expiry').hidden=false;observationId=data.observation_id;expires=data.expires_at||0;taskReason=data.reason||'other';$('#done').hidden=taskReason==='submit';if(taskReason==='submit'){$('#task-title').textContent='Review and submit your application';$('#task-tip').textContent='Never share this link. Only the reviewed Submit button is available. You may click it once; if the outcome is unclear, ask the bot to check it.';}viewport=data.viewport||viewport;challengeBoxes=data.challenge_boxes||[];
  if(data.screenshot_base64){$('#screen').src='data:image/jpeg;base64,'+data.screenshot_base64;$('#screen').hidden=false}
  else{$('#screen').hidden=true;feedback('Preview is temporarily unavailable. Refresh before clicking a visual challenge.')}
  $('#url').textContent=data.url;
  const wrap=$('#controls');wrap.replaceChildren();
  if(!data.controls.length)append('p',wrap,'No editable OTP/CAPTCHA controls detected. If a challenge is inside a framed widget, click the image inside that widget.');
  for(const item of data.controls){
    const row=append('div',wrap,null,'control');
    if(item.category==='human_input'){
      const label=append('label',row,item.label||'Verification code');
      const inp=append('input',row);inp.autocomplete=item.type==='password'?'current-password':(/otp|one.time|verification code/i.test(item.label)?'one-time-code':'off');inp.inputMode=item.type==='number'?'numeric':'text';inp.maxLength=100;inp.type=item.type==='password'?'password':'text';
      const btn=append('button',row,'Enter verification value');btn.type='button';
      btn.onclick=()=>{const value=inp.value;inp.value='';control({kind:'fill',target_ref:item.ref,value})};
      label.htmlFor=inp.id='auth-'+item.ref.replace(/[^a-zA-Z0-9-]/g,'');
    } else {
      append('span',row,item.label||item.category);
      const btn=append('button',row,`Click ${item.label||item.category}`);btn.type='button';
      btn.onclick=()=>control({kind:'click',target_ref:item.ref});
    }
  }
  $('#status').textContent=taskReason==='submit'?'Review the page, then click Submit once.':'Human assistance active';
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
  $('#status').textContent='Handed back to agent';endCapability();
  feedback(res.still_waiting_human?'Control returned. The site still displays a verification signal; the agent must inspect before proceeding.':'Control returned. The agent must verify the result before continuing.');
}catch(err){feedback(err.message)}};
setInterval(()=>{if(!expires)return;const remaining=Math.max(0,Math.ceil(expires-Date.now()/1000));$('#expiry').textContent=`Link expires in ${remaining} seconds`;if(!remaining){endCapability();$('#controls').querySelectorAll('button,input').forEach(el=>el.disabled=true);feedback(busy?'Link expired while processing. Ask the bot to check the outcome; do not retry.':'Link expired. Request a new invitation from the agent.')}},1000);
refresh().catch(e=>{feedback(e.message);$('#status').textContent='Unable to open verification'});
