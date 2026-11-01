"""Reviewed GET search forms; never a blanket exception for form submission."""
import json
import os
from urllib.parse import urlsplit
from fastapi import HTTPException

BUILTIN={('www.google.com','/search'),('www.wikipedia.org','/search-redirect.php'),('en.wikipedia.org','/w/index.php'),('www.walmart.com','/search'),('www.ikea.com','/us/en/search/'),('duckduckgo.com','/'),('www.coursera.org','/')}
HANDOFFS={('https://www.noaa.gov:443','https://search.usa.gov:443','/search')}

def search_scope(page_url,element):
    from browser.general import origin
    target=element.get('form_action','');p=urlsplit(target)
    try:source=origin(page_url);destination=origin(target)
    except ValueError:raise HTTPException(403,'Invalid search form destination') from None
    if not element.get('form_search_only') or element.get('form_method','').lower()!='get':
        raise HTTPException(403,'Search requires a reviewed GET search-only form')
    same_origin=source==destination
    handoff=(source,destination,p.path or '/') in HANDOFFS
    if not same_origin and not handoff:raise HTTPException(403,'Cross-origin search handoff is not reviewed for this source')
    try:
        entries=json.loads(os.getenv('BROWSER_SEARCH_TARGETS_JSON','[]'))
        if not isinstance(entries,list):raise ValueError()
        reviewed=set()
        for entry in entries:
            if not isinstance(entry,str):raise ValueError()
            u=urlsplit(entry)
            local_http=u.scheme=='http' and u.hostname in ('127.0.0.1','localhost')
            if u.query or u.fragment or (u.scheme!='https' and not local_http) or u.username or u.password:raise ValueError()
            reviewed.add((origin(entry),u.path or '/'))
    except (ValueError,TypeError):raise HTTPException(503,'Invalid reviewed search target configuration') from None
    if not handoff and not (same_origin and p.scheme=='https' and p.port in (None,443) and (p.hostname,p.path) in BUILTIN) and (destination,p.path or '/') not in reviewed:
        raise HTTPException(403,'Search target is not reviewed; configure BROWSER_SEARCH_TARGETS_JSON')
    return ('GET',origin(target),p.path or '/')
