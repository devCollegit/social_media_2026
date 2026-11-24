"""HTML 발표자료 → PDF (슬라이드 한 장 = 1쪽, 1280×720, 배경색 유지, 글꼴 내장)
사용: cd presentation && uv run --quiet --with playwright python export_pdf.py"""
import os
from playwright.sync_api import sync_playwright
HERE = os.path.dirname(os.path.abspath(__file__)); NAME = "토스증권_공포탐욕지수_발표"
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1280, "height": 720})
    pg.goto("file://" + os.path.join(HERE, NAME + ".html")); pg.wait_for_load_state("networkidle")
    pg.evaluate("document.fonts.ready")
    pg.emulate_media(media="print")
    pg.pdf(path=os.path.join(HERE, NAME + ".pdf"), width="1280px", height="720px", print_background=True, margin={"top": "0", "bottom": "0", "left": "0", "right": "0"})
    b.close()
print("ok")
