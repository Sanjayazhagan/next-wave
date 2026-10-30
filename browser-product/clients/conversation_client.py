"""Core/WhatsApp transport client; not a WhatsApp provider implementation."""
import httpx
from server.conversation_bridge import Interrupt,CitizenReply,Notification


class ConversationClient:
    def __init__(self,base_url,service_key):
        self.http=httpx.AsyncClient(base_url=base_url.rstrip('/')+'/integration/v2/conversation/',headers={'X-Internal-Key':service_key},timeout=45)
    async def __aenter__(self):return self
    async def __aexit__(self,*args):await self.http.aclose()
    async def request(self,method,path,body=None):
        r=await self.http.request(method,path,json=body);r.raise_for_status();return r.json()
    async def binding(self,context_id):return await self.request('GET',f'executions/{context_id}')
    async def ask(self,request:Interrupt):return await self.request('POST','interrupts',request.model_dump())
    async def claim_delivery(self,consumer_id):return await self.request('POST','deliveries/claim',{'consumer_id':consumer_id})
    async def acknowledge(self,delivery_id,consumer_id,lease_token,provider_message_id):
        return await self.request('POST',f'deliveries/{delivery_id}/ack',{'consumer_id':consumer_id,'lease_token':lease_token,'provider_message_id':provider_message_id})
    async def respond(self,interrupt_id,reply:CitizenReply):return await self.request('POST',f'interrupts/{interrupt_id}/responses',reply.model_dump())
    async def status(self,interrupt_id):return await self.request('GET',f'interrupts/{interrupt_id}')
    async def response(self,interrupt_id):return await self.request('GET',f'interrupts/{interrupt_id}/response')
    async def cancel(self,interrupt_id):return await self.request('POST',f'interrupts/{interrupt_id}/cancel',{})
    async def reconcile(self,interrupt_id):return await self.request('POST',f'interrupts/{interrupt_id}/reconcile',{})
    async def notify(self,request:Notification):return await self.request('POST','notifications',request.model_dump())
    async def ask_from_decision(self,binding,decision,request_id,questions=None,review_hash=None):
        """Map a validated core model pause to transport; never infer missing values."""
        from browser.protocol import ModelDecision
        parsed=decision if isinstance(decision,ModelDecision) else ModelDecision.model_validate(decision)
        kinds={'needs_information':'information','needs_human':'helper','needs_review':'approval'}
        if parsed.outcome not in kinds:raise ValueError('Only explicit pause decisions can queue citizen requests')
        if parsed.action is not None:raise ValueError('Conversation pauses cannot execute actions')
        if parsed.outcome=='needs_information' and parsed.requested_fields and set(parsed.requested_fields)!={q.name for q in (questions or [])}:raise ValueError('Core question mapping must cover exactly the model-requested field IDs')
        return await self.ask(Interrupt(request_id=request_id,context_id=binding['context_id'],generation=binding['generation'],subject=binding['subject'],kind=kinds[parsed.outcome],prompt=parsed.summary,fields=questions or [],review_hash=review_hash))
