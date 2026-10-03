"""StepStone sweep via Playwright. DE, job search, JSON-LD + DOM extraction.

Writes stepstone_jobs.md. Headless first; headed fallback on challenge.
Debug output lets you iterate selectors without guessing.
"""
import json
import re
import time
import urllib.parse
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(__file__).with_name("stepstone_jobs.md")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

QUERIES = ["junior developer", "junior softwareentwickler", "testautomation junior",
           "datenanalyst junior", "python junior entwickler", "it support junior",
           "junior automation engineer", "junior data engineer"]

BASE = "https://www.stepstone.de/jobs/?q={q}&loc=Deutschland&wsr=Deuschland"


def dismiss_consent(page):
    for sel in ["button#ccpConfirm", "button:has-text('Alle akzeptieren')",
                "button:has-text('Alle auswaehlen')", "button:has-text('Accept all')",
                "button:has-text('Auswahl speichern')", "button[data-testid='accept-all']"]:
        try:
            btn = page.locator(sel).first
            if btn.is_visible(timeout=800):
                btn.click(timeout=2000)
                page.wait_for_timeout(1200)
                return True
        except Exception:
            continue
    return False


def extract_ld_json(html):
    jobs = []
    for m in re.finditer(r'<script type="application/ld\+json">(.*?)</script>', html, re.S):
        try:
            data = json.loads(m.group(1))
        except Exception:
            continue
        items = data.get("itemListElement", []) if isinstance(data, dict) else data
        if not isinstance(items, list):
            continue
        for e in items:
            item = e.get("item", e) if isinstance(e, dict) else None
            if not isinstance(item, dict) or item.get("@type") not in ("JobPosting", None):
                continue
            if item.get("@type") != "JobPosting" and "title" not in item:
                continue
            loc = item.get("jobLocation") or {}
            if isinstance(loc, list):
                loc = loc[0] if loc else {}
            addr = loc.get("address", {}) if isinstance(loc, dict) else {}
            jobs.append({
                "title": item.get("title", ""),
                "company": (item.get("hiringOrganization") or {}).get("name", ""),
                "loc": addr.get("addressLocality", "") or "",
                "url": item.get("url", ""),
            })
    return jobs


def extract_dom(page):
    jobs = []
    cards = page.locator("article, [data-testid*='job'], li[class*='job']").all()
    for card in cards[:40]:
        try:
            a = card.locator("a[href*='stellenangebot'], a[href*='/jobs/']").first
            if not a.count():
                continue
            href = a.get_attribute("href") or ""
            if "stellenangebote" not in href:
                continue
            if href.startswith("/"):
                href = "https://www.stepstone.de" + href
            raw = a.inner_text().strip()
            if not raw:
                continue
            first_line = raw.split("\n")[0].strip()[:120]
            c = card.locator("[class*='company'], [data-testid*='company'], cite, h2 + div").first
            company = ""
            if c.count():
                company = c.inner_text().strip().split("\n")[0][:80]
            jobs.append({"title": first_line,
                         "company": company,
                         "loc": "",
                         "url": href.split("?")[0]})
        except Exception:
            continue
    return jobs


def run(headless):
    results, seen = [], set()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless,
                                   args=["--disable-blink-features=AutomationControlled"])
        ctx = browser.new_context(user_agent=UA, viewport={"width": 1280, "height": 900},
                                   locale="de-DE")
        page = ctx.new_page()
        status = "ok"
        for q in QUERIES:
            url = BASE.format(q=urllib.parse.quote(q))
            try:
                page.goto(url, timeout=45000, wait_until="domcontentloaded")
            except Exception as e:
                print(f"  goto fail: {str(e)[:60]}", flush=True)
                continue
            page.wait_for_timeout(3000)
            if "login" in page.url or "robot" in page.title().lower():
                status = "blocked"
                break
            dismiss_consent(page)
            page.wait_for_timeout(1500)

            html = page.content()
            ld = extract_ld_json(html)
            n_ld = 0
            for j in ld:
                key = j["url"].split("?")[0]
                if key and key not in seen and j["title"]:
                    seen.add(key)
                    results.append({**j, "src": "ld+json", "q": q})
                    n_ld += 1
            n_dom = 0
            if not ld:
                for j in extract_dom(page):
                    if j["url"] not in seen:
                        seen.add(j["url"])
                        results.append({**j, "src": "dom", "q": q})
                        n_dom += 1
            print(f"  '{q}': ld {n_ld}, dom {n_dom}, total {len(results)} | title={page.title()[:50]}", flush=True)
            time.sleep(1.5)
        browser.close()
    return results, status


def main():
    results, status = run(headless=True)
    if status == "blocked" or not results:
        print("headless empty/blocked; retrying headed", flush=True)
        results, status = run(headless=False)
    lines = [f"# STEPSTONE SWEEP - {time.strftime('%Y-%m-%d')}", "",
             f"{len(results)} results. status={status}", ""]
    for r in results:
        lines.append(f"### {r['title'][:100]} @ {r['company']}")
        lines.append(f"- loc: {r['loc']}")
        lines.append(f"- url: {r['url']}")
        lines.append(f"- src: {r['src']} | q: {r['q']}")
        lines.append("")
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {OUT} with {len(results)} entries (status {status})")


if __name__ == "__main__":
    main()
