"""Run after both services start, e.g. python scripts/run_local.py.
Full browser flow requires a host browser with network navigation permitted.
"""
import json, sys, urllib.error, urllib.request
BASE='http://127.0.0.1:8100'
def req(method,path,payload=None):
    data=None if payload is None else json.dumps(payload).encode()
    request=urllib.request.Request(BASE+path,method=method,data=data,headers={'Content-Type':'application/json'})
    try:
        with urllib.request.urlopen(request,timeout=35) as r: return json.load(r)
    except urllib.error.HTTPError as e:
        print('HTTP ERROR',e.code,e.read().decode()[:300]);raise

def main():
    print('health',req('GET','/health'))
    r=req('POST','/api/sessions',{'consent':True})
    sid=r['id']; print('created:',sid)
    print('otp',req('POST',f'/api/sessions/{sid}/otp',{'otp':'246810'}))
    print('human',req('POST',f'/api/sessions/{sid}/human',{'challenge_answer':'7'}))
    print('inject',req('POST',f'/api/sessions/{sid}/inject',{'script_name':'rename_income'}))
    print('fill',req('POST',f'/api/sessions/{sid}/fill',{}))
    session=req('GET',f'/api/sessions/{sid}')
    assert session['state']=='approval_needed'
    print('approve',req('POST',f'/api/sessions/{sid}/approve',{'confirmed':True,'review_hash':session['review_hash']}))
    print('status',req('POST',f'/api/sessions/{sid}/poll',{}))
    print('audit',len(req('GET',f'/api/sessions/{sid}/audit')['events']))
    assert req('GET',f'/api/sessions/{sid}')['state']=='submitted'
    print('PASS - actual local browser-driven integration')

if __name__=='__main__':
    try: main()
    except Exception as e:
        print('INTEGRATION BLOCKED/FAILED:',str(e));sys.exit(1)
