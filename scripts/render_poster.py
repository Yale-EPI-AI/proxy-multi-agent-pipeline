"""Render the single-slide poster HTML to PNG at exact Yale ePoster dimensions."""
from playwright.sync_api import sync_playwright
from pathlib import Path

ROOT = Path("/Users/samkouteili/yale/rose/epi/multi-agent")
SRC = ROOT / "presentations" / "poster_assets" / "poster.html"
OUT = ROOT / "presentations" / "poster_assets" / "poster.png"

# 40.97" × 23.04" @ 100 DPI base, rendered at 2x for sharpness
W, H = 4097, 2304

with sync_playwright() as pw:
    browser = pw.chromium.launch()
    ctx = browser.new_context(
        viewport={"width": W, "height": H},
        device_scale_factor=2,
    )
    page = ctx.new_page()
    page.goto("file://" + str(SRC))
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(1500)
    page.screenshot(path=str(OUT), clip={"x": 0, "y": 0, "width": W, "height": H})
    print(f"wrote {OUT} ({OUT.stat().st_size:,} bytes)")
    ctx.close()
    browser.close()
