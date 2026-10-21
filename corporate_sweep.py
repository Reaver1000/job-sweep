"""Corporate career-page sweeper for big non-tech employers (analyst roles).

Currently supports Workday CX tenants. Adding a company = adding one line to
TENANTS after finding its tenant/site slug.

Output: corporate_jobs.md (diff_new.py format).
"""
import re
import time
import requests
from pathlib import Path

HERE = Path(__file__).parent
OUT = HERE / "corporate_jobs.md"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Content-Type": "application/json",
    "Accept": "application/json",
    "Accept-Language": "en-GB,en;q=0.5",
}

# company -> (tenant, wdN, site)
TENANTS = {
    "Unilever": ("unilever", "wd3", "Unilever_Experienced_Professionals"),
    "Sartorius": ("sartorius", "wd3", "sartoriuscareers"),
    "AstraZeneca": ("astrazeneca", "wd3", "careers"),
}

QUERIES = ["analyst", "business analyst", "data analyst", "junior analyst"]

SENIOR_KILL = re.compile(r"\b(senior|lead|director|head of|principal|chief|staff)\b", re.I)
INTERN_KILL = re.compile(r"\b(intern|working student|apprentice|praktikum|trainee)\b", re.I)
LOC_KEEP = re.compile(r"germany|deutschland|united kingdom|\buk\b|london|edinburgh|manchester|birmingham|leeds|glasgow|europe|netherlands|amsterdam|belgium|brussels|france|paris|spain|madrid|barcelona|italy|milan|austria|vienna|switzerland|zurich|geneva|berlin|hamburg|münchen|munich|frankfurt|stuttgart|cologne|köln|leipzig|dresden|erfurt|düsseldorf|bremen|hannover|nuremberg|nürnberg", re.I)
LOC_KILL = re.compile(r"philippines|nigeria|india|lagos|chennai|lucknow|taguig|warsaw|poland|singapore|china|shanghai|beijing|japan|tokyo|brazil|sao paulo|mexico|africa|indonesia|malaysia|vietnam|thailand|argentina|colombia|pakistan|bangladesh|egypt|kenya|ghana|usa|united states|ann arbor|new york|san francisco|toronto|canada|australia", re.I)
MANAGER_KILL = re.compile(r"\bmanager\b", re.I)
JUNIOR_MARK = re.compile(r"\bjunior\b", re.I)
ANALYST_MARK = re.compile(r"analyst|analytics|business intelligence|reporting|\bdata\b|insight|\bbi\b", re.I)


def workday_cx(tenant, wdn, site, query, limit=20, offset=0):
    url = f"https://{tenant}.{wdn}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs"
    r = requests.post(url, json={"appliedFacets": {}, "limit": limit, "offset": offset, "searchText": query},
                      headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json()


def sweep_tenant(company, tenant_cfg):
    tenant, wdn, site = tenant_cfg
    seen = {}
    for q in QUERIES:
        offset = 0
        total = None
        while True:
            try:
                d = workday_cx(tenant, wdn, site, q, limit=20, offset=offset)
            except Exception as e:
                print(f"  {company} '{q}' @{offset}: ERR {str(e)[:60]}", flush=True)
                break
            if total is None:
                total = d.get("total", 0)
            for j in d.get("jobPostings") or []:
                ext = j.get("externalPath", "")
                if not ext or ext in seen:
                    continue
                seen[ext] = {
                    "title": j.get("title", ""),
                    "loc": j.get("locationsText", ""),
                    "posted": j.get("postedOn", ""),
                    "url": f"https://{tenant}.{wdn}.myworkdayjobs.com/en-US{ext}",
                }
            offset += 20
            if offset >= total or offset >= 100:
                break
            time.sleep(0.5)
        print(f"  {company} '{q}': total={total}, cum unique={len(seen)}", flush=True)
        time.sleep(0.5)
    return seen


def keep(job):
    title = job["title"]
    loc = job["loc"]
    if SENIOR_KILL.search(title):
        return False, "senior"
    if MANAGER_KILL.search(title) and not JUNIOR_MARK.search(title):
        return False, "senior"
    if INTERN_KILL.search(title):
        return False, "intern"
    if LOC_KILL.search(loc):
        return False, "geo"
    if not LOC_KEEP.search(loc):
        return False, "geo"
    if not ANALYST_MARK.search(title):
        return False, "relevance"
    return True, ""


def main():
    kept = {}
    for company, cfg in TENANTS.items():
        jobs = sweep_tenant(company, cfg)
        for ext, job in jobs.items():
            ok, why = keep(job)
            if ok:
                key = (company + "|" + job["title"]).lower()[:90]
                kept[key] = {"company": company, **job}
        print(f"{company}: {len(jobs)} unique, kept so far {len(kept)}", flush=True)

    lines = ["# Corporate career-page sweep (Workday tenants)", ""]
    for j in kept.values():
        snip = f"{j['posted']} | {j['loc']}"
        lines.append(f"### {j['title']} @ {j['company']}")
        lines.append(f"- loc: {j['loc']}")
        lines.append(f"- url: {j['url']}")
        lines.append(f"- pay: ")
        lines.append(f"- snip: {snip}")
        lines.append("")
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nKEPT {len(kept)} -> {OUT}")

if __name__ == "__main__":
    main()
