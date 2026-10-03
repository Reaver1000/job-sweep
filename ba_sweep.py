"""Arbeitsagentur jobsuche - supplementary sweep with extra terms.

Same scrape as job_sweep.src_arbeitsagentur but with terms the main sweep
lacks. Dedupes against seen_jobs.json, apply_list.json and deep_cache.json.
Writes ba_new.md.
"""
import io
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
OUT = HERE / "ba_new.md"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

TERMS = [
    "junior", "quereinsteiger", "softwaretester", "testautomatisierung",
    "business analyst", "product owner", "application support",
    "anwendungssupport", "anwendungsbetreuung", "frontend entwickler",
    "fullstack entwickler", "data analyst", "kundensupport",
    "technischer support", "app entwickler",
]


def fetch(url):
    req = urllib.request.Request(url, headers=HEADERS)
    return urllib.request.urlopen(req, timeout=40).read().decode("utf-8", "replace")


def _ba_field(card, field):
    m = re.search(rf'id="eintrag-\d+-{field}"[^>]*>(.*?)</div>', card, re.S)
    if not m:
        return ""
    txt = re.sub(r"<[^>]+>", "", m.group(1))
    txt = txt.replace("&nbsp;", " ").strip()
    txt = re.sub(r"^\d{1,2}\.\s(?=\D)", "", txt)
    return txt.strip()


def main():
    known = set()
    for f in ("seen_jobs.json",):
        p = HERE / f
        if p.exists():
            try:
                known.update(json.loads(p.read_text(encoding="utf-8")).keys())
            except Exception:
                pass
    try:
        known.update(json.loads((HERE / "apply_list.json").read_text(encoding="utf-8")) and
                     [e["url"] for e in json.loads((HERE / "apply_list.json").read_text(encoding="utf-8"))])
    except Exception:
        pass
    try:
        known.update(json.loads((HERE / "deep_cache.json").read_text(encoding="utf-8")).keys())
    except Exception:
        pass

    seen_ids = set()
    rows = []
    for term in TERMS:
        for page in range(1, 8):
            url = (f"https://www.arbeitsagentur.de/jobsuche/suche?was={urllib.parse.quote(term)}"
                   f"&wo=deutschland&arbeitsmodelle=homeoffice&seite={page}")
            try:
                html = fetch(url)
            except Exception as e:
                print(f"  {term} p{page} stop: {str(e)[:60]}", flush=True)
                break
            cards = re.split(r'<article[^>]*class="ergebnisliste-item"', html)
            if len(cards) < 2:
                break
            n_new = 0
            for card in cards[1:]:
                m = re.search(r'href="(https://www\.arbeitsagentur\.de/jobsuche/jobdetail/([A-Za-z0-9_-]+))"', card)
                if not m:
                    continue
                url_job, jid = m.group(1), m.group(2)
                if jid in seen_ids:
                    continue
                seen_ids.add(jid)
                title = _ba_field(card, "titel")
                firma = _ba_field(card, "firma")
                ort = _ba_field(card, "arbeitsort").replace("Arbeitsort:", "").strip()
                gehalt = _ba_field(card, "gehaltsspanne")
                ho = _ba_field(card, "homeoffice")
                if not title or url_job in known:
                    continue
                rows.append({"title": title, "company": firma, "loc": ort,
                             "pay": gehalt, "ho": ho, "url": url_job, "q": term})
                n_new += 1
            if n_new == 0:
                break
            time.sleep(0.4)
        print(f"  '{term}': total {len(rows)}", flush=True)

    lines = [f"# ARBEITSAGENTUR EXTRA SWEEP - {time.strftime('%Y-%m-%d')}", "",
            f"{len(rows)} new entries (homeoffice filter).", ""]
    for r in rows:
        lines.append(f"### {r['title']} @ {r['company']}")
        lines.append(f"- loc: {r['loc']}")
        if r["pay"]:
            lines.append(f"- pay: {r['pay']}")
        if r["ho"]:
            lines.append(f"- homeoffice: {r['ho']}")
        lines.append(f"- url: {r['url']}")
        lines.append(f"- q: {r['q']}")
        lines.append("")
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {OUT} with {len(rows)} entries")


if __name__ == "__main__":
    main()
