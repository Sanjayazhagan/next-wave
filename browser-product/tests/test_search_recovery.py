import pytest
from fastapi import HTTPException
from browser.search import search_scope
from browser.general import observe,act
from tests.test_navigation_compatibility import fixture
from tests.test_extended_controls import command

@pytest.mark.parametrize('page,target',[
 ('https://www.walmart.com/','https://www.walmart.com/search'),
 ('https://www.ikea.com/us/en/','https://www.ikea.com/us/en/search/'),
 ('https://duckduckgo.com/','https://duckduckgo.com/'),
 ('https://www.coursera.org/','https://www.coursera.org/'),
 ('https://www.noaa.gov/','https://search.usa.gov/search')])
def test_reviewed_search_destinations_are_get_only_and_source_bound(page,target):
    e={'form_search_only':True,'form_method':'get','form_action':target}
    assert search_scope(page,e)[0]=='GET'
    with pytest.raises(HTTPException):search_scope(page,{**e,'form_method':'post'})
    with pytest.raises(HTTPException):search_scope('https://unrelated.example/',e)

@pytest.mark.asyncio
async def test_blur_releases_autocomplete_and_exposes_obstruction():
    html='''<input aria-label="Search" onfocus="document.querySelector('[role=listbox]').hidden=false" onblur="document.querySelector('[role=listbox]').hidden=true"><div role="listbox" hidden style="position:fixed;inset:0;z-index:100;background:white">Suggestions</div><button onclick="window.clicked=true">Read article</button>'''
    async with fixture(html) as (_,ctx,page):
        await page.locator('input').focus()
        obs=await observe(ctx,screenshot=False)
        assert any(o['role']=='listbox' for o in obs['interaction_state']['overlays'])
        button=next(e for e in obs['elements'] if e['label']=='Read article')
        assert button['occluded'] and button['blocker']
        field=next(e for e in obs['elements'] if e['tag']=='input')
        result=await act(ctx,command(obs,'blur',field),capture_screenshot=False)
        assert not result['observation']['interaction_state']['overlays']
        button=next(e for e in result['observation']['elements'] if e['label']=='Read article')
        await act(ctx,command(result['observation'],'click',button),capture_screenshot=False)
        assert await page.evaluate('window.clicked')

@pytest.mark.asyncio
async def test_blur_does_not_allow_human_auth_fields():
    async with fixture('<input type=password aria-label=Password>') as (_,ctx,page):
        obs=await observe(ctx,screenshot=False)
        with pytest.raises(HTTPException) as error:await act(ctx,command(obs,'blur',obs['elements'][0]),capture_screenshot=False)
        assert error.value.status_code==403
