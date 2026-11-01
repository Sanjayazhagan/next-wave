import pytest
from fastapi import HTTPException
from browser.general import act,observe,signature
from tests.test_navigation_compatibility import fixture
from tests.test_extended_controls import command

@pytest.mark.asyncio
async def test_ad_insertions_preserve_target_and_click_original_node():
    async with fixture('<button onclick="window.right=true">Open article</button>') as (_,ctx,page):
        obs=await observe(ctx,screenshot=False);target=obs['elements'][0]
        await page.evaluate("document.body.insertAdjacentHTML('afterbegin','<input aria-label=Advertisement><button>Ad</button>')")
        result=await act(ctx,command(obs,'click',target),capture_screenshot=False)
        assert await page.evaluate('window.right')
        assert any(e['ref']==target['ref'] for e in result['observation']['elements'])

@pytest.mark.asyncio
async def test_replaced_dom_node_still_requires_fresh_observation():
    async with fixture('<button onclick="window.clicked=true">Choose</button>') as (_,ctx,page):
        obs=await observe(ctx,screenshot=False);target=obs['elements'][0]
        await page.evaluate("let e=document.querySelector('button');e.replaceWith(e.cloneNode(true))")
        with pytest.raises(HTTPException) as error:await act(ctx,command(obs,'click',target),capture_screenshot=False)
        assert error.value.status_code==409 and not await page.evaluate('Boolean(window.clicked)')

@pytest.mark.asyncio
async def test_delayed_link_navigation_is_in_action_effect():
    html='<a href="/article" onclick="event.preventDefault();setTimeout(()=>location.href=this.href,350)">Read article</a>'
    async with fixture(html) as (_,ctx,page):
        ctx.permitted=lambda url:url=='about:blank' or url.startswith('https://fixture.example/')
        async def serve(route):await route.fulfill(body='<h1>Article</h1>' if route.request.url.endswith('/article') else html,content_type='text/html')
        await page.route('https://fixture.example/**',serve);await page.goto('https://fixture.example/')
        obs=await observe(ctx,screenshot=False)
        result=await act(ctx,command(obs,'click',obs['elements'][0]),capture_screenshot=False)
        assert result['effect']['url_changed']
        assert result['observation']['url']=='https://fixture.example/article'

@pytest.mark.asyncio
async def test_query_destination_change_is_not_hidden_by_url_redaction():
    async with fixture('<a href="https://example.com/search?q=first">Search results</a>') as (_,ctx,page):
        obs=await observe(ctx,screenshot=False);target=obs['elements'][0]
        await page.locator('a').evaluate("e=>e.href='https://example.com/search?q=second'")
        with pytest.raises(HTTPException) as error:await act(ctx,command(obs,'click',target),capture_screenshot=False)
        assert error.value.status_code==409

@pytest.mark.asyncio
@pytest.mark.parametrize('size,expected',[('width:600px;height:400px',True),('width:1px;height:1px',False)])
async def test_visible_consent_iframe_is_reported_for_user_choice(size,expected):
    html=f'<iframe title="The Guardian consent message" style="{size}" srcdoc="Consent choice"></iframe><button>Read</button>'
    async with fixture(html) as (_,ctx,page):
        obs=await observe(ctx,screenshot=False)
        assert obs['consent_required']==expected
        if not expected:return
        assert any(s['kind']=='consent_required' for s in obs['human_signals'])
        button=next(e for e in obs['elements'] if e['label']=='Read')
        with pytest.raises(HTTPException) as error:await act(ctx,command(obs,'click',button),capture_screenshot=False)
        assert 'consent' in str(error.value.detail).lower()
