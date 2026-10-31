"""Public privacy policy, which Meta requires before an app can be published."""
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()

PRIVACY_POLICY = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>GradientZero Privacy Policy</title>
<style>
body { font-family: system-ui, sans-serif; line-height: 1.6; color: #1a1a1a;
       background: #fff; max-width: 42rem; margin: 2rem auto; padding: 0 1rem; }
h1 { font-size: 1.6rem; } h2 { font-size: 1.1rem; margin-top: 1.5rem; }
</style>
</head>
<body>
<h1>GradientZero Privacy Policy</h1>
<p>Last updated: 31 October 2026</p>
<p>GradientZero is an assistant that helps people apply for government schemes over
chat apps. It is a student project built for the Forge '26 hackathon.</p>

<h2>What we collect</h2>
<p>With your consent, we collect the messages, voice notes and documents you send us,
your phone number or chat ID, your answers to eligibility questions, your portal login
ID, and application receipts.</p>

<h2>How we use it</h2>
<p>We use this information only to fill in scheme applications for you and to send you
their status. We show you the application before anything is submitted. We do not sell
your information or use it for advertising.</p>

<h2>Who else processes it</h2>
<ul>
<li>Telegram or Meta processes messages, because they travel over Telegram or
WhatsApp.</li>
<li>AI model providers receive your chat messages, including details you share such as
your state, course, income and community, so the assistant can reply. ID numbers,
phone numbers and email addresses are masked first. Some providers may keep or learn
from this text, so please do not share anything you want kept private in the chat.</li>
<li>AI model providers also receive photos of the documents you send, so details can be
read from them. We blur Aadhaar and bank numbers first, but this depends on our software
finding them, so a number could be missed. Names, income, community and other printed
details are not blurred.</li>
<li>AI model providers also receive page structure and field names to plan each portal
step. They do not receive the personal values typed into portals. OTPs, CAPTCHA
answers, passwords and portal logins are never sent to them.</li>
<li>Translation and speech providers process voice notes and text in your language.</li>
<li>Government portals receive the details you approve for your application.</li>
</ul>

<h2>How we protect it</h2>
<p>Documents, portal IDs, receipts and saved session data are encrypted when stored.
The blurred working copy of a document is deleted as soon as it has been read. Message
text is not written to our logs.</p>

<h2>Your choices</h2>
<p>Reply STOP at any time to end a session. To have your data deleted, send us a
message asking for deletion and we will remove it.</p>
</body>
</html>
"""


@router.get("/privacy", response_class=HTMLResponse)
def privacy_policy() -> str:
    return PRIVACY_POLICY
