"""Clearly fictional native scholarship form; stores no applicant data."""
import hashlib
import hmac
import re
import secrets
from urllib.parse import parse_qs
from fastapi import APIRouter,HTTPException,Request
from fastapi.responses import HTMLResponse,RedirectResponse

router=APIRouter(tags=['fictional practice scholarship'])
RECEIPT_PATTERN=r'Receipt: (DEMO-SCH-[A-F0-9]{12}-[A-F0-9]{32})'
STYLE='''body{font:16px system-ui,sans-serif;background:#f4f7fb;color:#18314e;margin:0;padding:24px}main{max-width:760px;margin:24px auto;background:white;border-radius:16px;padding:32px;box-shadow:0 8px 30px #17314e12}h1{font-size:28px;margin:12px 0}.brand{font-weight:700;color:#2459b9}.notice{background:#fff2cb;padding:16px;border-radius:8px;line-height:1.5}.grid{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin:24px 0}label{display:block;font-weight:600}input:not([type=checkbox]),select{display:block;box-sizing:border-box;width:100%;padding:11px;border:1px solid #aebbcf;border-radius:6px;margin-top:8px;font:inherit}.check{display:flex;gap:10px;align-items:flex-start;font-weight:400}button{margin-top:24px;background:#2459b9;border:0;border-radius:8px;color:white;font:600 16px system-ui;padding:14px 24px}.receipt{font:600 17px monospace;overflow-wrap:anywhere;background:#eef4ff;padding:18px;border-radius:8px}p{line-height:1.5}@media(max-width:540px){body{padding:10px}main{padding:20px}.grid{grid-template-columns:1fr}}'''

def page(title,body):
    return HTMLResponse(f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title><style>{STYLE}</style></head><body><main><div class="brand">GradientZero Â· Practice portal</div>{body}</main></body></html>',headers={'Cache-Control':'no-store','Content-Security-Policy':"default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'"})

@router.get('/practice/scholarship')
async def form():
    return page('Mock scholarship application','''<h1>Mock scholarship application</h1><p class="notice"><strong>Practice only.</strong> This is not a real scholarship application. Use made-up details only. No eligibility decision is made and no applicant data is saved.</p><form action="/practice/scholarship/submit" method="post"><div class="grid"><label>Applicant name<input name="name" maxlength="80" required placeholder="Demo Student"></label><label>Email address<input name="email" type="email" maxlength="100" required placeholder="demo@example.invalid"></label><label>Age<input name="age" type="number" min="16" max="100" required></label><label>Annual household income<input name="income" type="number" min="0" max="100000000" required></label><label>Course<select name="course" aria-label="Course" required><option value="">Choose a course</option><option value="diploma">Diploma</option><option value="degree">Undergraduate degree</option></select></label></div><label class="check"><input name="synthetic" type="checkbox" value="yes" required> I am using synthetic details for this practice application.</label><button type="submit">Submit Application</button></form>''')

def sign(identifier):
    from server.app import SIGN_KEY
    return hmac.new(SIGN_KEY.encode(),('practice-scholarship:'+identifier).encode(),hashlib.sha256).hexdigest()[:32].upper()

@router.post('/practice/scholarship/submit')
async def submit(request:Request):
    if request.headers.get('content-type','').split(';')[0].strip()!='application/x-www-form-urlencoded':raise HTTPException(415,'Use the practice form')
    raw=await request.body()
    if len(raw)>8192:raise HTTPException(413,'Practice form too large')
    try:
        fields=parse_qs(raw.decode('utf-8'),keep_blank_values=True,strict_parsing=True,max_num_fields=6)
        if set(fields)!={'name','email','age','income','course','synthetic'} or any(len(v)!=1 for v in fields.values()):raise ValueError()
        values={k:v[0] for k,v in fields.items()}
        if not 1<=len(values['name'].strip())<=80 or not re.fullmatch(r'[^\s@]{1,60}@[^\s@]{1,90}',values['email']) or len(values['email'])>100:raise ValueError()
        if not 16<=int(values['age'])<=100 or not 0<=int(values['income'])<=100000000:raise ValueError()
        if values['course'] not in ('diploma','degree') or values['synthetic']!='yes':raise ValueError()
    except (ValueError,UnicodeError):raise HTTPException(422,'Complete all practice fields with synthetic details') from None
    identifier=secrets.token_hex(6).upper();receipt=f'DEMO-SCH-{identifier}-{sign(identifier)}'
    return RedirectResponse('/practice/scholarship/receipt/'+receipt,status_code=303)

@router.get('/practice/scholarship/receipt/{receipt}')
async def receipt_page(receipt:str):
    match=re.fullmatch(r'DEMO-SCH-([A-F0-9]{12})-([A-F0-9]{32})',receipt)
    if not match or not hmac.compare_digest(match[2],sign(match[1])):raise HTTPException(404,'Practice receipt not found')
    return page('Practice scholarship receipt',f'<h1>Application successfully submitted</h1><p class="notice">This confirms the fictional practice form only. No real scholarship application was sent and no applicant data was saved.</p><p class="receipt">Receipt: {receipt}</p><p>You can return to the bot with this practice receipt.</p>')
