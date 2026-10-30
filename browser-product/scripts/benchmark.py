"""Five-run deterministic mock benchmark (requires active API & worker and network-enabled Chromium).
Prints results and saves CSV; never treats synthetic results as real-portal performance.
"""
import argparse,csv,json,time,urllib.request,urllib.error
from pathlib import Path
BASE='http://127.0.0.1:8100'
def call(method,path,data=None):
    req=urllib.request.Request(BASE+path,data=json.dumps(data).encode() if data is not None else None,method=method,headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=45) as f:return json.load(f)
def one(idx,chaos):
    start=time.monotonic();sid=None
    try:
        s=call('POST','/api/sessions',{'consent':True});sid=s['id'];
        call('POST',f'/api/sessions/{sid}/otp',{'otp':'246810'})
        call('POST',f'/api/sessions/{sid}/human',{'challenge_answer':'7'})
        if chaos:call('POST',f'/api/sessions/{sid}/inject',{'script_name':chaos})
        result=call('POST',f'/api/sessions/{sid}/fill',{})
        if result['state']!='approval_needed': raise ValueError('Not at review stage: '+result['state'])
        call('POST',f'/api/sessions/{sid}/approve',{'confirmed':True,'review_hash':result['review_hash']})
        status=call('POST',f'/api/sessions/{sid}/poll',{})
        events=call('GET',f'/api/sessions/{sid}/audit')['events']
        return {'run':idx,'chaos':chaos or 'none','success':status['status']=='submitted','seconds':round(time.monotonic()-start,2),'repairs':result.get('repairs',0),'events':len(events),'error':''}
    except Exception as e:
        return {'run':idx,'chaos':chaos or 'none','success':False,'seconds':round(time.monotonic()-start,2),'repairs':0,'events':0,'error':str(e)[:180]}
    finally:
        if sid:
            try:call('DELETE',f'/api/sessions/{sid}')
            except Exception:pass

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--runs',type=int,default=5);a.add_argument('--chaos',default='rename_income',choices=['none','rename_income','popup','server_failure','move_button']);a.add_argument('--out',default='benchmark_mock.csv');v=a.parse_args()
    results=[]
    for i in range(1,v.runs+1):
        item=one(i,None if v.chaos=='none' else v.chaos);results.append(item);print(item,flush=True)
    with open(v.out,'w',newline='') as f:
        writer=csv.DictWriter(f,results[0]);writer.writeheader();writer.writerows(results)
    success=sum(x['success'] for x in results)
    print(f'Finished {success}/{len(results)} successful **MOCK** runs. Results: {v.out}')
    raise SystemExit(0 if success==len(results) else 1)
