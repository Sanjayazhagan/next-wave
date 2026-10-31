"""Read-only navigation probe inside the same Playwright container as production.

Example:
  docker compose -f compose.yaml -f compose.integrated.yaml exec worker \
      python scripts/diagnose_browser_navigation.py https://the-internet.herokuapp.com/upload

Runs no forms and preserves production's public-web route and DNS checks.
Printed output strips query strings, fragments, body content, and credentials.
"""
import asyncio
import json
import os
import sys
import time
from urllib.parse import urlsplit, urlunsplit

from playwright.async_api import async_playwright, TimeoutError as PWTimeout
from browser.general import GeneralContext
from browser.public_web import assert_public_url


def label(url: str) -> str:
    p = urlsplit(url)
    return urlunsplit((p.scheme,p.hostname or '',p.path[:120],'',''))


async def diagnose(url):
    await assert_public_url(url)
    events=[]
    start=time.monotonic()
    async with async_playwright() as pw:
        browser_args=['--no-sandbox','--disable-dev-shm-usage']
        if os.getenv('CHROMIUM_DISABLE_HTTP2','false').strip().lower() in ('1','true','yes','on'):
            browser_args.append('--disable-http2')
        launch={'headless':True,'args':browser_args}
        if os.getenv('CHROMIUM_PATH'):launch['executable_path']=os.getenv('CHROMIUM_PATH')
        browser=await pw.chromium.launch(**launch)
        ctx=await browser.new_context(accept_downloads=False,service_workers='block')
        page=await ctx.new_page()
        session=GeneralContext(context=ctx,page=page,allowed=set(),public_web=True)
        await ctx.route('**/*',session.route)
        def failed(req):
            if len(events)<25:
                events.append({'kind':'requestfailed','method':req.method,'url':label(req.url),'failure':req.failure})
        ctx.on('requestfailed',failed)
        status=None;problem=None
        try:
            response=await page.goto(url,wait_until='domcontentloaded',timeout=20000)
            status=response.status if response else None
        except PWTimeout:
            problem='navigation_timed_out_20s'
        except Exception as e:
            problem=f'navigation_exception_{type(e).__name__}'
        result={'requested':label(url),'current_page':label(page.url), 'main_status':status,
                'elapsed_seconds':round(time.monotonic()-start,1),'problem':problem,
                'page_has_body': bool(await page.locator('body').count()), 'request_failures':events}
        await ctx.close();await browser.close()
    print(json.dumps(result,indent=2))
    return 0 if not problem else 1


if __name__=='__main__':
    if len(sys.argv)!=2:
        raise SystemExit('Usage: python scripts/diagnose_browser_navigation.py https://public.example/path')
    raise SystemExit(asyncio.run(diagnose(sys.argv[1])))
