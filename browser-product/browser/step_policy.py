"""Conservative, context-aware intent labels for observed browser controls.

Heuristics help decide which workflow to request; they are NOT authority for a
final submission, payment, or unrestricted POST. Unknown submit buttons fail closed.
"""
import re
from urllib.parse import urlsplit

OTP_SEND = re.compile(r'\b(?:send|resend|request|get|generate)\s+(?:an?\s+)?(?:otp|one[ -]?time(?:\s+password|\s+code)?|verification\s+code|security\s+code|login\s+code)\b|\bsend\s+code\b', re.I)
CAPTCHA_REFRESH = re.compile(r'\b(?:refresh|reload|new|regenerate|change)\b.{0,32}\b(?:captcha|security\s+image|verification\s+image)\b|\b(?:captcha|security\s+image)\b.{0,32}\b(?:refresh|reload|new|change)\b', re.I)
OTP_VERIFY = re.compile(r'\b(?:verify|validate|check|confirm)\s+(?:the\s+)?(?:otp|one[ -]?time\s+code|verification\s+code|security\s+code|code)\b', re.I)
UPLOAD = re.compile(r'\b(?:upload|attach|send\s+document|save\s+document|add\s+attachment)\b', re.I)
INTERMEDIATE = re.compile(r'^(?:next(?:\s+step)?|continue|proceed|go\s+back|previous|back|save(?:\s+(?:draft|and\s+(?:next|continue)|&\s+continue))?|save\s+&\s+next)$', re.I)
FINAL = re.compile(r'\b(?:submit|finali[sz]e|complete\s+application|send\s+application|confirm\s+application|approve\s+application|pay(?:ment)?|purchase|buy\s+now|withdraw|delete|remove\s+account|apply\s+now|register\s+account)\b', re.I)
RISKY_PATH = re.compile(r'(?:^|/)(?:submit|finali[sz]e|payment|pay|purchase|withdraw|delete|approve|complete-application)(?:/|$)', re.I)
AUTH_INPUT = re.compile(r'\b(?:otp|captcha|one[ -]?time|verification\s+code|security\s+code|password|face\s+auth)\b', re.I)


def category(control: dict, *, has_file=False, has_auth=False) -> str:
    label = str(control.get('label') or control.get('name') or '').strip()
    kind = str(control.get('type') or '').lower()
    tag = str(control.get('tag') or '').lower()
    href = str(control.get('href') or '')
    action = str(control.get('form_action') or '')
    if kind in ('password',) or (tag in ('input','textarea') and AUTH_INPUT.search(label + ' ' + str(control.get('autocomplete') or ''))):
        return 'human_input'
    if kind == 'file':
        return 'file_input'
    if tag not in ('a','button','input') and control.get('role') not in ('button','link'):
        return 'ordinary'
    # A plain Submit button can belong to a *dedicated document-only upload form*.
    # This evidence is calculated for the submitter's own form, never for some
    # unrelated file input elsewhere on the page. Only an observed upload-path
    # POST, without other user-entry fields or final-application wording,
    # qualifies. Core still checks an attached file and scopes the POST.
    if (label.lower() in ('submit', 'submit file', 'submit upload')
            and control.get('form_upload_only') and control.get('form_has_file')
            and not RISKY_PATH.search(urlsplit(action).path)):
        return 'upload_step'
    if FINAL.search(label) or RISKY_PATH.search(urlsplit(href).path) or RISKY_PATH.search(urlsplit(action).path):
        return 'final'
    if CAPTCHA_REFRESH.search(label):
        return 'captcha_refresh'
    if OTP_SEND.search(label) and (has_auth or re.search(r'otp|verification|login',label,re.I)):
        return 'otp_send'
    if OTP_VERIFY.search(label) and has_auth:
        return 'otp_verify'
    if UPLOAD.search(label) and has_file:
        return 'upload_step'
    if INTERMEDIATE.fullmatch(label):
        return 'intermediate'
    # A nameless type=submit must never be assumed to be a harmless intermediate.
    if kind in ('submit','image') or (tag=='button' and control.get('form') and kind not in ('button','reset')):
        return 'final_unknown'
    return 'ordinary'


def final_path(url:str)->bool:
    return bool(RISKY_PATH.search(urlsplit(url).path))
