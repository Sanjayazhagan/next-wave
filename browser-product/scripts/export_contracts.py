"""Export versioned human-assistance input schemas from actual API models."""
import json
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
from server.integration import TaskRequest, Claim, Reply, Control
from server.contracts import BrowserStart, BrowserCommand, PreparedDocument
from server.access import Assignment,Revocation

out = root/'contracts'/'v1'
out.mkdir(exist_ok=True)
for name, model in [('human-task', TaskRequest), ('human-claim', Claim), ('human-response', Reply), ('human-control', Control), ('browser-start', BrowserStart), ('browser-command', BrowserCommand), ('prepared-document', PreparedDocument), ('operator-assignment',Assignment), ('identity-revocation',Revocation)]:
    (out/(name+'.schema.json')).write_text(json.dumps(model.model_json_schema(), indent=2)+'\n', encoding='utf-8')
print('Exported integration request schemas')
from browser.protocol import ContextStart,BrowserAction,ModelDecision,GeneralDocument
out2=root/'contracts'/'v2';out2.mkdir(exist_ok=True)
for name,model in [('context-start',ContextStart),('browser-action',BrowserAction),('model-decision',ModelDecision),('prepared-document',GeneralDocument)]:
    (out2/(name+'.schema.json')).write_text(json.dumps(model.model_json_schema(),indent=2)+'\n',encoding='utf-8')
print('Exported general browser/model contracts')
from server.conversation_bridge import Interrupt,CitizenReply,Question,DeliveryClaim,DeliveryAck,Notification
for name,model in [('conversation-interrupt',Interrupt),('citizen-reply',CitizenReply),('citizen-question',Question),('delivery-claim',DeliveryClaim),('delivery-ack',DeliveryAck),('conversation-notification',Notification)]:
    (out2/(name+'.schema.json')).write_text(json.dumps(model.model_json_schema(),indent=2)+'\n',encoding='utf-8')
print('Exported core conversation transport contracts')
