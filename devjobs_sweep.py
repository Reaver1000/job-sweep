"""DEVjobs.de sweeper - English interface, German dev job board.

Scrapes category search pages (server-rendered), filters for remote +
non-senior roles, writes devjobs_jobs.md in the diff_new.py format.
"""
import re
import time
import requests
from pathlib import Path

HERE = Path(__file__).parent
OUT = HERE / "devjobs_jobs.md"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-GB,en;q=0.5",
}
BASE = "https://en.devjobs.de"

TECHS = ["python", "javascript", "typescript", "react", "node-js", "sql", "linux", "docker", "kubernetes"]
PAGES_PER_TECH = 3

SENIOR_KILL = re.compile(
    r"\b(senior|lead|director|head|principal|chief|staff|manager|architect)\b", re.I
)
INTERN_KILL = re.compile(r"\b(intern|working student|werkstudent|praktikum)\b", re.I)

def clean(s):
    s = re.sub(r"<[^>]+>", " ", s)
    s = s.replace("&", "&").replace("&nbsp;", " ").replace("&#x27;", "'")
    return re.sub(r"\s+", " ", s).strip()

def parse_cards(html):
    """Each card: href=/job/<hash> ... <h2>title</h2> ... company <p> ... <span>loc</span> ... snippet <p> ... <ul><li>tag</li>...</ul>"""
    cards = []
    parts = html.split('href="/job/')
    for part in parts[1:]:
        m = re.match(r'([0-9a-f]{32})"', part)
        if not m:
            continue
        url = "/job/" + m.group(1)
        # card content ends at the next card start; take a generous slice
        block = part[:part.find('href="/job/')] if 'href="/job/' in part else part
        block = block[:6000]
        if not re.search(r"<h2[^>]*>", block):
            continue
        t = re.search(r"<h2[^>]*>(.*?)</h2>", block)
        title = clean(t.group(1)) if t else ""
        comp = ""
        cm = re.search(r'alt="Logo ([^"]+)"', block)
        if cm:
            comp = cm.group(1)
        else:
            pm = re.search(r"</picture>\s*<div[^>]*><p[^>]*>([^<]+)</p>", block)
            if pm:
                comp = clean(pm.group(1))
        loc = re.search(r"<span[^>]*>([^<]+)</span>", block)
        location = clean(loc.group(1)) if loc else ""
        snips = re.findall(r"<p[^>]*>([^<]+)</p>", block)
        snip = ""
        for s in snips:
            s = clean(s)
            if s and s != comp and len(s) > 40:
                snip = s
                break
        tags = [clean(x) for x in re.findall(r"<li[^>]*>([^<]+)</li>", block)]
        cards.append({
            "url": BASE + url,
            "title": title,
            "company": comp,
            "loc": location,
            "tags": tags,
            "snip": snip[:120],
        })
    return cards

def keep(job):
    tags = " ".join(job["tags"])
    title = job["title"]
    # remote required for normal roles
    if not re.search(r"\bRemote\b", tags, re.I):
        return False, "not-remote"
    if re.search(r"hybrid|on-?site|office", tags, re.I):
        return False, "not-remote"
    if SENIOR_KILL.search(title) or SENIOR_KILL.search(tags):
        return False, "seniority"
    if INTERN_KILL.search(title) or INTERN_KILL.search(tags):
        return False, "internship"
    return True, ""

def main():
    s = requests.Session()
    s.headers.update(HEADERS)
    seen = {}
    kept, kills = [], 0
    kill_reasons = {}
    for tech in TECHS:
        for page in range(1, PAGES_PER_TECH + 1):
            try:
                r = s.get(f"{BASE}/jobs/search",
                          params={"technologies": tech, "page": str(page)},
                          timeout=30)
            except Exception as e:
                print(f"  {tech} p{page}: ERR {str(e)[:60]}", flush=True)
                continue
            for card in parse_cards(r.text):
                if card["url"] in seen:
                    continue
                seen[card["url"]] = card
                ok, why = keep(card)
                if ok:
                    kept.append(card)
                else:
                    kills += 1
                    kill_reasons[why] = kill_reasons.get(why, 0) + 1
            time.sleep(0.4)
        print(f"  {tech}: cum {len(seen)} seen, {len(kept)} kept", flush=True)

    lines = ["# DEVjobs.de sweep", ""]
    for j in kept:
        lines.append(f"### {j['title']} @ {j['company']}")
        lines.append(f"- loc: {j['loc']}")
        lines.append(f"- url: {j['url']}")
        lines.append(f"- pay: ")
        lines.append(f"- snip: {j['snip']}")
        lines.append("")
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nKEPT {len(kept)} | KILLED {kills} | reasons: {kill_reasons}")
    print(f"wrote {OUT} with {len(kept)} entries")

if __name__ == "__main__":
    main()
