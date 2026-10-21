import sys, asyncio
from pathlib import Path
from playwright.async_api import async_playwright

async def main(html, out, w, h, scale):
    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await b.new_page(viewport={"width": w, "height": h}, device_scale_factor=scale)
        await pg.goto(Path(html).resolve().as_uri())
        await pg.wait_for_load_state("networkidle")
        await pg.wait_for_timeout(500)
        await pg.screenshot(path=out, full_page=False)
        await b.close()

asyncio.run(main(sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), float(sys.argv[5])))
