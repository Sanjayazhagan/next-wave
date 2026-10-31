import json
import time
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
import server.app as app


def fixture(monkeypatch,tmp_path):
    monkeypatch.setattr(app,'DB',tmp_path/'conversation.db');monkeypatch.setenv('DATA_ENCRYPTION_KEYS',Fernet.generate_key().decode())
    async def worker(method,path,payload=None,timeout=20):
        if path=='/sessions':return {'worker_session_id':'generation-1'}
        if path.endswith('/otp'):return {'ok':payload['otp']=='246810'}
        raise AssertionError(path)
    monkeypatch.setattr(app,'worker',worker)


def start(c,headers):
    request={'request_id':'start-conversation-1','subject':'alice','consent_ref':'synthetic-consent','fields':{k:{'value':v,'source_ref':'synthetic-fixture','confidence':1,'verified':True} for k,v in app.DEFAULT_PROFILE.items()}}
    return c.post('/integration/v1/sessions',headers=headers,json=request).json()['id']


def test_information_delivery_reply_pause_and_dedup(monkeypatch,tmp_path):
    fixture(monkeypatch,tmp_path);headers={'X-Internal-Key':app.KEY};root='/integration/v2/conversation'
    with TestClient(app.app) as c:
        sid=start(c,headers)
        ask={'request_id':'ask-missing-0001','context_id':sid,'generation':'generation-1','subject':'alice','kind':'information','prompt':'What is your annual income?','fields':[{'name':'income','label':'Annual income','kind':'number'}]}
        assert c.post(root+'/interrupts',json=ask).status_code==401
        made=c.post(root+'/interrupts',headers=headers,json=ask);assert made.status_code==201,made.text
        ident=made.json()['interrupt_id']
        assert c.post(root+'/interrupts',headers=headers,json=ask).json()['interrupt_id']==ident
        assert c.post(f'/api/sessions/{sid}/otp',json={'otp':'246810'}).status_code==409
        delivery=c.post(root+'/deliveries/claim',headers=headers,json={'consumer_id':'local-consumer'}).json()
        assert delivery['delivery']['subject']=='alice'
        assert c.post(root+'/deliveries/claim',headers=headers,json={'consumer_id':'other'}).json()['delivery'] is None
        ack={'consumer_id':'local-consumer','lease_token':delivery['lease_token'],'provider_message_id':'synthetic-message-01'}
        path=root+'/deliveries/'+delivery['delivery']['delivery_id']+'/ack'
        assert c.post(path,headers=headers,json={**ack,'consumer_id':'wrong'}).status_code==403
        assert c.post(path,headers=headers,json=ack).json()['state']=='sent'
        assert c.post(path,headers=headers,json=ack).json()['replayed']
        reply={'response_id':'reply-0001','subject':'alice','generation':'generation-1','values':{'income':'120000'}}
        path=root+'/interrupts/'+ident+'/responses'
        assert c.post(path,headers=headers,json={**reply,'subject':'bob'}).status_code==403
        assert c.post(path,headers=headers,json={**reply,'generation':'old'}).status_code==409
        assert c.post(path,headers=headers,json={**reply,'values':{'income':'nan'}}).status_code==422
        assert c.post(path,headers=headers,json=reply).json()['state']=='completed'
        assert c.post(path,headers=headers,json=reply).json()['replayed']
        result=c.get(root+'/interrupts/'+ident+'/response',headers=headers).json()
        assert result['values']['income']=='120000' and result['verification_status']=='citizen_provided_not_document_verified'
        with app.conn() as db:
            stored=db.execute('SELECT response FROM conversation_interrupts WHERE id=?',(ident,)).fetchone()['response']
        assert '120000' not in stored


def test_otp_not_stored_expiry_and_reclaimed_delivery(monkeypatch,tmp_path):
    fixture(monkeypatch,tmp_path);headers={'X-Internal-Key':app.KEY};root='/integration/v2/conversation'
    with TestClient(app.app) as c:
        sid=start(c,headers)
        ask={'request_id':'otp-request-001','context_id':sid,'generation':'generation-1','subject':'alice','kind':'otp','prompt':'Enter the fictional test code'}
        made=c.post(root+'/interrupts',headers=headers,json=ask);assert made.status_code==201,made.text
        ident=made.json()['interrupt_id']
        first=c.post(root+'/deliveries/claim',headers=headers,json={'consumer_id':'crashed'}).json()
        with app.conn() as db:db.execute('UPDATE conversation_deliveries SET lease_until=? WHERE id=?',(time.time()-1,first['delivery']['delivery_id']))
        second=c.post(root+'/deliveries/claim',headers=headers,json={'consumer_id':'recovery'}).json()
        assert first['delivery']['delivery_id']==second['delivery']['delivery_id'] and first['lease_token']!=second['lease_token']
        response={'response_id':'otp-response-001','subject':'alice','generation':'generation-1','secret':'246810'}
        result=c.post(root+'/interrupts/'+ident+'/responses',headers=headers,json=response)
        assert result.status_code==200,result.text
        assert result.json()['state']=='completed'
        assert c.get('/api/sessions/'+sid).json()['state']=='captcha_needed'
        with app.conn() as db:
            r=dict(db.execute('SELECT * FROM conversation_interrupts WHERE id=?',(ident,)).fetchone())
            assert r['response'] is None and '246810' not in str(r)
        # Expired requests never accept late replies.
        ask.update(request_id='expired-request-01',kind='helper')
        ident=c.post(root+'/interrupts',headers=headers,json=ask).json()['interrupt_id']
        with app.conn() as db:db.execute('UPDATE conversation_interrupts SET expires=? WHERE id=?',(time.time()-1,ident))
        assert c.post(root+'/interrupts/'+ident+'/responses',headers=headers,json={**response,'secret':None}).status_code==409


def test_failed_secret_reply_dedup_and_approval_is_not_submission(monkeypatch,tmp_path):
    fixture(monkeypatch,tmp_path);headers={'X-Internal-Key':app.KEY};root='/integration/v2/conversation'
    with TestClient(app.app) as c:
        sid=start(c,headers)
        ask={'request_id':'otp-retry-request-1','context_id':sid,'generation':'generation-1','subject':'alice','kind':'otp','prompt':'Enter fictional test code'}
        ident=c.post(root+'/interrupts',headers=headers,json=ask).json()['interrupt_id']
        reply={'response_id':'bad-code-response-1','subject':'alice','generation':'generation-1','secret':'000000'}
        path=root+'/interrupts/'+ident+'/responses'
        assert c.post(path,headers=headers,json=reply).json()['state']=='pending'
        assert c.post(path,headers=headers,json=reply).json()['replayed']
        assert c.get(root+'/interrupts/'+ident,headers=headers).json()['attempts']==1
        c.post(root+'/interrupts/'+ident+'/cancel',headers=headers)
        digest='a'*64
        with app.conn() as db:db.execute("UPDATE sessions SET state='approval_needed',review_hash=? WHERE id=?",(digest,sid))
        ask.update(request_id='approval-request-1',kind='approval',prompt='Approve this fictional review?',review_hash=digest)
        ident=c.post(root+'/interrupts',headers=headers,json=ask).json()['interrupt_id']
        reply={'response_id':'approval-response-1','subject':'alice','generation':'generation-1','decision':'approve','review_hash':digest}
        result=c.post(root+'/interrupts/'+ident+'/responses',headers=headers,json=reply).json()
        assert result['state']=='completed' and result['submission_performed'] is False
        assert c.get('/api/sessions/'+sid).json()['state']=='approval_needed'
        assert c.get(root+'/interrupts/'+ident+'/response',headers=headers).json()['decision']=='approve'
