"""Check recorded synthetic demo duration and complete accelerated browser playback."""
import asyncio
import json
from pathlib import Path
from playwright.async_api import async_playwright


async def main():
    out=Path('output/demo').resolve()
    preview=out/'preview.html';preview.write_text('<!doctype html><meta charset="utf-8"><title>Synthetic local recording preview</title><video controls src="civicflow-local-demo.webm"></video>',encoding='utf-8')
    async with async_playwright() as pw:
        b=await pw.chromium.launch();page=await b.new_page();await page.goto(preview.as_uri())
        await page.wait_for_function('document.querySelector("video").readyState>=2')
        duration=await page.locator('video').evaluate('(v)=>{v.playbackRate=16;v.play();return v.duration}')
        assert 120<=duration<=180,f'Expected 2–3 minutes; got {duration}'
        await page.wait_for_function('document.querySelector("video").ended',timeout=30000)
        assert not await page.locator('video').evaluate('(v)=>v.error')
        report={'duration_seconds':duration,'full_accelerated_browser_playback':'passed','audio':'silent','scope':'actual local synthetic demo; no external WhatsApp or government application'}
        (out/'playback-check.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(report);await b.close()


if __name__=='__main__':asyncio.run(main())
