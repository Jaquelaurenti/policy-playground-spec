import asyncio
from pathlib import Path
from playwright.async_api import async_playwright
S="/tmp/claude-0/-home-claude/4c9ae48c-10e9-5678-8681-628a8f13dac5/scratchpad"
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(); pg = await b.new_page(viewport={"width":1500,"height":1100}, device_scale_factor=1.3)
        await pg.goto(Path(f"{S}/sim/_wrapped.html").resolve().as_uri()); await pg.wait_for_timeout(1200)
        await pg.screenshot(path=f"{S}/video/shots/desk.png", clip={"x":0,"y":172,"width":1500,"height":660})
        await pg.click("#tab-load"); await pg.click("[data-preset=normal]"); await pg.wait_for_timeout(400)
        await pg.screenshot(path=f"{S}/video/shots/load.png", clip={"x":0,"y":150,"width":1500,"height":660})
        await b.close()
asyncio.run(main())
