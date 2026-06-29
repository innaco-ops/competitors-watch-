#!/usr/bin/env python3
"""Capture all peer homepages to static PNGs for the Competitor Watch board.

Runs in GitHub Actions with Playwright's bundled Chromium. Scrolls each page
first so lazy / animated sections load, then takes a full-page shot. Writes:

  shots/<domain>.png         the screenshot
  shots/fingerprints.json    coarse hash per domain (change detection)
  shots/meta.json            last-updated timestamp + which changed
"""
import os, json, time, sys
from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(ROOT, "shots")
os.makedirs(OUT_DIR, exist_ok=True)

# Keep in sync with index.html SITES (ordered by traffic).
SITES = [
    {"domain": "notion.com",     "url": "https://www.notion.com"},
    {"domain": "asana.com",      "url": "https://asana.com"},
    {"domain": "clickup.com",    "url": "https://clickup.com"},
    {"domain": "airtable.com",   "url": "https://www.airtable.com"},
    {"domain": "smartsheet.com", "url": "https://www.smartsheet.com"},
]

def capture(page, url, out, width=1920):
    page.set_viewport_size({"width": width, "height": 900})
    page.goto(url, wait_until="load", timeout=90000)
    time.sleep(5)
    h = page.evaluate("document.body.scrollHeight")
    y = 0
    while y < h:
        page.evaluate(f"window.scrollTo(0,{y})")
        time.sleep(2.2)
        page.evaluate("document.querySelectorAll('video').forEach(v=>{v.muted=true;v.play&&v.play().catch(()=>{});})")
        y += 450
        h = page.evaluate("document.body.scrollHeight")
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    time.sleep(2)
    try:
        page.wait_for_function(
            "Array.from(document.images).every(i => i.complete && i.naturalWidth > 0)",
            timeout=15000)
    except Exception:
        pass
    page.evaluate("window.scrollTo(0,0)")
    time.sleep(7)
    page.screenshot(path=out, full_page=True)

def fingerprint(path):
    """Coarse hash of the image — flags layout/design changes."""
    try:
        from PIL import Image
        img = Image.open(path).convert("RGB").resize((100, 140))
        px = list(img.getdata())
        s = 0
        for i in range(0, len(px), 6):
            r, g, b = px[i]
            s += r + g + b
        return s
    except Exception:
        return None

def main():
    fp_path = os.path.join(OUT_DIR, "fingerprints.json")
    try:
        old_fp = json.load(open(fp_path))
    except Exception:
        old_fp = {}

    new_fp, changed, failed = {}, [], []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=[
            "--autoplay-policy=no-user-gesture-required",
            "--disable-features=PreloadMediaEngagementData,AutoplayIgnoreWebAudio",
            "--disable-blink-features=AutomationControlled",
        ])
        ctx = browser.new_context(
            viewport={"width": 1920, "height": 900}, device_scale_factor=1,
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
        ctx.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
        for site in SITES:
            dom, url = site["domain"], site["url"]
            out = os.path.join(OUT_DIR, f"{dom}.png")
            print(f"Capturing {dom} …", flush=True)
            page = ctx.new_page()
            try:
                capture(page, url, out)
                nfp = fingerprint(out)
                if nfp is not None:
                    new_fp[dom] = nfp
                    ofp = old_fp.get(dom)
                    if ofp is not None and abs(nfp - ofp) / max(nfp, ofp, 1) > 0.015:
                        changed.append(dom)
                print(f"  ok ({os.path.getsize(out)//1024} KB)", flush=True)
            except Exception as e:
                failed.append(dom)
                print(f"  FAILED {dom}: {e}", flush=True)
            finally:
                page.close()
        browser.close()

    for dom, v in old_fp.items():
        new_fp.setdefault(dom, v)
    json.dump(new_fp, open(fp_path, "w"), indent=2)
    json.dump({"updated": int(time.time()), "changed": changed, "failed": failed},
              open(os.path.join(OUT_DIR, "meta.json"), "w"), indent=2)
    print(f"Done. changed={changed} failed={failed}", flush=True)
    if len(failed) == len(SITES):
        sys.exit(1)

if __name__ == "__main__":
    main()
