"""Render poster figures to PNG via headless Chromium."""
from playwright.sync_api import sync_playwright
from pathlib import Path

ROOT = Path("/Users/samkouteili/yale/rose/epi/multi-agent")
OUT = ROOT / "presentations" / "poster_assets"
OUT.mkdir(parents=True, exist_ok=True)

JOBS = [
    # (source html, output png, viewport w, viewport h, full_page, wait_ms, clip)
    ("outputs/knowledge_graph/graph.html", "kg.png", 1800, 1400, False, 4500, None),
    ("outputs/UWD/dashboard.html",         "dashboard_UWD.png", 1400, 1800, False, 1500,
     {"x": 0, "y": 0, "width": 1400, "height": 1800}),
    ("outputs/WRR/dashboard.html",         "dashboard_WRR.png", 1400, 1800, False, 1500,
     {"x": 0, "y": 0, "width": 1400, "height": 1800}),
]

with sync_playwright() as pw:
    browser = pw.chromium.launch()
    for src, dst, w, h, full, wait_ms, clip in JOBS:
        url = "file://" + str(ROOT / src)
        ctx = browser.new_context(viewport={"width": w, "height": h}, device_scale_factor=2)
        page = ctx.new_page()
        page.goto(url)
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(wait_ms)
        out = OUT / dst
        if clip:
            page.screenshot(path=str(out), clip=clip)
        else:
            page.screenshot(path=str(out), full_page=full)
        print(f"wrote {out} ({out.stat().st_size} bytes)")
        ctx.close()
    browser.close()
