import re, json
from pathlib import Path

HERE = Path(__file__).parent

def headers(path):
    try:
        t = (HERE / path).read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    out = {}
    for block in t.split("\n### ")[1:]:
        lines = block.split("\n")
        title = lines[0].strip()
        loc = next((l for l in lines if l.startswith("- loc:")), "")
        url = next((l for l in lines if l.startswith("- url:")), "")
        pay = next((l for l in lines if l.startswith("- pay:")), "")
        snip = next((l for l in lines if l.startswith("- snip:")), "")
        out[title.lower()[:80]] = (title, loc[7:][:50], pay[6:][:40], url[6:][:150], snip[6:][:120])
    return out

applied = json.load(open('applied.json', encoding='utf-8'))
SENIOR = re.compile(r'senior|lead|director|head of|principal|staff|chefarzt', re.I)
SKIP = re.compile(r'Hyra|Haystack|Amadeus|TaskVerse|RemoExperts|Ethos|Welocalize|Lionbridge|RWS|Perit|Volga|Synthires|Crossing Hurdles|7Learnings|Atos|SAP|EWM|Berater.*SAP', re.I)

fresh = headers('linkedin_jobs.md'); old = headers('linkedin_jobs_prev.md')
new = [k for k in fresh if k not in old]
shown = 0
for k in new:
    title, loc, pay, url, snip = fresh[k]
    if SENIOR.search(title) or SKIP.search(title):
        continue
    uid = url.split('/')[-1][:24]
    if uid and any(uid in a for a in applied):
        continue
    print(f'* {title[:85]}')
    print(f'    {loc[:55]} | {url[:45]}')
    shown += 1
    if shown >= 25:
        break
print(f'\n({shown} shown of {len(new)} new)')
