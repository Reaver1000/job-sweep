"""LinkedIn sweep v2. Guest API via the logged-in browser context (bypasses IP
rate limits), absolute /jobs/view/ links, 4 pages per query.
Writes linkedin_jobs.md.
"""
import re
import time
import urllib.parse
from pathlib import Path

OUT = Path(__file__).with_name("linkedin_jobs.md")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

QUERIES = ["junior analyst", "junior business analyst", "junior software engineer", "junior developer", "junior data analyst",
           "test automation engineer junior", "junior qa", "IT support junior",
           "python junior developer", "junior automation engineer",
           "junior application support",
           "forward deployed engineer junior", "integration engineer junior",
           "solutions engineer junior", "implementation engineer junior",
           "technical consultant junior"]
LOCATION = "Germany"


def clean(s):
    s = re.sub(r"<[^>]+>", " ", s or "")
    return re.sub(r"\s+", " ", s).strip()


def parse_fragment(html, results, seen):
    n = 0
    # the fragment's <li> tags are bare; anchor on the full-link anchor instead
    parts = re.split(r'<a[^>]*base-card__full-link[^>]*href="', html)
    for part in parts[1:]:
        a = re.match(r'([^"]+)"', part)
        if not a:
            continue
        link = a.group(1)
        # card text lives BEFORE the anchor in the same block
        block_start = part.rfind('<li', 0, part.find('base-search-card__title') if 'base-search-card__title' in part else 600)
        block = part[:part.find('</li>')] if '</li>' in part else part[:3000]
        t = re.search(r'<h3[^>]*base-search-card__title[^>]*>(.*?)</h3>', block, re.S)
        c = re.search(r'<h4[^>]*base-search-card__subtitle[^>]*>(.*?)</h4>', block, re.S)
        l = re.search(r'<span[^>]*job-search-card__location[^>]*>(.*?)</span>', block, re.S)
        d = re.search(r'datetime="([^"]+)"', block)
        if not t:
            continue
        title = clean(t.group(1))
        link = link.split("?")[0]
        kid = re.search(r"(jobs/view/[^/?#]+)", link)
        kid = kid.group(1) if kid else link
        if kid in seen or not title:
            continue
        seen.add(kid)
        results.append({
            "title": title,
            "company": clean(c.group(1)) if c else "",
            "loc": clean(l.group(1)) if l else "",
            "posted": d.group(1) if d else "",
            "url": link,
        })
        n += 1
    return n


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
            for start in (0, 25, 50, 75):
                url = ("https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
                       f"?keywords={urllib.parse.quote(term)}"
                       f"&location={urllib.parse.quote(LOCATION)}"
                       f"&f_TPR=r604800&f_WT=2&start={start}")
                try:
                    page.goto(url, timeout=45000, wait_until="domcontentloaded")
                except Exception:
                    continue
                page.wait_for_timeout(3000)
                html = page.content()
                if "authwall" in html[:30000]:
                    blocked = True
                    break
                n = parse_fragment(html, results, seen)
                if n == 0:
                    break
                time.sleep(1.5)
            if blocked:
                print(f"  '{term}': authwall", flush=True)
                break
            print(f"  '{term}': total {len(results)}", flush=True)
        ctx.close()
    return results, "ok" if results else "blocked"


def main():
    results, status = run_playwright()
    lines = [f"# LINKEDIN SWEEP - {time.strftime('%Y-%m-%d')}", "",
             f"{len(results)} results (Germany, remote filter, past week). status={status}", ""]
    for r in results:
        lines.append(f"### {r['title']} @ {r['company']}")
        lines.append(f"- loc: {r['loc']} | posted: {r['posted']}")
        lines.append(f"- url: {r['url']}")
        lines.append("")
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {OUT} with {len(results)} entries (status {status})")


if __name__ == "__main__":
    main()
