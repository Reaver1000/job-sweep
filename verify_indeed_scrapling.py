"""Indeed verification via Scrapling StealthyFetcher — solves the Cloudflare/Turnstile
wall that vanilla Playwright could not. Extracts #jobDescriptionText after hydration.

Usage: python verify_indeed_scrapling.py
Writes/updates indeed_verify.md entries.
"""
import re
import time
from pathlib import Path
from scrapling.fetchers import StealthyFetcher

OUT = Path(__file__).with_name("indeed_verify.md")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

JOBS = [
    ("de", "30dfdaf9e910b057", "mund consulting Tester/Testautomatisierer"),
    ("de", "88f2379266086b7f", "Firstwaters Junior Business Analyst"),
    ("de", "43fd615be2183dc2", "tech11 Junior IT Business Analyst"),
    ("uk", "db205f5ae46ea1bf", "KP UK PMO Analyst"),
]


def fetch_jd(dom, jk):
    """Extract the JD text from the rendered page."""
    html = dom.body.html if hasattr(dom.body, 'html') else str(dom.body)
    # primary: the jobDescriptionText div (populated after hydration)
    m = re.search(r'id="jobDescriptionText"[^>]*>(.*?)</div>\s*</div>', html, re.S)
    if not m:
        # fallback: grab from the jobDescriptionText marker to the next major marker
        i = html.find('jobDescriptionText')
        if i < 0:
            return None
        seg = html[i:i+12000]
        text = re.sub(r'<[^>]+>', ' ', seg)
        text = re.sub(r'&[a-z#0-9]+;', ' ', text)
        text = re.sub(r'\s+', ' ', text)
        return text[:3000]
    seg = m.group(1)
    text = re.sub(r'<[^>]+>', ' ', seg)
    text = re.sub(r'&[a-z#0-9]+;', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text[:3000]


def main():
    lines = []
    for dom_id, jk, label in JOBS:
        url = f"https://{dom_id}.indeed.com/viewjob?jk={jk}"
        print(f"--- {label} ---", flush=True)
        try:
            page = StealthyFetcher.fetch(
                url,
                headless=True,
                network_idle=True,
                solve_cloudflare=True,
                wait=6000,
            )
            print(f"  status: {page.status}", flush=True)
            jd = fetch_jd(page, jk)
            if jd and len(jd) > 100:
                print("  JD OK:", jd[:200])
                lines.append(f"## {label} (jk={jk})\n{jd}\n")
            else:
                print("  JD extraction failed", flush=True)
                lines.append(f"## {label} (jk={jk})\n- extraction failed (page {page.status})\n")
        except Exception as e:
            print(f"  ERR {str(e)[:100]}", flush=True)
            lines.append(f"## {label} (jk={jk})\n- ERR {str(e)[:100]}\n")
        time.sleep(2)

    with open(OUT, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"\nappended to {OUT}")


if __name__ == "__main__":
    main()
