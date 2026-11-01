"""Explicitly reviewed native-form target; never a wildcard submit permission."""
import asyncio
import json
import os
from urllib.parse import urlsplit
from fastapi import HTTPException
from browser.general import origin


def reviewed_target(page_url,element):
    target=element.get('form_action','');method=element.get('form_method','').upper()
    if not element.get('form_state_complete',True):raise HTTPException(403,'Large hidden form state requires a reviewed portal adapter')
    if not element.get('form') or method not in ('GET','POST'):
        raise HTTPException(403,'Final action needs a reviewed portal adapter')
    try:
        if origin(page_url)!=origin(target):raise ValueError()
        entries=json.loads(os.getenv('BROWSER_FINAL_SUBMIT_TARGETS_JSON','[]'))
        if not isinstance(entries,list):raise ValueError()
        for entry in entries:
            if not isinstance(entry,dict) or entry.get('method') not in ('GET','POST'):raise ValueError()
            configured=entry.get('url','');parsed=urlsplit(configured)
            if parsed.query or parsed.fragment:raise ValueError()
            if (origin(configured),parsed.path or '/',entry['method'])==(origin(target),urlsplit(target).path or '/',method):
                return (method,origin(target),urlsplit(target).path or '/')
    except (ValueError,TypeError):raise HTTPException(503,'Invalid operator native-submit registry')
    raise HTTPException(403,'Final submission requires an operator-reviewed exact native target or portal adapter')


async def click_reviewed_submit(ctx,locator,scope):
    ctx.native_submit_scope=scope;ctx.native_submit_event=asyncio.Event()
    try:
        await locator.click(timeout=8000)
        try:await asyncio.wait_for(ctx.native_submit_event.wait(),2)
        except asyncio.TimeoutError:return False
        return True
    finally:
        ctx.native_submit_scope=None;ctx.native_submit_event=None
