"""Low-cardinality, process-local HTTP metrics; no identifiers or request bodies."""
from collections import Counter
import time

requests=Counter()
latency=Counter()

class Telemetry:
    def __init__(self,app):self.app=app
    async def __call__(self,scope,receive,send):
        if scope['type']!='http':return await self.app(scope,receive,send)
        family=scope['path'].split('/')[1] if scope['path'].startswith(('/api/','/assist-api/','/integration/','/core-browser/','/core-assist/')) else 'other'
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
    try:
        from server import app
        from server.core_assist import database
        database()
        with app.conn() as db:
            rows=db.execute('SELECT state,count(*) AS n FROM core_assist_tasks GROUP BY state').fetchall()
        for row in rows:
            if row['state'] in ('active','offering','completing','needs_reconciliation','expired','completed','cancelled'):
                lines.append(f"gradientzero_core_assist_tasks{{state=\"{row['state']}\"}} {row['n']}")
    except Exception:pass
    return '\n'.join(lines)+'\n'
