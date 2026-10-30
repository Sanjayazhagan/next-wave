"""Bound actual streamed bytes before any request can cause side effects."""
import asyncio
import os


class RequestBoundary:
    def __init__(self,app):
        self.app=app

    async def __call__(self,scope,receive,send):
        if scope['type']!='http' or scope['method'] not in ('POST','PUT','PATCH','DELETE'):
            return await self.app(scope,receive,send)
        limit=int(os.getenv('MAX_REQUEST_BYTES','2097152'))
        lengths=[v for k,v in scope.get('headers',[]) if k.lower()==b'content-length']
        status=None
        if len(lengths)>1 or (lengths and not lengths[0].isdigit()):
            status=400
        elif lengths and int(lengths[0])>limit:
            status=413
        body=bytearray()
        if not status:
            try:
                async with asyncio.timeout(float(os.getenv('REQUEST_BODY_TIMEOUT_SECONDS','15'))):
                    while True:
                        message=await receive()
                        if message['type']=='http.disconnect':
                            return
                        chunk=message.get('body',b'')
                        if len(body)+len(chunk)>limit:
                            status=413;break
                        body.extend(chunk)
                        if not message.get('more_body',False):
                            break
            except TimeoutError:
                status=408
        if status:
            await send({'type':'http.response.start','status':status,'headers':[(b'content-type',b'application/json'),(b'cache-control',b'no-store')]})
            await send({'type':'http.response.body','body':b'{"detail":"Request body rejected by size, framing or timeout policy"}'})
            return
        if lengths and int(lengths[0])!=len(body):
            await send({'type':'http.response.start','status':400,'headers':[(b'content-type',b'application/json')]})
            await send({'type':'http.response.body','body':b'{"detail":"Request length mismatch"}'})
            return
        delivered=False
        async def buffered():
            nonlocal delivered
            if not delivered:
                delivered=True
                return {'type':'http.request','body':bytes(body),'more_body':False}
            return await receive()
        await self.app(scope,buffered,send)
