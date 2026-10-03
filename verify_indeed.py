"""Verify Indeed job candidates: open detail pages, extract full descriptions."""
import re
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(__file__).with_name("indeed_verify.md")


def _append(lines):
    with open(OUT, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

JOBS = [
    # (domain, indeed-jk-id, label). Find jk ids in your indeed_sweep.py output URLs.
    ("de", "examplejkid000001", "Example Company Junior Developer"),
    ("uk", "examplejkid000002", "Example Company QA Analyst"),
]


def dismiss_consent(page):
    try:
        for frame in page.frames:
            if "consent" in frame.url or "fundingchoices" in frame.url or "sparrow" in frame.url:
                for sel in ["button:has-text('Alle ablehnen')", "button:has-text('Reject all')",
                            "button:has-text('Ablehnen')", "button:has-text('Reject')"]:
                    try:
                        btn = frame.locator(sel).first
                        if btn.is_visible(timeout=700):
                            btn.click(timeout=2000)
                            page.wait_for_timeout(1200)
                            return
                    except Exception:
                        continue
    except Exception:
        pass
    for sel in ["button:has-text('Auswahl ablehnen')", "button:has-text('Alle ablehnen')",
                "button:has-text('Einfach fortfahren')", "button:has-text('Reject all')",
                "button:has-text('Decline all')", "button:has-text('Ablehnen')",
                "button:has-text('Reject')", "#onetrust-reject-all-handler"]:
        try:
            btn = page.locator(sel).first
            if btn.is_visible(timeout=600):
                btn.click(timeout=2000)
                page.wait_for_timeout(1200)
                return
        except Exception:
            continue


def main():
    done = set()
    if OUT.exists():
        txt = OUT.read_text(encoding="utf-8")
        done = {m.group(1) for m in re.finditer(r"jk=([0-9a-f]+)\)", txt)}
    lines = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False,
                                   args=["--disable-blink-features=AutomationControlled"])
        ctx = browser.new_context(user_agent=UA, viewport={"width": 1280, "height": 900})
        page = ctx.new_page()
        for dom, jk, label in JOBS:
            if jk in done:
                print(f"  skip {label} (done)", flush=True)
                continue
            url = f"https://{dom}.indeed.com/viewjob?jk={jk}"
            try:
                page.goto(url, timeout=40000, wait_until="domcontentloaded")
            except Exception as e:
                lines.append(f"## {label} (jk={jk})\n- FAIL goto: {str(e)[:80]}\n")
                _append(lines)
                lines = []
                continue
            page.wait_for_timeout(3500)
            if "moment" in page.title().lower():
                page.wait_for_timeout(9000)
                if "moment" in page.title().lower():
                    lines.append(f"## {label} (jk={jk})\n- FAIL challenge\n")
                    _append(lines)
                    lines = []
                    continue
            dismiss_consent(page)
            try:
                page.wait_for_selector("#jobDescriptionText", timeout=8000)
            except Exception:
                pass
            page.wait_for_timeout(1500)
            try:
                title = page.locator("h2[data-testid='jobsearch-JobInfoJobTerm'], h1").first.inner_text().strip()
            except Exception:
                title = label
            try:
                body = page.locator("div[id='jobDescriptionText'], #jobDescriptionText, [data-testid='jobDescriptionText']").first.inner_text().strip()
            except Exception:
                try:
                    body = page.inner_text("body")
                except Exception:
                    body = ""
            try:
                comp = page.locator("[data-testid='jobsearch-CompanyInfoBlock'] h2, .jobsearch-CompanyInfoBlock h2").first.inner_text().strip()
            except Exception:
                comp = ""
            lines.append(f"## {label} (jk={jk})")
            lines.append(f"- title: {title}")
            lines.append(f"- company: {comp}")
            lines.append(f"- url: {url}")
            lines.append(f"- body: {' '.join(body.split())[:6000]}")
            lines.append("")
            _append(lines)
            lines = []
            print(f"  ok {label}", flush=True)
            time.sleep(1.5)
        browser.close()
    print("done")


if __name__ == "__main__":
    main()
