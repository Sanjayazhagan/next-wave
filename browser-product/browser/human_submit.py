"""One citizen click on an immutable reviewed native form. Never automated submit."""
import asyncio
import time
from urllib.parse import urlsplit
from fastapi import HTTPException
from browser.general import signature,observe,resolve_target,origin
from browser.native_submit import click_reviewed_submit

def stopped(state,reason,**extra):
    return {'state':state,'reason':reason,'confirmed_by_portal':False,'receipt_number':None,'click_attempted':False,'needs_reconciliation':False,**extra}

def record(info,ctx,result):
    from browser.core_compat import release_human
    info.human_result_task_id=info.human_task_id
    info.human_result=result
    release_human(info,ctx)
    return result

async def prepare(info,ctx,req):
    from browser.core_compat import final_control
    if info.uncertain_action or info.consumed:raise HTTPException(409,'A submission was already attempted; reconcile before a new workflow')
    if not req.review_observation_id or not req.approval_ref:raise HTTPException(422,'submit requires review_observation_id and approval_ref')
    if req.review_observation_id!=info.observation_id:raise HTTPException(409,'Review changed; request a new citizen review',headers={'X-Browser-Outcome':'not_applied'})
    fp,elements,_,_,_=await signature(ctx)
    if ctx.inspection_incomplete or fp!=info.fingerprint or ctx.page.url!=ctx.observed_url:raise HTTPException(409,'Review page changed; request a new citizen review',headers={'X-Browser-Outcome':'not_applied'})
    finals=[e for e in elements if final_control(e) and not e.get('disabled') and (not req.target_ref or e['ref']==req.target_ref)]
    if len(finals)!=1:raise HTTPException(422,'Select exactly one reviewed final target_ref')
    e=finals[0]
    if not e.get('form') or e.get('form_method','').upper() not in ('GET','POST') or not e.get('form_state_complete',False):raise HTTPException(403,'Human submit needs a complete native form or reviewed portal adapter')
    try:
        if origin(ctx.page.url)!=origin(e['form_action']):raise ValueError()
    except ValueError:raise HTTPException(403,'Cross-origin final form needs a reviewed portal adapter') from None
    await ctx.check_destination(e['form_action'])
    if req.approval_ref in info.approval_refs:raise HTTPException(409,'Approval reference already used; request a new review')
    info.approval_refs.add(req.approval_ref)
    info.submit_review={'fingerprint':fp,'url':ctx.page.url,'target_ref':e['ref'],'scope':(e['form_method'].upper(),origin(e['form_action']),urlsplit(e['form_action']).path or '/')}
    info.human_result=None;info.human_result_task_id=None

async def check_review(info,ctx):
    fp,elements,targets,_,_=await signature(ctx)
    r=info.submit_review
    if not r or ctx.inspection_incomplete or fp!=r['fingerprint'] or ctx.page.url!=r['url']:
        record(info,ctx,stopped('review_changed','Review page changed; request a new citizen review',needs_new_review=True))
        raise HTTPException(409,'Review page changed; request a new citizen review',headers={'X-Browser-Outcome':'not_applied'})
    e=next((e for e in elements if e['ref']==r['target_ref']),None)
    if not e:raise HTTPException(409,'Reviewed submit target disappeared',headers={'X-Browser-Outcome':'not_applied'})
    return e,targets

async def view(info,ctx):
    await check_review(info,ctx)
    obs=await observe(ctx)
    if ctx.fingerprint!=info.submit_review['fingerprint']:
        await check_review(info,ctx)
    e=next(e for e in obs['elements'] if e['ref']==info.submit_review['target_ref'])
    return {'state':'human_in_control','reason':'submit','url':obs['url'],'observation_id':obs['observation_id'],'screenshot_base64':obs['screenshot_base64'],'viewport':obs['viewport'],'controls':[{'ref':e['ref'],'label':e['label'],'category':'final_submit','type':e['type'],'bounds':e['bounds']}],'challenge_boxes':[],'human_signals':obs['human_signals']}

async def click(info,ctx,req):
    from browser.core_compat import final_control,receipt_from_observation,convert,ensure_human
    if req.kind!='click' or req.value or req.x is not None or req.y is not None:raise HTTPException(403,'Submit handoff allows only its final button; no typing or coordinates',headers={'X-Browser-Outcome':'not_applied'})
    if not req.observation_id:raise HTTPException(422,'Current human-view observation_id is required',headers={'X-Browser-Outcome':'not_applied'})
    if req.target_ref!=info.submit_review['target_ref']:raise HTTPException(403,'Only the reviewed final submit control is allowed',headers={'X-Browser-Outcome':'not_applied'})
    e,targets=await check_review(info,ctx)
    if req.observation_id!=ctx.observation_id:raise HTTPException(409,'Human view changed; refresh the review',headers={'X-Browser-Outcome':'not_applied'})
    if not final_control(e):raise HTTPException(403,'Target is not a final control',headers={'X-Browser-Outcome':'not_applied'})
    loc=await resolve_target(ctx,e,targets)
    try:await loc.click(trial=True,timeout=2000)
    except Exception:raise HTTPException(409,'Reviewed submit is not actionable; request a new review',headers={'X-Browser-Outcome':'not_applied'}) from None
    # The last asynchronous preflight may itself permit a page change.
    await check_review(info,ctx)
    ensure_human(info,req.task_id)  # Expiry may elapse during asynchronous preflight.
    task=info.human_task_id;info.consumed=True;info.uncertain_action='human-submit:'+task
    result=stopped('uncertain','Submission outcome requires reconciliation',click_attempted=True,needs_reconciliation=True)
    try:
        async with asyncio.timeout(35):
            requested=await click_reviewed_submit(ctx,loc,info.submit_review['scope'])
            try:await ctx.page.wait_for_load_state('domcontentloaded',timeout=2500)
            except Exception:pass
            after=await observe(ctx,screenshot=False)
            receipt=receipt_from_observation(after,info)
            confirmed=bool(requested and receipt and after.get('page_status')=='ready' and ctx.fingerprint!=info.submit_review['fingerprint'])
            result={'state':'completed' if confirmed else 'uncertain','confirmed_by_portal':confirmed,'receipt_number':receipt,'click_attempted':True,'request_observed':requested,'needs_reconciliation':not confirmed,'url':after['url'],'page_status':after.get('page_status'),'page_text':after.get('text','')[:2000],'content_trust':'untrusted_website_data'}
            convert(after,info);info.fingerprint=ctx.fingerprint
            if confirmed:info.uncertain_action=None
    except asyncio.CancelledError:
        record(info,ctx,result);raise
    except Exception:
        pass  # No portal exception text, payload or credentials enter status/logs.
    return record(info,ctx,result)
