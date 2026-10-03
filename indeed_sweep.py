"""Indeed sweep via Playwright. DE + UK, last 7 days, remote filter.

Writes indeed_jobs.md with title, company, loc, url, snippet.
Headless first; falls back to headed if Cloudflare challenge detected.
"""
import re
import time
import urllib.parse
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(__file__).with_name("indeed_jobs.md")
REMOTE_SC = "sc=0kf%3Aattr%28DSQF7%29%3B"

DE_QUERIES = ["junior developer", "junior softwareentwickler", "junior support",
              "junior datenanalyst", "junior qa testautomation", "testautomatisierung junior",
              "junior python entwickler", "it support junior homeoffice", "junior automation"]
UK_QUERIES = ["junior developer", "junior data analyst", "junior qa", "junior customer support"]

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


def search_url(domain, q, page):
    qs = urllib.parse.quote(q)
    base = f"https://{domain}/jobs?q={qs}&l="
    if domain.startswith("uk."):
        base += "Remote"
    else:
        base += "Deutschland"
    base += f"&{REMOTE_SC}&fromage=7"
    if page > 0:
        base += f"&start={page * 10}"
    return base


def dismiss_consent(page):
    try:
        for frame in page.frames:
            if "consent" in frame.url or "fundingchoices" in frame.url or "sparrow" in frame.url:
                for sel in ["button:has-text('Alle ablehnen')", "button:has-text('Reject all')",
                            "button:has-text('Ablehnen')", "button:has-text('Reject')",
                            "button[aria-label*='reject']", "button[aria-label*='ablehnen']"]:
                    try:
                        btn = frame.locator(sel).first
                        if btn.is_visible(timeout=800):
                            btn.click(timeout=2000)
                            page.wait_for_timeout(1500)
                            return
                    except Exception:
                        continue
    except Exception:
        pass


def is_challenge(page):
    t = page.title().lower()
    return "moment" in t or "attention required" in t or "verify" in t


def scrape_query(page, domain, q, results, seen):
    for pg in range(2):
        url = search_url(domain, q, pg)
        try:
            page.goto(url, timeout=45000, wait_until="domcontentloaded")
        except Exception:
            continue
        page.wait_for_timeout(2500)
        if is_challenge(page):
            return "challenge"
        dismiss_consent(page)
        page.wait_for_timeout(1000)
        # organic cards; sponsored promoted cards have jk too - keep, they are real jobs
        cards = page.locator("div.job_seen_jobpay, td.resultContent, div[class*='jobCard']").all()
        if not cards:
            cards = page.locator("li.css-5lfssd, div.css-150v3x0").all()
        n = 0
        for card in cards[:25]:
            try:
                a = card.locator("a.jcs-JobTitle, h2.jobTitle a, a[data-testid='jobTitle'], h2 a").first
                if not a.count():
                    continue
                href = a.get_attribute("href") or ""
                if not href:
                    continue
                if href.startswith("/"):
                    href = f"https://{domain}{href}"
                m = re.search(r"jk=([0-9a-f]+)", href)
                jk = m.group(1) if m else href
                if jk in seen:
                    continue
                title = (a.inner_text() or "").strip()
                comp = ""
                for sel in ["[data-testid='company-name']", ".companyName", "[class*='companyName']"]:
                    loc_c = card.locator(sel)
                    if loc_c.count():
                        comp = (loc_c.first.inner_text() or "").strip()
                        break
                loc = ""
                for sel in ["[data-testid='text-location']", "[class*='companyLocation']"]:
                    loc_l = card.locator(sel)
                    if loc_l.count():
                        loc = (loc_l.first.inner_text() or "").strip()
                        break
                snip = (card.inner_text() or "")[:400].replace("\n", " | ")
                if title and jk not in seen:
                    seen.add(jk)
                    results.append({"title": title, "company": comp, "loc": loc,
                                    "url": href, "snip": snip, "src": domain, "q": q})
                    n += 1
            except Exception:
                continue
        if n == 0:
            break
        time.sleep(1.2)
    return "ok"


def run(headless):
    results = []
    seen = set()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless, args=["--disable-blink-features=AutomationControlled"])
        ctx = browser.new_context(user_agent=UA, viewport={"width": 1280, "height": 900},
                                   locale="de-DE")
        page = ctx.new_page()
        status = "ok"
        for q in DE_QUERIES:
            status = scrape_query(page, "de.indeed.com", q, results, seen)
            if status == "challenge":
                break
            print(f"  de '{q}': total {len(results)}", flush=True)
        if status != "challenge":
            for q in UK_QUERIES:
                status = scrape_query(page, "uk.indeed.com", q, results, seen)
                if status == "challenge":
                    break
                print(f"  uk '{q}': total {len(results)}", flush=True)
        browser.close()
    return results, status


def main():
    results, status = run(headless=True)
    if status == "challenge":
        print("headless blocked by challenge; retrying headed", flush=True)
        results, status = run(headless=False)
    lines = [f"# INDEED SWEEP - {time.strftime('%Y-%m-%d')}", "",
             f"{len(results)} results (DE + UK, last 7 days, remote filter). status={status}", ""]
    for r in results:
        lines.append(f"### {r['title']} @ {r['company']}")
        lines.append(f"- loc: {r['loc']}")
        lines.append(f"- url: {r['url']}")
        lines.append(f"- src: {r['src']} | q: {r['q']}")
        lines.append(f"- snip: {r['snip'][:300]}")
        lines.append("")
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {OUT} with {len(results)} entries (status {status})")


if __name__ == "__main__":
    main()
