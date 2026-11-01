import asyncio
from fastapi import HTTPException
from browser.general import origin
from browser.step_policy import final_path

async def scoped_interaction(ctx,locator,intent,post_target=None):
    """Permit a vetted write during this single observed click only.

    Auth challenges are same-origin scoped. A dedicated upload form instead
    binds to the exact observed POST URL (never an arbitrary same-origin POST).
    Final-submission network paths are denied in either case.
    """
    try:
        scope_origin=origin(ctx.page.url)
        if intent=='upload_form':
            if not post_target or origin(post_target)!=scope_origin or final_path(post_target):
                raise HTTPException(403,'Upload target needs a reviewed portal adapter')
            ctx.write_scope=(scope_origin,intent,post_target.split('#',1)[0].split('?',1)[0])
            ctx.write_event=asyncio.Event()
        else:ctx.write_scope=(scope_origin,intent)
    except ValueError:ctx.write_scope=None  # in-memory about:blank test fixture only
    try:
        await locator.click(timeout=8000)
        if intent=='upload_form' and ctx.write_event:
            try:await asyncio.wait_for(ctx.write_event.wait(),1)
            except asyncio.TimeoutError:pass
    finally:
        ctx.write_scope=None;ctx.write_event=None

