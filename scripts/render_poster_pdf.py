"""Render the single-slide poster HTML directly to PDF at Yale ePoster dimensions."""
from playwright.sync_api import sync_playwright
from pathlib import Path

ROOT = Path("/Users/samkouteili/yale/rose/epi/multi-agent")
SRC = ROOT / "presentations" / "poster_assets" / "poster.html"
OUT = ROOT / "presentations" / "poster_assets" / "poster.pdf"

W_IN, H_IN = 40.97, 23.04
W_PX, H_PX = 4097, 2304

with sync_playwright() as pw:
    browser = pw.chromium.launch()
    ctx = browser.new_context(viewport={"width": W_PX, "height": H_PX})
    page = ctx.new_page()
    page.goto("file://" + str(SRC))
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(1200)
    page.emulate_media(media="print")
    page.pdf(
        path=str(OUT),
        width=f"{W_IN}in",
        height=f"{H_IN}in",
        print_background=True,
        margin={"top": "0", "right": "0", "bottom": "0", "left": "0"},
        prefer_css_page_size=False,
    )
    print(f"wrote {OUT} ({OUT.stat().st_size:,} bytes)")
    ctx.close()
    browser.close()
