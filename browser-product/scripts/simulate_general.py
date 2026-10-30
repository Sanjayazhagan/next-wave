"""Create a synthetic general-browser context for inspection. No AI is called."""
import asyncio
import json
import os
from pathlib import Path
import sys
import uuid
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from clients.general_browser import GeneralBrowserClient
from browser.protocol import ContextStart


async def main():
    root=Path(__file__).resolve().parents[1];config=root/'data'/'local-config.json'
    settings=json.loads(config.read_text(encoding='utf-8')) if config.exists() else {}
    key=os.getenv('INTERNAL_KEY',settings.get('INTERNAL_KEY','demo-worker-key-change-before-production'))
    base=os.getenv('BASE_URL','http://127.0.0.1:8100').rstrip('/')
    async with GeneralBrowserClient(base,key) as browser:
        created=await browser.create(ContextStart(request_id=str(uuid.uuid4()),subject='synthetic-core-simulator',consent_ref='synthetic-consent',url=base+'/browser-lab/application'))
        observation=created['observation']
        print('SYNTHETIC FRAMEWORK DEMO — no AI/model/WhatsApp called')
        print('Discovered controls:',len(observation['elements']))
        print('Read-only viewer:',base+'/browser-workbench#'+created['id'])
        print('Core execution context:',created['id'])


if __name__=='__main__':asyncio.run(main())
