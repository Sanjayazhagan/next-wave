"""Single-host persistent request budgets. Edge/distributed protection is separate."""
import hashlib
import os
import time
from fastapi.responses import JSONResponse

class RateLimit:
    def __init__(self,app):self.app=app
    async def __call__(self,scope,receive,send):
        path=scope.get('path','')
        if scope['type']!='http' or not path.startswith(('/api/','/auth/','/assist-api/','/integration/')):
            return await self.app(scope,receive,send)
        from server import app
        family='auth' if path.startswith('/auth/') or path.endswith('/claim') else ('core' if path.startswith('/integration/') else 'citizen')
        budget={'auth':30,'core':600,'citizen':360}[family]
        client=(scope.get('client') or ('unknown',0))[0]
        fingerprint=hashlib.sha256((app.SIGN_KEY+family+str(client)).encode()).hexdigest()
        bucket=int(time.time()//60)
        with app.conn() as db:
            db.execute('CREATE TABLE IF NOT EXISTS service_budgets (client TEXT,bucket INTEGER,count INTEGER,PRIMARY KEY(client,bucket))')
            db.execute('DELETE FROM service_budgets WHERE bucket<?',(bucket-2,))
            db.execute('INSERT INTO service_budgets VALUES(?,?,1) ON CONFLICT(client,bucket) DO UPDATE SET count=count+1',(fingerprint,bucket))
            count=db.execute('SELECT count FROM service_budgets WHERE client=? AND bucket=?',(fingerprint,bucket)).fetchone()['count']
        if count>budget:
            return await JSONResponse({'detail':'Request budget exceeded; retry shortly'},status_code=429,headers={'Retry-After':'60'})(scope,receive,send)
        return await self.app(scope,receive,send)
