"""Conservative, portal-reviewed evidence for *human-clicked* submissions.

A changed URL, HTTP 200 or an AI's guess never proves that an application
was submitted. Rules require both an exact expected confirmation URL and
literal page evidence; a separate vetted receipt pattern remains supported.
"""
import json
import os
from urllib.parse import urlsplit

from fastapi import HTTPException


# Selenium's public practice form has no receipt number. This narrow,
# hard-coded rule is only evidence for that exact synthetic test flow.
_PRACTICE_RULE = {
    'source_url': 'https://www.selenium.dev/selenium/web/web-form.html',
    'success_url': 'https://www.selenium.dev/selenium/web/submitted-form.html',
    'required_text': ['Form submitted', 'Received!'],
}


def _exact_url(value, *, allow_local=False):
    if not isinstance(value, str) or not 10 <= len(value) <= 2048:
        raise ValueError('A full, bounded URL is required')
    try:
        parts = urlsplit(value)
        host = (parts.hostname or '').lower()
        if parts.username is not None or parts.password is not None or parts.fragment:
            raise ValueError('No credentials or fragments in confirmation URLs')
        if parts.scheme == 'http':
            if not allow_local or host not in ('127.0.0.1', 'localhost'):
                raise ValueError('Only HTTPS is allowed outside local fixture tests')
        elif parts.scheme != 'https':
            raise ValueError('HTTPS required')
        if not host or any(ord(c) < 33 for c in value) or '\\' in value:
            raise ValueError('Malformed URL')
        if parts.port is not None and not (parts.scheme == 'https' and parts.port == 443) and not (parts.scheme == 'http' and allow_local):
            raise ValueError('Non-standard URL port')
    except ValueError as exc:
        raise ValueError('Invalid confirmation URL') from exc
    return parts


def reviewed_rules():
    raw = os.getenv('BROWSER_SUBMIT_CONFIRMATIONS_JSON', '[]')
    if len(raw) > 16384:
        raise HTTPException(503, 'Invalid submit confirmation registry')
    try:
        entries = json.loads(raw)
        if not isinstance(entries, list) or len(entries) > 32:
            raise ValueError()
        # HTTP loopback is for explicit local demo fixtures only, never Azure.
        allow_local = os.getenv('APP_MODE', 'demo') == 'demo' and os.getenv('SECURITY_MODE', 'local-demo') != 'signed'
        for entry in entries:
            if not isinstance(entry, dict) or set(entry) != {'source_url', 'success_url', 'required_text'}:
                raise ValueError()
            source = _exact_url(entry['source_url'], allow_local=allow_local)
            success = _exact_url(entry['success_url'], allow_local=allow_local)
            if (source.scheme, source.hostname, source.port or (443 if source.scheme == 'https' else 80)) != (success.scheme, success.hostname, success.port or (443 if success.scheme == 'https' else 80)):
                raise ValueError()
            phrases = entry['required_text']
            if not isinstance(phrases, list) or not 1 <= len(phrases) <= 5 or any(not isinstance(s, str) or not 5 <= len(s.strip()) <= 120 for s in phrases):
                raise ValueError()
    except (ValueError, TypeError, json.JSONDecodeError):
        raise HTTPException(503, 'Invalid operator submit confirmation registry') from None
    return [_PRACTICE_RULE, *entries]


def confirmation_evidence(source_url, observation, *, request_observed, changed, receipt):
    """Return public evidence label or None; no page content is returned/stored."""
    if not request_observed or not changed or observation.get('page_status', 'ready') != 'ready':
        return None
    if receipt:
        return 'reviewed_receipt'
    text = observation.get('text') or ''
    url = observation.get('url') or ''
    if not text or not url:
        return None
    # Validate operator policy even when the current page has no matching rule.
    for rule in reviewed_rules():
        if source_url == rule['source_url'] and url == rule['success_url'] and all(phrase.casefold() in text.casefold() for phrase in rule['required_text']):
            return 'reviewed_confirmation'
    return None
