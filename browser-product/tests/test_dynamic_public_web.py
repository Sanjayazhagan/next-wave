"""Opt-in arbitrary public HTTPS navigation, without unsafe DNS/network fixtures."""
import os
import socket
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from browser.general import GeneralContext
from browser import public_web
from browser.core_compat import Open


@pytest.mark.parametrize('url', [
    'http://example.org', 'https://localhost', 'https://localhost:443',
    'https://127.0.0.1', 'https://10.1.2.3', 'https://172.17.0.1',
    'https://192.168.1.20', 'https://169.254.169.254', 'https://100.64.0.1',
    'https://[::1]/', 'https://[fc00::1]/', 'https://[fe80::1]/',
    'https://metadata.google.internal', 'https://db.local',
    'https://intranet', 'https://example.com:8443', 'https://example.com:80',
    'https://name:pass@example.com', 'file:///etc/passwd',
    'https://127.1/', 'https://0177.0.0.1/', 'https://example.com\\@evil.com',
    'https://example.com/hello world',
])
def test_rejects_non_public_destination(url):
    with pytest.raises(ValueError):
        public_web.public_url_syntax(url)


def test_valid_public_https_url_and_opt_in(monkeypatch):
    assert public_web.public_url_syntax('https://www.wikipedia.org/wiki/Python') == ('www.wikipedia.org', 443)
    monkeypatch.delenv('BROWSER_NAVIGATION_MODE', raising=False)
    assert public_web.navigation_mode() == 'allowlist'
    monkeypatch.setenv('BROWSER_NAVIGATION_MODE', 'public-web')
    assert public_web.navigation_mode() == 'public-web'
    session = GeneralContext(context=None, page=None, allowed=set(), public_web=True)
    assert session.permitted('https://www.wikipedia.org')
    assert session.permitted('https://example.org')
    assert not session.permitted('http://example.org')
    assert not session.permitted('https://localhost:8100')
    static = GeneralContext(context=None, page=None, allowed={'https://example.org:443'})
    assert static.permitted('https://example.org')
    assert not static.permitted('https://www.wikipedia.org')
    assert Open(portal_id='test').portal_id == 'test'
    assert Open(url='https://www.wikipedia.org', consent_ref='citizen-consent-12345').url


@pytest.mark.asyncio
async def test_blocks_dns_that_points_to_internal_ip(monkeypatch):
    def fake_dns(host,port,*args):
        return [(socket.AF_INET, socket.SOCK_STREAM, 0, '', ('192.168.0.1', 443))]
    monkeypatch.setattr(public_web.socket, 'getaddrinfo', fake_dns)
    with pytest.raises(HTTPException) as exc:
        await public_web.assert_public_url('https://malicious-public.example.net')
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_blocks_mixed_public_private_dns(monkeypatch):
    def fake_dns(host,port,*args):
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 0, '', ('8.8.8.8',443)),
            (socket.AF_INET, socket.SOCK_STREAM, 0, '', ('10.0.0.5',443)),
        ]
    monkeypatch.setattr(public_web.socket, 'getaddrinfo', fake_dns)
    with pytest.raises(HTTPException) as exc:
        await public_web.assert_public_url('https://redirect-target.org')
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_allows_public_dns(monkeypatch):
    def fake_dns(host,port,*args):
        return [(socket.AF_INET, socket.SOCK_STREAM, 0, '', ('8.8.8.8',443))]
    monkeypatch.setattr(public_web.socket, 'getaddrinfo', fake_dns)
    await public_web.assert_public_url('https://some-public-site.org/page')


@pytest.mark.asyncio
async def test_every_request_route_checked_and_post_rejected(monkeypatch):
    class Request:
        def __init__(self,url,method): self.url,self.method=url,method
    class Route:
        def __init__(self,url,method): self.request=Request(url,method); self.decision=None
        async def continue_(self):self.decision='allowed'
        async def abort(self,*args):self.decision='blocked'
    async def valid(url):
        if 'bad-site' in url:raise HTTPException(403,'bad DNS')
    monkeypatch.setattr('browser.general.assert_public_url',valid)
    session=GeneralContext(context=None,page=None,allowed=set(),public_web=True)
    for url,method,expected in [
        ('https://public-site.org','GET','allowed'),
        ('https://bad-site.org','GET','blocked'),
        ('https://public-site.org','POST','blocked'),
        ('https://127.0.0.1','GET','blocked'),
        ('http://public-site.org','GET','blocked'),
        ('https://public-site.org/submit','GET','blocked')
    ]:
        route=Route(url,method)
        await session.route(route)
        assert route.decision==expected, (url,method)

@pytest.mark.asyncio
async def test_core_session_accepts_dynamic_url_only_with_consent(monkeypatch):
    """No live website is required; check real HTTP contract + session bridge."""
    import asyncio
    from browser import core_compat as core
    from browser.general_routes import contexts

    class Page:
        def __init__(self):self.url='about:blank'
        async def goto(self,url,**kwargs):self.url=url
    class Context:
        def __init__(self):self.page=Page();self.closed=False
        async def new_page(self):return self.page
        async def route(self,*args):pass
        async def route_web_socket(self,*args):pass
        def on(self,*args):pass
        async def close(self):self.closed=True
    class Browser:
        async def new_context(self,**kwargs):return Context()

    fake=SimpleNamespace(MOCK_URL='http://mock:8100', sessions={},creation_lock=asyncio.Lock(),
       app=SimpleNamespace(state=SimpleNamespace(browser=Browser())),
       require_key=lambda x: None)
    monkeypatch.setattr(core,'worker',lambda:fake)
    monkeypatch.setattr(core,'observe',lambda ctx: asyncio.sleep(0))
    async def public_check(url):
        assert url == 'https://www.wikipedia.org/wiki/Python'
    monkeypatch.setattr(core,'assert_public_url',public_check)
    monkeypatch.setenv('BROWSER_NAVIGATION_MODE','public-web')
    monkeypatch.setenv('BROWSER_PORTALS_JSON','')
    with pytest.raises(HTTPException) as exc:
        await core.open_session(core.Open(url='https://www.wikipedia.org/wiki/Python'), 'service-key')
    assert exc.value.status_code == 422
    try:
        opened=await core.open_session(core.Open(url='https://www.wikipedia.org/wiki/Python',consent_ref='citizen-consent-1234'), 'service-key')
        assert opened['session_id'] in core.bridges
        info=core.bridges[opened['session_id']]
        ctx=contexts[info.context_id]
        assert ctx.public_web is True
        assert ctx.page.url=='https://www.wikipedia.org/wiki/Python'
    finally:
        if 'opened' in locals():
            await core.close(opened['session_id'], 'service-key')


@pytest.mark.asyncio
async def test_legacy_registered_open_works_in_allowlist_mode(monkeypatch):
    from browser import core_compat as core, worker as w
    monkeypatch.setenv('BROWSER_NAVIGATION_MODE','allowlist')
    monkeypatch.setenv('BROWSER_PORTALS_JSON','{"test":{"url":"https://www.wikipedia.org"}}')
    monkeypatch.setenv('BROWSER_ALLOWED_ORIGINS','https://example.org')
    with pytest.raises(HTTPException) as exc:
        await core.open_session(core.Open(portal_id='test'), w.INTERNAL_KEY)
    # This test only reaches the origin check; the worker is never contacted.
    assert exc.value.status_code==403
    with pytest.raises(HTTPException) as exc:
        await core.open_session(core.Open(url='https://www.wikipedia.org',consent_ref='citizen-consent-1234'), w.INTERNAL_KEY)
    assert exc.value.status_code==403
