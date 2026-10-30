import {randomUUID} from 'node:crypto';
import {ConversationClient} from './conversation_client.mjs';
if(process.env.ALLOW_SYNTHETIC_EXAMPLE!=='1'||!process.env.BASE_URL||!process.env.INTERNAL_KEY)throw Error('Configure explicit synthetic test environment');
const base=process.env.BASE_URL,key=process.env.INTERNAL_KEY;
async function browser(method,path,body){const r=await fetch(base+'/integration/v2/browser'+path,{method,headers:{'X-Internal-Key':key,...(body?{'Content-Type':'application/json'}:{})},body:body?JSON.stringify(body):undefined});const data=await r.json();if(!r.ok)throw Error(data.detail);return data;}
const created=await browser('POST','/contexts',{request_id:randomUUID(),subject:'synthetic-node-conversation',consent_ref:'synthetic-consent',url:base+'/browser-lab/start'});
const transport=new ConversationClient(base,key),bound=await transport.binding(created.id);
const ticket=await transport.ask({request_id:randomUUID(),context_id:created.id,generation:bound.generation,subject:bound.subject,kind:'information',prompt:'What name should the synthetic application use?',fields:[{name:'name',label:'Applicant name'}]});
const claimed=await transport.claim('synthetic-node-consumer');
if(claimed.delivery?.interrupt_id!==ticket.interrupt_id)throw Error('Message correlation failed');
await transport.acknowledge(claimed.delivery.delivery_id,{consumer_id:'synthetic-node-consumer',lease_token:claimed.lease_token,provider_message_id:'SYNTHETIC-NOT-SENT'});
await transport.respond(ticket.interrupt_id,{response_id:randomUUID(),subject:bound.subject,generation:bound.generation,values:{name:'Synthetic Node Applicant'}});
if((await transport.response(ticket.interrupt_id)).values.name!=='Synthetic Node Applicant')throw Error('Reply correlation failed');
await browser('DELETE','/contexts/'+created.id);
console.log(JSON.stringify({node_conversation_client:'passed',external_message_sent:false}));
