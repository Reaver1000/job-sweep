"""Diff fresh sweep outputs against the previous run's snapshots. Prints genuinely new entries."""
import sys
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
        key = title.lower()[:80]
        out[key] = (title, loc[7:][:50], pay[6:][:40], url[6:][:150], snip[6:][:120])
    return out


for cur, prev in [("indeed_jobs.md", "indeed_jobs_prev.md"),
                  ("linkedin_jobs.md", "linkedin_jobs_prev.md"),
                  ("ba_new.md", "ba_new_prev.md")]:
    fresh = headers(cur)
    old = headers(prev)
    new = [k for k in fresh if k not in old]
    print(f"===== {cur}: {len(new)} new of {len(fresh)} =====")
    for k in new:
        title, loc, pay, url, snip = fresh[k]
        print(f"* {title[:100]}")
        print(f"    loc: {loc} | pay: {pay}")
        print(f"    url: {url}")
        print(f"    snip: {snip}")
    print()
