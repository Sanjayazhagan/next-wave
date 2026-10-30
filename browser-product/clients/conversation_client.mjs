/** Server-side core/n8n transport. This client never talks to a WhatsApp provider. */
export class ConversationClient {
  constructor(baseUrl,key){this.base=baseUrl.replace(/\/$/,'')+'/integration/v2/conversation';this.key=key;}
  async request(method,path,body){
    const r=await fetch(this.base+path,{method,signal:AbortSignal.timeout(45000),headers:{'X-Internal-Key':this.key,...(body?{'Content-Type':'application/json'}:{})},body:body?JSON.stringify(body):undefined});
    const data=await r.json();if(!r.ok){const e=new Error(data.detail||'Conversation transport failed');e.status=r.status;throw e;}return data;
  }
  binding(id){return this.request('GET',`/executions/${encodeURIComponent(id)}`);}
  ask(input){return this.request('POST','/interrupts',input);}
  notify(input){return this.request('POST','/notifications',input);}
  claim(consumer_id){return this.request('POST','/deliveries/claim',{consumer_id});}
  acknowledge(id,input){return this.request('POST',`/deliveries/${encodeURIComponent(id)}/ack`,input);}
  respond(id,input){return this.request('POST',`/interrupts/${encodeURIComponent(id)}/responses`,input);}
  response(id){return this.request('GET',`/interrupts/${encodeURIComponent(id)}/response`);}
  status(id){return this.request('GET',`/interrupts/${encodeURIComponent(id)}`);}
  cancel(id){return this.request('POST',`/interrupts/${encodeURIComponent(id)}/cancel`,{});}
}
