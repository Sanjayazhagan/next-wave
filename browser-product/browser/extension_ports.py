"""Explicit adapter boundaries that generic DOM interpretation cannot safely infer.

Implementations are trusted Python modules reviewed and registered by operators;
neither model output nor a public request may install code or a selector policy.
"""
from typing import Protocol


class AuthenticationAdapter(Protocol):
    async def detect(self,page)->dict: ...
    async def relay_human_response(self,page,interrupt_id:str,response:str)->dict: ...


class HumanRegionAdapter(Protocol):
    async def region(self,page)->dict: ...
    async def completed(self,page)->bool: ...


class ReviewAdapter(Protocol):
    async def readback(self,page)->dict: ...
    async def submit_with_approval(self,page,review_hash:str,capability:str)->dict: ...


class ReceiptAdapter(Protocol):
    async def reconcile(self,page,operation_id:str)->dict: ...
    async def status(self,page,application_ref:str)->dict: ...


class CoreSkillPort(Protocol):
    async def lookup(self,portal_id:str,page_fingerprint:str)->dict: ...
    async def report_step(self,skill_id:str,observed_result:dict)->None: ...


class VerifiedProfilePort(Protocol):
    async def verified_fields(self,subject:str,requested_fields:list[str])->dict: ...
    async def prepared_artifact(self,subject:str,artifact_id:str)->dict: ...


# Intentionally no successful placeholder implementations. A missing adapter must
# remain unavailable instead of treating a model's text as auth/submission proof.
def capability_manifest():
    return {'version':'2','model_bundled':False,'observation':['text','accessibility','screenshot','fields','constraints','links','frames','tabs','tables'],
            'actions':['click','fill','select','check','upload','navigate','back','scroll','wait','switch_tab','extract'],
            'generic_network_methods':['GET','HEAD','OPTIONS'],
            'dedicated_adapter_required':['authentication','interactive_challenge_completion','final_review_and_submission','receipt_reconciliation','application_status'],
            'core_owned':['model_decisions','LangGraph','skill_learning_and_repair','consent_and_approval_decisions','WhatsApp','vault','eligibility_and_doctor']}
