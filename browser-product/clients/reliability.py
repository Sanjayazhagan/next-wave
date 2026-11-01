"""Bounded backoff only when retry cannot duplicate a browser effect."""
import asyncio

def not_applied(response):
    if response.headers.get('X-Browser-Outcome')=='not_applied':return True
    if response.headers.get('X-Browser-Outcome')=='unknown':return False
    try:detail=str(response.json().get('detail',''))
    except ValueError:detail=''
    return response.status_code==409 and any(t in detail for t in ('Page changed since','Observation is stale','Target changed;','Target no longer observed'))

async def request_with_backoff(http,method,path,body=None):
    for attempt in range(3):
        response=await http.request(method,path,json=body)
        safe=method.upper()=='GET' or response.headers.get('X-Browser-Outcome')=='not_applied'
        if response.status_code not in (429,503) or not safe or attempt==2:break
        hint=response.headers.get('Retry-After','1')
        # Long delays belong to the caller's scheduler, not a blocking tool loop.
        if not hint.isdigit() or int(hint)>3:break
        await asyncio.sleep(max(.1,int(hint)))
    response.raise_for_status()
    return response.json()
