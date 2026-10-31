/** Executable synthetic integration example for the core/n8n teammate. */
import { randomUUID } from 'node:crypto';
import { BrowserClient } from './browser_client.mjs';
if (process.env.ALLOW_SYNTHETIC_EXAMPLE !== '1' || !process.env.INTERNAL_KEY || !process.env.BASE_URL) {
  throw new Error('Set BASE_URL, INTERNAL_KEY and ALLOW_SYNTHETIC_EXAMPLE=1 for a local synthetic run');
}
const client = new BrowserClient(process.env.BASE_URL, process.env.INTERNAL_KEY);
const values = {student_name:'Synthetic Node Citizen',course:'B.Tech',income:'120000',state:'Tamil Nadu',category:'BC'};
const input = {request_id:randomUUID(),subject:'synthetic-node-example',consent_ref:'synthetic-example',mode:'demo',fields:Object.fromEntries(Object.entries(values).map(([k,value])=>[k,{value,source_ref:'synthetic-example',confidence:1,verified:true}]))};
const session = await client.start(input);
if ((await client.start(input)).id !== session.id) throw new Error('Start replay failed');
const command = (expected_state,kind,payload={})=>client.command(session.id,{action_id:randomUUID(),expected_state,kind,payload});
await command('otp_needed','otp',{otp:'246810'});
await command('captcha_needed','human',{challenge_answer:'7'});
const review = await command('form_ready','fill');
const approval = {action_id:randomUUID(),expected_state:'approval_needed',kind:'approve',payload:{confirmed:true,review_hash:review.review_hash}};
const receipt = await client.command(session.id,approval);
if ((await client.command(session.id,approval)).receipt_id !== receipt.receipt_id) throw new Error('Approval replay failed');
if ((await command('submitted','poll')).status !== 'submitted') throw new Error('Status check failed');
const events = await client.events(session.id);
if ((await client.events(session.id,events.next_cursor)).events.length) throw new Error('Event replay cursor failed');
console.log(JSON.stringify({mode:'synthetic',node_client:'passed',real_application_submitted:false}));
