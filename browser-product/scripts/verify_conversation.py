"""Actual HTTP browser ↔ synthetic message consumer ↔ citizen reply. No external send."""
import asyncio
import json
from pathlib import Path
import sys
import uuid
import os
import subprocess
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.test_harness import services
from clients.general_browser import GeneralBrowserClient
from clients.conversation_client import ConversationClient
from clients.browser_client import BrowserClient
from browser.protocol import ContextStart,BrowserAction
from server.conversation_bridge import Interrupt,CitizenReply,Question,Notification
from server.contracts import BrowserStart,BrowserCommand
from server.app import DEFAULT_PROFILE


async def main():
    out=Path('output/conversation-integration')
    async with services(out,8940,8941) as (base,env):
        key=env['INTERNAL_KEY']
        async with GeneralBrowserClient(base,key) as browser,ConversationClient(base,key) as bridge,BrowserClient(base,key) as legacy:
            created=await browser.create(ContextStart(request_id=str(uuid.uuid4()),subject='synthetic-citizen',consent_ref='synthetic-consent',url=base+'/browser-lab/application'))
            ident=created['id'];binding=await bridge.binding(ident)
            decision={'outcome':'needs_information','summary':'What applicant name should be used?','requested_fields':['name']}
            waiting=await bridge.ask_from_decision(binding,decision,str(uuid.uuid4()),questions=[Question(name='name',label='Applicant name')])
            ticket=waiting['interrupt_id']
            # Fake consumer exercises the exact queue/ack interface real core/n8n will use.
            delivery=await bridge.claim_delivery('synthetic-whatsapp-consumer')
            message=delivery['delivery'];assert message['interrupt_id']==ticket
            await bridge.acknowledge(message['delivery_id'],'synthetic-whatsapp-consumer',delivery['lease_token'],'SYNTHETIC-MESSAGE-NOT-SENT')
            reply=CitizenReply(response_id=str(uuid.uuid4()),subject=binding['subject'],generation=binding['generation'],values={'name':'Synthetic applicant from conversation'})
            await bridge.respond(ticket,reply)
            values=await bridge.response(ticket)
            assert values['verification_status']=='citizen_provided_not_document_verified'
            observed=await browser.observe(ident)
            field=next(e for e in observed['elements'] if e['label']=='Applicant full name')
            # Fixture core explicitly confirms this synthetic value before filling.
            result=await browser.act(ident,BrowserAction(action_id=str(uuid.uuid4()),observation_id=observed['observation_id'],kind='fill',target_ref=field['ref'],value=values['values']['name'],verified=True,source_ref='synthetic-core-confirmed-citizen-reply'))
            assert result['effect']['matched']
            await browser.close(ident)
            # Test actual legacy OTP adapter routing: the code never enters the queue or DB.
            session=await legacy.start(BrowserStart(request_id=str(uuid.uuid4()),subject='synthetic-otp-user',consent_ref='fixture',fields={k:{'value':v,'source_ref':'fixture','confidence':1,'verified':True} for k,v in DEFAULT_PROFILE.items()}))
            bound=await bridge.binding(session['id'])
            otp=await bridge.ask(Interrupt(request_id=str(uuid.uuid4()),context_id=session['id'],generation=bound['generation'],subject=bound['subject'],kind='otp',prompt='Enter your fictional test code'))
            response=await bridge.respond(otp['interrupt_id'],CitizenReply(response_id=str(uuid.uuid4()),subject=bound['subject'],generation=bound['generation'],secret='246810'))
            assert response['state']=='completed' and not response['secret_persisted']
            assert (await legacy.session(session['id']))['state']=='captcha_needed'
            async def adapter_command(expected,kind,payload=None):
                return await legacy.command(session['id'],BrowserCommand(action_id=str(uuid.uuid4()),expected_state=expected,kind=kind,payload=payload or {}))
            await adapter_command('captcha_needed','human',{'challenge_answer':'7'})
            review=await adapter_command('form_ready','fill')
            receipt=await adapter_command('approval_needed','approve',{'confirmed':True,'review_hash':review['review_hash']})
            assert (await legacy.receipt(session['id'])).startswith(b'%PDF-')
            for kind in ('result','status'):
                await bridge.notify(Notification(notification_id=str(uuid.uuid4()),context_id=session['id'],generation=bound['generation'],subject=bound['subject'],kind=kind,summary='Synthetic application '+kind,receipt_ref=receipt['receipt_id']))
                notice=await bridge.claim_delivery('synthetic-result-consumer')
                assert notice['delivery']['requires_response'] is False and notice['delivery']['receipt_ref']==receipt['receipt_id']
                await bridge.acknowledge(notice['delivery']['delivery_id'],'synthetic-result-consumer',notice['lease_token'],'SYNTHETIC-NOT-SENT')
            node=await asyncio.to_thread(subprocess.run,['node','clients/example_conversation.mjs'],env=dict(os.environ,BASE_URL=base,INTERNAL_KEY=key,ALLOW_SYNTHETIC_EXAMPLE='1'),capture_output=True,text=True,timeout=60,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            if node.returncode:raise RuntimeError('Node conversation example failed')
            report={'scope':'synthetic integration; no AI or WhatsApp provider called','information_request_delivery_ack_reply':'passed','verified_reply_filled_in_live_general_browser':'passed','transient_otp_relay_to_actual_worker':'passed','observed_receipt_result_and_status_notifications':'passed','authenticated_receipt_download':'passed','node_example':json.loads(node.stdout),'external_message_sent':False}
            (out/'results.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report,indent=2))


if __name__=='__main__':asyncio.run(main())
