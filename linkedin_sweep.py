"""LinkedIn sweep. Guest API first, Playwright fallback.

Writes linkedin_jobs.md. Guest endpoint: /jobs-guest/jobs/api/seeMoreJobPostings/search
f_WT=2 (remote), f_TPR=r604800 (past week).
"""
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

OUT = Path(__file__).with_name("linkedin_jobs.md")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

QUERIES = ["junior software engineer", "junior developer", "junior data analyst",
           "test automation engineer junior", "junior qa", "IT support junior",
           "python junior developer", "junior automation engineer",
           "junior application support", "junior business analyst"]
LOCATION = "Germany"


def clean(s):
    s = re.sub(r"<[^>]+>", " ", s or "")
    return re.sub(r"\s+", " ", s).strip()


def guest_fetch(term, start):
    qs = urllib.parse.quote(term)
    url = (f"https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
           f"?keywords={qs}&location={urllib.parse.quote(LOCATION)}"
           f"&f_TPR=r604800&f_WT=2&start={start}")
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Accept": "text/html", "Accept-Language": "en-US,en;q=0.9"})
    return urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace")


def parse_cards(html, results, seen):
    n = 0
    for m in re.finditer(r'<li class="[^"]*base-card[^"]*"[^>]*>(.*?)</li>', html, re.S):
        card = m.group(1)
        t = re.search(r'<h3[^>]*base-search-card__title[^>]*>(.*?)</h3>', card, re.S)
        c = re.search(r'<h4[^>]*base-search-card__subtitle[^>]*>(.*?)</h4>', card, re.S)
        l = re.search(r'<span[^>]*job-search-card__location[^>]*>(.*?)</span>', card, re.S)
        a = re.search(r'<a[^>]*base-card__full-link[^>]*href="([^"]+)"', card, re.S)
        d = re.search(r'datetime="([^"]+)"', card)
        if not t or not a:
            continue
        title = clean(t.group(1))
        link = a.group(1).split("?")[0]
        key = re.search(r"(/jobs/view/[^/?#]+)", link)
        kid = key.group(1) if key else link
        if kid in seen or not title:
            continue
        seen.add(kid)
        results.append({
            "title": title,
            "company": clean(c.group(1)) if c else "",
            "loc": clean(l.group(1)) if l else "",
            "posted": d.group(1) if d else "",
            "url": link,
            "q": term,
        })
        n += 1
    return n


def run_guest():
    results, seen = [], set()
    for term in QUERIES:
        for start in (0, 25):
            try:
                html = guest_fetch(term, start)
            except Exception as e:
                print(f"  guest '{term}' s{start}: {str(e)[:60]}", flush=True)
                return results, "blocked"
            if "authwall" in html[:20000] or len(html) < 500:
                return results, "blocked"
            n = parse_cards(html, results, seen)
            if n == 0:
                break
            time.sleep(1.0)
        print(f"  guest '{term}': total {len(results)}", flush=True)
    return results, ("ok" if results else "blocked")


def run_playwright():
    from playwright.sync_api import sync_playwright
    results, seen = [], set()
    profile = Path(__file__).with_name(".li-profile")
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            str(profile), headless=False,
            user_agent=UA, viewport={"width": 1280, "height": 900},
            args=["--disable-blink-features=AutomationControlled"])
        if not any(c["name"] == "li_at" for c in ctx.cookies()):
            print("NOT LOGGED IN - run python li_login.py first", flush=True)
            ctx.close()
            return results, "nologin"
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        for term in QUERIES:
            blocked = False
            for start in (0, 25):
                url = (f"https://www.linkedin.com/jobs/search/?keywords={urllib.parse.quote(term)}"
                       f"&location={urllib.parse.quote(LOCATION)}&f_TPR=r604800&f_WT=2&start={start}")
                try:
                    page.goto(url, timeout=45000, wait_until="domcontentloaded")
                except Exception:
                    continue
                page.wait_for_timeout(3500)
                if "authwall" in page.url or "login" in page.url:
                    blocked = True
                    break
                cards = page.locator(
                    "li.base-card, div.job-card-container, li.jobs-search-results__list-item, "
                    "div[data-entity-urn]").all()
                if not cards and start == 0:
                    print(f"    debug url={page.url[:90]} title={page.title()[:60]}", flush=True)
                n = 0
                for card in cards[:30]:
                    try:
                        a = card.locator(
                            "a.base-card__full-link, a.job-card-container__link, "
                            "a[data-control-name], a.hidden-needs-tabfix").first
                        if not a.count():
                            continue
                        href = a.get_attribute("href") or ""
                        if not href:
                            continue
                        link = href.split("?")[0]
                        kid = re.search(r"(/jobs/view/[^/?#]+)", link)
                        kid = kid.group(1) if kid else link
                        if kid in seen:
                            continue
                        t = card.locator(
                            ".base-search-card__title, .job-card-list__title, "
                            ".artdeco-entity-lockup__title, h3").first
                        c = card.locator(
                            ".base-search-card__subtitle, .job-card-container__primary-description, "
                            ".artdeco-entity-lockup__subtitle, h4").first
                        l = card.locator(
                            ".job-search-card__location, .job-card-container__metadata-item, "
                            ".artdeco-entity-lockup__caption").first
                        title = t.inner_text().strip() if t.count() else ""
                        if not title:
                            continue
                        seen.add(kid)
                        results.append({
                            "title": title,
                            "company": c.inner_text().strip() if c.count() else "",
                            "loc": l.inner_text().strip() if l.count() else "",
                            "posted": "",
                            "url": link,
                            "q": term,
                        })
                        n += 1
                    except Exception:
                        continue
                if n == 0:
                    break
                time.sleep(1.5)
            if blocked:
                print(f"  pw '{term}': authwall", flush=True)
                break
            print(f"  pw '{term}': total {len(results)}", flush=True)
        ctx.close()
    return results, "ok" if results else "blocked"


def main():
    results, status = run_guest()
    if status == "blocked":
        print("guest API blocked; Playwright fallback", flush=True)
        results, status = run_playwright()
    lines = [f"# LINKEDIN SWEEP - {time.strftime('%Y-%m-%d')}", "",
             f"{len(results)} results (Germany, remote filter, past week). status={status}", ""]
    for r in results:
        lines.append(f"### {r['title']} @ {r['company']}")
        lines.append(f"- loc: {r['loc']} | posted: {r['posted']}")
        lines.append(f"- url: {r['url']}")
        lines.append(f"- q: {r['q']}")
        lines.append("")
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {OUT} with {len(results)} entries (status {status})")


if __name__ == "__main__":
    main()
