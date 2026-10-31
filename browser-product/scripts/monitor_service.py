"""One bounded health/metrics sample; emits no personal data or external messages."""
import asyncio
import json
import os
import sys
import httpx


async def main():
    base=os.getenv('BASE_URL','http://127.0.0.1:8100').rstrip('/')
    key=os.getenv('INTERNAL_KEY','')
    if not key:raise SystemExit('Configure INTERNAL_KEY for the monitor; no key is printed')
    alerts=[]
    async with httpx.AsyncClient(base_url=base,timeout=10,headers={'X-Internal-Key':key}) as c:
        try:
            ready=await c.get('/ready');ready.raise_for_status()
            r=await c.get('/integration/v1/metrics');r.raise_for_status();data=r.json()
            if data['sessions_by_state'].get('submission_uncertain',0):alerts.append('submission_reconciliation_required')
            if data['human_tasks_by_state'].get('needs_reconciliation',0):alerts.append('human_step_reconciliation_required')
        except httpx.HTTPError:alerts.append('service_unavailable_or_monitor_unauthorized')
    print(json.dumps({'healthy':not alerts,'alerts':alerts,'contains_citizen_data':False}))
    return 2 if alerts else 0


if __name__=='__main__':raise SystemExit(asyncio.run(main()))
