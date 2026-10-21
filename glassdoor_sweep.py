"""Glassdoor.de sweeper via persistent Chrome profile (.gd-profile, real Chrome headed).
Searches targeted junior/remote queries, parses job cards, filters, writes glassdoor_jobs.md.
"""
import re
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

HERE = Path(__file__).parent
OUT = HERE / "glassdoor_jobs.md"
PROFILE = HERE / ".gd-profile"

QUERIES = [
    "junior analyst remote",
    "junior business analyst remote",
    "junior data analyst remote",
    "junior python entwickler remote",
    "junior softwareentwickler remote",
    "IT support junior homeoffice",
    "junior qa testautomation remote",
    "junior automation engineer remote",
    "junior data engineer remote",
]

SENIOR_KILL = re.compile(r"\b(senior|lead|director|head of|principal|chief|staff)\b", re.I)
INTERN_KILL = re.compile(r"\b(werkstudent|praktikum|internship|working student|studentische|ausbildung)\b", re.I)
REMOTE_NEED = re.compile(r"remote|homeoffice|telearbeit", re.I)
OFFICE_ONLY = re.compile(r"nur vor ort|b\u00fcro[- ]?pflicht|vor-?ort\b", re.I)
ROLE_HINTS = re.compile(r"analyst|engineer|developer|berater|consultant|support|administrator|manager|spezialist|scientist|entwickler|architekt|designer|operator|specialist|programmierer|tester", re.I)
COMPANY_HINTS = re.compile(r"\b(GmbH|AG|SE|KGaA|Ltd|Inc|Group|GmbH & Co\.? KG|SE & Co\.? KG| Holding)\b")
MANAGER_KILL = re.compile(r"\b(operations manager|commercial manager|vertriebsleiter|key account|account executive|sales manager)\b", re.I)

def parse_card(href, text):
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    if not lines:
        return None
    # title: line with the most role hints; fall back to longest line
    title = None
    for l in lines:
        if len(l) < 4 or re.match(r'^\d+[.,]\d$', l):
            continue
        if l.startswith('Standort') or 'Anzeige' in l:
            continue
        if ROLE_HINTS.search(l) and (title is None or len(ROLE_HINTS.findall(l)) > len(ROLE_HINTS.findall(title))):
            title = l
    if title is None:
        title = max(lines, key=len)
    # company: short line with company suffix, or the first non-title line
    company = ""
    for l in lines:
        if l == title or re.match(r'^\d+[.,]\d$', l):
            continue
        if COMPANY_HINTS.search(l) and len(l) < 60:
            company = re.sub(r'\s*\d+[.,]\d+$', '', l).strip()
            break
    if not company:
        for l in lines:
            if l != title and len(l) < 50 and not l.startswith('Standort') and 'Anzeige' not in l:
                company = l
                break
    loc = ""
    age = ""
    snip = ""
    for l in lines:
        if l.startswith('Standort'):
            loc = l.replace('Standort:', '').strip()
        elif 'Anzeige' in l and re.search(r'T\+?', l):
            m = re.search(r'Anzeige\s+(\d+)\s*T', l)
            if m:
                age = m.group(1)
        elif not snip and len(l) > 30 and l != title and 'Kenntnisse und F' not in l[:5]:
            snip = l
    return {"title": title, "company": company, "loc": loc, "age": age, "snip": snip[:120], "url": href}

def main():
    kept = {}
    with sync_playwright() as pw:
        browser = pw.chromium.launch_persistent_context(
            str(PROFILE), channel='chrome', headless=False,
            viewport={'width': 1366, 'height': 900},
            args=['--disable-blink-features=AutomationControlled'],
        )
        page = browser.new_page()
        first = True
        for q in QUERIES:
            url = f'https://www.glassdoor.de/Job/jobs.htm?sc.keyword={q.replace(" ", "%20")}'
            try:
                page.goto(url, timeout=60000, wait_until='domcontentloaded')
                page.wait_for_timeout(10000 if first else 6000)
                first = False
                cards = page.evaluate('''() => {
                    const out = [];
                    const seen = new Set();
                    document.querySelectorAll('a[href*="/job-listing/"]').forEach(a => {
                        const href = a.href.split('&')[0];
                        if (seen.has(href)) return;
                        seen.add(href);
                        let el = a;
                        for (let i = 0; i < 4 && el.parentElement; i++) el = el.parentElement;
                        out.push({href: href, text: el.innerText || ''});
                    });
                    return out;
                }''')
                n = 0
                for c in cards:
                    parsed = parse_card(c['href'], c['text'])
                    if not parsed or not parsed['title']:
                        continue
                    full = ' | '.join([parsed['title'], parsed['company'], parsed['loc'], parsed['snip']])
                    if OFFICE_ONLY.search(full):
                        continue
                    if SENIOR_KILL.search(full) or MANAGER_KILL.search(parsed['title']):
                        continue
                    if INTERN_KILL.search(full):
                        continue
                    # require genuine remote signal, not just "remote moeglich" noise without any remote confirm
                    if not REMOTE_NEED.search(full):
                        continue
                    key = (parsed['title'] + '|' + parsed['company']).lower()[:90]
                    kept[key] = parsed
                    n += 1
                print(f'  {q}: {len(cards)} cards, {n} kept', flush=True)
            except Exception as e:
                print(f'  {q}: FAIL {str(e)[:80]}', flush=True)
            time.sleep(1.5)
        browser.close()

    lines = ["# Glassdoor sweep", ""]
    for j in kept.values():
        lines.append(f"### {j['title']} @ {j['company']}")
        lines.append(f"- loc: {j['loc']}")
        lines.append(f"- url: {j['url']}")
        lines.append(f"- pay: ")
        lines.append(f"- snip: {j['snip']}")
        lines.append("")
    OUT.write_text("\n".join(lines), encoding='utf-8')
    print(f"\nKEPT {len(kept)}")
    print(f"wrote {OUT} with {len(kept)} entries")

if __name__ == '__main__':
    main()
