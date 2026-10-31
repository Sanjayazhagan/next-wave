"""Low-cardinality, process-local HTTP metrics; no identifiers or request bodies."""
from collections import Counter
import time

requests=Counter()
latency=Counter()

class Telemetry:
    def __init__(self,app):self.app=app
    async def __call__(self,scope,receive,send):
        if scope['type']!='http':return await self.app(scope,receive,send)
        family=scope['path'].split('/')[1] if scope['path'].startswith(('/api/','/assist-api/','/integration/')) else 'other'
        status=500;start=time.monotonic()
        async def observed(message):
            nonlocal status
            if message['type']=='http.response.start':status=message['status']
            await send(message)
        try:await self.app(scope,receive,observed)
        finally:
            requests[(family,str(status))]+=1
            latency[family]+=time.monotonic()-start


def render():
    lines=['# TYPE gradientzero_http_requests_total counter']
    for (family,status),count in sorted(requests.items()):
        lines.append(f'gradientzero_http_requests_total{{family="{family}",status="{status}"}} {count}')
    lines.append('# TYPE gradientzero_http_duration_seconds_sum counter')
    for family,total in sorted(latency.items()):lines.append(f'gradientzero_http_duration_seconds_sum{{family="{family}"}} {total}')
    return '\n'.join(lines)+'\n'
