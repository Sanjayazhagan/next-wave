"""Local core/WhatsApp stand-in. Never sends an external message."""
import json
import os
import urllib.request
from pathlib import Path

base = os.getenv('BASE_URL', 'http://127.0.0.1:8100').rstrip('/')
config_path=Path(__file__).resolve().parents[1]/'data'/'local-config.json'
config=json.loads(config_path.read_text(encoding='utf-8')) if config_path.exists() else {}
key = os.getenv('INTERNAL_KEY', config.get('INTERNAL_KEY','demo-worker-key-change-before-production'))


def call(path, body):
    req = urllib.request.Request(base+path, data=json.dumps(body).encode(), headers={
        'Content-Type': 'application/json', 'X-Internal-Key': key})
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.load(r)


session = call('/api/sessions', {'consent': True})
call(f'/api/sessions/{session["id"]}/otp', {'otp': '246810'})
task = call('/integration/v1/human-tasks', {'session_id': session['id']})
print('LOCAL SIMULATOR — no WhatsApp message sent')
print('Complete verification:', base+task['assistance_path'])
print('Session:', session['id'])
print('Core resumes from the human_task_completed audit event; this simulator stops at the handoff.')
