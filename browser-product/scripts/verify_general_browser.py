"""General browser tools on an unrelated multipage fixture. No AI decision is claimed."""
import asyncio
import json
from pathlib import Path
import sys
import uuid
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import httpx
from scripts.test_harness import services
from server.app import fixture_pdf
from browser.protocol import validate_decision
from clients.general_browser import GeneralBrowserClient
import base64
import io
from PIL import Image
from playwright.async_api import async_playwright


async def main():
    out=Path('output/general-browser')
    async with services(out,8920,8921) as (base,env):
        async with httpx.AsyncClient(base_url=base,headers={'X-Internal-Key':env['INTERNAL_KEY']},timeout=45) as c:
            async def request(method,path,body=None,status=200):
                r=await c.request(method,path,json=body)
                assert r.status_code==status,(path,r.status_code,r.text[:300])
                return r.json()
            denied=await c.post('/integration/v2/browser/contexts',json={'request_id':str(uuid.uuid4()),'subject':'synthetic-citizen','consent_ref':'synthetic-consent','url':'https://example.com'})
            assert denied.status_code==403
            created=await request('POST','/integration/v2/browser/contexts',{'request_id':str(uuid.uuid4()),'subject':'synthetic-citizen','consent_ref':'synthetic-consent','url':base+'/browser-lab/start'},201)
            ident=created['id'];root='/integration/v2/browser/contexts/'+ident;obs=created['observation']
            def target(label):
                found=[e for e in obs['elements'] if e['label']==label]
                assert len(found)==1,(label,[(e['label'],e['tag']) for e in obs['elements']])
                return found[0]['ref']
            async def action(kind,label=None,**kw):
                nonlocal obs
                body={'action_id':str(uuid.uuid4()),'observation_id':obs['observation_id'],'kind':kind,**kw}
                if label:body['target_ref']=target(label)
                if kind=='switch_tab':
                    (out/'tab-check.json').write_text(json.dumps({'requested':kw.get('tab_id'),'observed_tabs':obs['tabs']},indent=2),encoding='utf-8')
                result=await request('POST',root+'/actions',body)
                if kind in ('fill','select','check','upload'):
                    assert result['effect']['matched'] and result['provenance']['source_ref']
                obs=result['observation'];return result
            await action('click','Begin request')
            assert any(e['label']=='Supporting reference note' for e in obs['elements'])
            assert any(e['label']=='Supplement code' for e in obs['elements'])
            assert 'synthetic-secret' not in json.dumps({k:v for k,v in obs.items() if k!='screenshot_base64'})
            assert '123456789012' not in json.dumps({k:v for k,v in obs.items() if k!='screenshot_base64'})
            frame=await request('GET',f'/api/browser-contexts/{ident}/view')
            assert frame['screenshot_base64'] and 'observation_id' not in frame
            await action('fill','Applicant full name',value='Synthetic citizen',verified=True,source_ref='synthetic-profile')
            async with async_playwright() as pw:
                viewer_browser=await pw.chromium.launch()
                viewer_page=await viewer_browser.new_page(viewport={'width':900,'height':1000})
                await viewer_page.goto(base+'/browser-workbench#'+ident)
                await viewer_page.locator('#screen').wait_for(state='visible')
                assert 'synthetic-profile' in await viewer_page.locator('#provenance').inner_text()
                await viewer_page.screenshot(path=str(out/'workbench.png'),full_page=True)
                await viewer_browser.close()
            await action('select','Service route',value='priority',verified=True,source_ref='citizen-choice')
            await action('check','Send status notifications',checked=True,verified=True,source_ref='citizen-choice')
            await action('fill','Supporting reference note',value='Synthetic frame input',verified=True,source_ref='synthetic-document')
            await action('fill','Supplement code',value='SHADOW-TEST',verified=True,source_ref='synthetic-document')
            artifact=await request('POST',f'/integration/v1/sessions/{ident}/artifacts',{'subject':'synthetic-citizen','source_ref':'fixture','file_name':'fixture.pdf','file_base64':base64.b64encode(fixture_pdf()).decode()},201)
            await action('upload','Prepared certificate',artifact_id=artifact['artifact_id'],verified=True,source_ref='fixture')
            assert next(e for e in obs['elements'] if e['label']=='Prepared certificate')['file_count']==1
            picture=io.BytesIO();Image.new('RGB',(8,8),(25,110,90)).save(picture,format='PNG')
            image=await request('POST',root+'/artifacts',{'subject':'synthetic-citizen','source_ref':'synthetic-image','file_name':'photo.png','mime_type':'image/png','file_base64':base64.b64encode(picture.getvalue()).decode()},201)
            await action('upload','Prepared photograph',artifact_id=image['artifact_id'],verified=True,source_ref='synthetic-image')
            assert next(e for e in obs['elements'] if e['label']=='Prepared photograph')['file_count']==1
            stale=obs.copy();await action('click','Change field label')
            await request('POST',root+'/actions',{'action_id':str(uuid.uuid4()),'observation_id':stale['observation_id'],'kind':'fill','target_ref':stale['elements'][0]['ref'],'value':'wrong'},409)
            await action('fill','Applicant legal name',value='Updated synthetic citizen',verified=True,source_ref='citizen-edit')
            extracted=await action('extract','Applicant legal name');assert extracted['extracted']['value']=='Updated synthetic citizen'
            original_tab=next(t['id'] for t in obs['tabs'] if t['active'])
            await action('click','Open guidance')
            # Popup navigation completes asynchronously; refresh until it is an allowed live tab.
            for _ in range(20):
                obs=await request('GET',root+'/observe')
                candidates=[t for t in obs['tabs'] if t['id']!=original_tab and t['allowed']]
                if candidates:break
                await asyncio.sleep(.1)
            assert candidates
            await action('switch_tab',tab_id=candidates[0]['id']);assert 'Guidance' in obs['text']
            await action('switch_tab',tab_id=original_tab)
            await action('click','Preview request')
            assert obs['structure']['tables']
            await request('POST',root+'/actions',{'action_id':str(uuid.uuid4()),'observation_id':obs['observation_id'],'kind':'click','target_ref':target('Submit application')},403)
            await action('navigate',url=base+'/browser-lab/start')
            payload=await request('POST',root+'/model-input',{'goal':'Identify missing fields; do not submit anything'})
            assert 'screenshot_base64' not in payload['observation']
            view=await request('GET',f'/api/browser-contexts/{ident}/view')
            (out/'observed-page.jpeg').write_bytes(base64.b64decode(view['screenshot_base64']))
            assert payload['decision_schema'] and payload['observation']['content_trust']=='untrusted_website_data'
            try:validate_decision({'outcome':'act','summary':'invented target','action':{'action_id':str(uuid.uuid4()),'observation_id':payload['observation']['observation_id'],'kind':'click','target_ref':'invented'}},payload['observation'])
            except ValueError:pass
            else:raise AssertionError('Invented model target accepted')
            await request('DELETE',root)
            async with GeneralBrowserClient(base,env['INTERNAL_KEY']) as sdk:
                from browser.protocol import ContextStart
                sdk_context=await sdk.create(ContextStart(request_id=str(uuid.uuid4()),subject='synthetic-sdk',consent_ref='fixture',url=base+'/browser-lab/start'))
                sdk_payload=await sdk.model_input(sdk_context['id'],'Identify the next link, without submitting')
                assert sdk_payload['observation']['elements']
                paused=await sdk.apply_decision(sdk_context['id'],{'outcome':'needs_information','summary':'Ask citizen for the required information'},sdk_payload['observation'])
                assert paused['paused']
                class ExplicitFixturePort:
                    async def decide(self,*,request):
                        assert request['instructions'] and request['decision_schema'] and request['observation']
                        return {'outcome':'needs_information','summary':'Synthetic contract test: ask citizen, no model called'}
                assert (await sdk.step_with_model(sdk_context['id'],'Identify missing fields',ExplicitFixturePort()))['paused']
                try:await sdk.step_with_model(sdk_context['id'],'Do not guess',None)
                except ValueError:pass
                else:raise AssertionError('Missing model was silently accepted')
                await sdk.close(sdk_context['id'])
            report={'mode':'synthetic','model_connected':False,'general_observation_and_tools':'passed','navigation_select_checkbox_upload':'passed','iframe_shadow_dom_popup_tabs':'passed','stale_refs_and_submit_gate':'passed','provider_neutral_model_input_and_output_validation':'passed','real_portal_verified':False}
            (out/'results.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report,indent=2))


if __name__=='__main__':asyncio.run(main())
