"""Independent synthetic pages used to verify general browser tools."""
from fastapi import APIRouter
from fastapi.responses import FileResponse,HTMLResponse
from pathlib import Path
router=APIRouter()

@router.get('/browser-lab/frame')
async def frame():return HTMLResponse('<!doctype html><html><body><label for="note">Supporting reference note</label><input id="note" name="reference"></body></html>')

@router.get('/browser-lab/help')
async def help_page():return HTMLResponse('<!doctype html><html><head><title>Lab guidance</title></head><body><h1>Guidance</h1><p>Use verified information only. This is synthetic guidance.</p></body></html>')

@router.get('/browser-lab/{step}')
async def lab(step:str):return FileResponse(Path(__file__).resolve().parents[1]/'web'/'browser_lab.html')
