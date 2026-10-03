"""Mega-sweep: pull ALL remote-eligible jobs, then ELIMINATE by hard blockers.

Philosophy: do not pre-filter by title. Fetch wide, eliminate what the candidate
cannot do, keep everything else - including oddly-titled roles.

Elimination order (first failing check wins):
  1. not_remote        - no remote flag and no remote language anywhere
  2. region_blocked    - US-only / Americas-only / requires US work auth
  3. seniority         - senior/lead/principal/staff/head/director/manager
  4. internship        - intern/praktikum/werkstudent (low wage, needs enrolment)
  5. alien_stack       - title demands a stack the candidate does not have (Java, SAP, ...)
  6. licensed_job      - nurse/lawyer/accountant/electrician etc.
 7. german_c1         - posting demands fluent/C1 German
 7b. posting_language  - body is French/Spanish/Portuguese (can't work in it)
 8. hybrid_disguised  - says remote but body reveals mandatory office days
  9. low_pay           - quoted pay below threshold
 10. irrelevant_field  - clinical/legal/beauty/warehouse/driving/construction

Survivors: scored + loosely family-tagged, written to jobs_found.md.
Eliminated: stats + examples written to jobs_eliminated.md.
"""
import json
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

HERE = Path(__file__).parent
OUT_OK = HERE / "jobs_found.md"
OUT_KILL = HERE / "jobs_eliminated.md"
OUT_NEW = HERE / "new_jobs.md"
SEEN_FILE = HERE / "seen_jobs.json"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

REMOTE_WORDS = ["remote", "homeoffice", "home office", "work from home", "anywhere", "telearbeit",
                "100% remote", "fully remote", "remote-first", "distributed", "location independent",
                "ortsunabhaengig", "deutschlandweit", "von zu hause"]

REGION_OK = ["worldwide", "anywhere", "global", "europe", "emea", "germany", "deutschland",
             "eu", "european", "cet", "eet", "berlin", "dach", "austria", "switzerland",
             "poland", "netherlands", "multiple", "international", "uk"]

REGION_KILL = ["us only", "us-only", "united states only", "usa only", "u.s. only", "u.s.-based",
               "remote from usa", "remote from us", "remote from uk", "remote from united states",
               "remote from canada", "remote from australia",
               "us-based", "us based", "americas only", "north america only", "must be located in the united states",
               "us citizens", "us residents", "authorized to work in the us", "must reside in the us",
               "canada only", "latam only", "philippines only", "india only", "australia only",
               "uk only", "uk-based only", "ireland only", "brazil only", "mexico only"]

SENIORITY = ["senior", "sr.", " sr ", "lead ", " lead", "principal", "staff engineer", "head of",
             "director", "vice president", "vp ", "chief", "manager", "leiter", "teamleiter",
             "gruppenleiter", "bereichsleiter"]

INTERNSHIP = ["intern", "internship", "praktikum", "werkstudent", "working student", "trainee",
              "ausbildung", "azubi", "praktikant", "thesis", "abschlussarbeit", "student assistant",
              "studentische", "voluntary", "volunteer", "unpaid"]

ALIEN_STACK = ["java ", "java developer", "java-", "spring boot", "kotlin", "sap", "abap", "salesforce",
               "mulesoft", "servicenow", "workday", "databricks", "snowflake engineer", ".net", "c#",
               "dotnet", "php developer", "laravel", "magento", "wordpress developer", "shopify",
               "ios ", "android", "swift ", "objective-c", "flutter", "react native", "xamarin",
               "c++", "embedded", "firmware", "fpga", "rust developer", "golang", "go developer",
               "scala", "haskell", "erlang", "cobol", "fortran", "perl", "unity", "unreal",
               "devops engineer", "sre", "site reliability", "platform engineer", "cloud architect",
               "kubernetes admin", "vmware", "citrix", "mainframe", "oracle dba", "dba",
               "network engineer", "cisco", "ccna required", "5g", "rf engineer", "telecom",
               "plc", "sps-programmierer", "automation engineer plc", "elektro", "mechatron",
               "solidity", "blockchain developer", "quantitative", "hft", "trading systems",
               "machine learning engineer", "ml engineer", "ai research", "deep learning",
               "data scientist", "mlops", "computer vision engineer", "nlp engineer",
               "security engineer", "pentester", "penetration", "soc analyst tier 3",
               "game developer", "3d artist", "vfx", "audio engineer",
               "video editor", "video creator", "videographer", "motion design",
               "graphic design", "animator", "illustrator", "photographer",
               "photo editor", "sound design", "music producer", "podcast producer",
               "voice over", "voiceover", "interior design", "fashion design",
               "ux design", "ui design", "product design"]

LICENSED = ["nurse", "pflegefachkraft", "gesundheits", "arzt", "aerzt", "physician", "doctor",
            "lawyer", "anwalt", "rechtsanwalt", "jurist", "paralegal", "notar",
            "steuerberater", "accountant", "buchhalter", "bilanzbuchhalter", "auditor",
            "electrician", "elektriker", "plumber", "hvac", "architekt", "architect bau",
            "lehrer", "teacher primary", "teacher secondary", "grundschullehrer", "educator school",
            "psycholog", "therapist", "therapeut", "counselor", "social worker", "sozialarbeiter",
            "pharmacist", "apotheker", "lab technician", "laborant", "chemist", "biologist",
            "pilot", "flight", "truck driver", "fahrer", "warehouse", "lagerarbeiter", "picker",
            "chef cook", "koch", "restaurant", "hairdresser", "friseur", "beautician", "kosmetik",
            "real estate agent", "immobilienmakler", "insurance agent", "versicherungsvertreter",
            "facility manager gebaeude", "hausmeister", "security guard", "sicherheitsdienst",
            "bauleiter", "construction", "maurer", "carpenter", "tischler", "mechanic kfz", "kfz"]

GERMAN_C1 = ["verhandlungssicher", "c1 deutsch", "deutsch c1", "c1 german", "german c1",
             "c2 deutsch", "muttersprachliches deutsch", "native-level german", "fließende deutschkenntnisse",
             "fliessende deutschkenntnisse", "sehr gute deutschkenntnisse in wort und schrift",
             "deutsch in wort und schrift verhandlungssicher", "excellent german skills both written and verbal"]

FRENCH_POST = ["description des", "compétences", "conditions du poste", "profil recherché",
               "responsabilités", "être titulaire", "années d'expérience", "tâches",
               "exigences du poste", "lieu d'affectation", "conditions de travail",
               "durée du contrat", "diplôme", "maîtrise du français", "français courant"]
SPANISH_POST = ["descripción del puesto", "se busca", "experiencia mínima", "jornada completa",
                "requisitos mínimos", "salario bruto", "tipo de puesto", "se requiere",
                "años de experiencia", "se ofrece", "incorporación inmediata"]
PORTUGUESE_POST = ["descrição da vaga", "experiência mínima", "tipo de vaga",
                   "requisitos mínimos", "anos de experiência", "salário compatível"]
# density fallback (word-boundary safe: best/test/unique/require/part never match)
FRENCH_STOP = ["les", "des", "une", "est", "sont", "dans", "pour", "avec", "cette",
               "leurs", "nos", "vos", "qui", "sur", "par", "aux", "ces", "son", "sa"]

HYBRID_TELLS = ["hybrid", "days per week in the office", "days a week in the office", "tage pro woche im büro",
                "tage die woche im büro", "2 days on-site", "3 days on-site", "2-3 tage vor ort",
                "ein tag pro woche im büro", "weekly office", "office days", "präsenztage",
                "regelmäßige präsenz", "regelmäßig vor ort", "relocation required", "must relocate",
                "umzug erforderlich", "bereitschaft zur relocation"]

IRRELEVANT = ["beauty", "cosmetics", "fashion model", "influencer manager", "event manager",
              "catering", "housekeeping", "cleaning", "reinigung", "garten", "landscaping"]

LOW_PAY_YEAR = 26000      # EUR-ish equivalent floor
LOW_PAY_HOUR = 13         # below this is near minimum wage

# Broad family tags (generous, order matters - first hit wins)
FAMILIES = {
    "support-tech": ["support", "helpdesk", "help desk", "service desk", "kundendienst", "kundenbetreuung",
                     "customer care", "kundenberater", "kundenservice"],
    "customer-success": ["customer success", "client success", "account manager tech", "customer experience",
                         "customer manager", "community manager", "kundenmanager"],
    "implementation-onboarding": ["implementation", "onboarding", "solutions", "deployment", "integration specialist",
                                  "einrichtung", "einführung", "consultant"],
    "it-admin": ["systemadministrator", "system administrator", "sysadmin", "administrator", "it admin",
                 "fachinformatiker", "it specialist", "it-techniker", "infrastructure"],
    "data": ["data", "analytics", "analyst", "business intelligence", "reporting", "bi ", "insights",
             "research", "controlling", "statistik"],
    "qa-test": ["qa", "quality assurance", "test", "quality engineer", "softwaretester", "prüf"],
    "dev": ["developer", "engineer", "entwickler", "programmier", "software", "fullstack", "full-stack",
            "backend", "frontend", "web"],
    "writing-content": ["writer", "author", "redakteur", "content", "documentation", "dokumentation",
                        "copywriter", "editor", "localization", "übersetz", "translator"],
    "ops-coordination": ["operations", "koordinator", "coordinator", "projektkoordinator", "assistant",
                         "assistenz", "office manager", "backoffice", "back office", "dispatcher",
                         "logistik koordination", "supply chain analyst", "procurement"],
    "ai-training": ["ai tutor", "ai trainer", "ai training", "data annotation", "labeling", "rater",
                    "llm evaluator", "content reviewer", "ai evaluator", "prompt", "künstliche intelligenz training"],
    "product-adjacent": ["product owner", "product specialist", "produktmanager junior", "business development",
                         "growth", "crm manager", "crm administrator", "revops", "sales operations",
                         "pre-sales", "presales", "technical account"],
    "other-tech": [],  # catch-all
}


def fetch(url):
    req = urllib.request.Request(url, headers=HEADERS)
    return urllib.request.urlopen(req, timeout=40).read()


def clean(s):
    if not s:
        return ""
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def ascii_safe(s):
    return s.encode("ascii", "replace").decode("ascii")


RAW = []


def collect(title, company, location, remote_flag, tags, url, desc, source, salary=""):
    if not title or not url:
        return
    RAW.append({
        "title": clean(title), "company": clean(company), "location": clean(location),
        "remote_flag": remote_flag, "tags": tags, "url": url.strip(), "desc": desc,
        "source": source, "salary": clean(salary),
    })


# ---------- SOURCES ----------

def src_arbeitnow():
    for page in range(1, 26):
        try:
            data = json.loads(fetch(f"https://www.arbeitnow.com/api/job-board-api?page={page}"))
        except Exception as e:
            print(f"  arbeitnow p{page} stop: {ascii_safe(str(e))[:60]}")
            break
        jobs = data.get("data", [])
        if not jobs:
            break
        for j in jobs:
            collect(j.get("title", ""), j.get("company_name", ""),
                    "REMOTE-flag" if j.get("remote") else j.get("location", ""),
                    bool(j.get("remote")), j.get("tags", []), j.get("url", ""),
                    clean(j.get("description", ""))[:1500], "arbeitnow")
        time.sleep(0.3)


def src_remoteok():
    try:
        data = json.loads(fetch("https://remoteok.com/api"))
    except Exception as e:
        print(f"  remoteok fail: {ascii_safe(str(e))[:60]}")
        return
    for j in data[1:]:
        salary = ""
        if j.get("salary_min") and j.get("salary_max"):
            salary = f"${j['salary_min']:,}-${j['salary_max']:,}"
        collect(j.get("position", ""), j.get("company", ""), j.get("location") or "Worldwide",
                True, j.get("tags", []),
                j.get("url") or f"https://remoteok.com/remote-jobs/{j.get('slug','')}",
                clean(j.get("description", ""))[:1500], "remoteok", salary)


def src_remotive():
    for cat in ["software-dev", "customer-support", "data", "qa", "writing", "sales", "finance-legal",
                "business", "all-others"]:
        try:
            data = json.loads(fetch(f"https://remotive.com/api/remote-jobs?category={cat}&limit=300"))
        except Exception:
            continue
        for j in data.get("jobs", []):
            collect(j.get("title", ""), j.get("company_name", ""),
                    j.get("candidate_required_location") or "worldwide", True, [],
                    j.get("url", ""), clean(j.get("description", ""))[:1500], "remotive",
                    j.get("salary", "") or "")


def src_wwr():
    feeds = ["remote-programming-jobs", "remote-customer-support-jobs", "remote-quality-assurance-jobs",
             "remote-devops-sysadmin-jobs", "remote-copywriting-jobs", "remote-business-and-management-jobs",
             "remote-marketing-jobs", "remote-data-jobs", "remote-administrative-jobs",
             "remote-all-others-jobs"]
    for f in feeds:
        try:
            root = ET.fromstring(fetch(f"https://weworkremotely.com/categories/{f}.rss"))
        except Exception:
            continue
        for item in root.iter("item"):
            collect(item.findtext("title", ""), "", "REMOTE", True, [],
                    item.findtext("link", ""), clean(item.findtext("description", ""))[:1500], "wwr")


def src_jobicy():
    for ind in ["dev", "support", "data-science", "marketing", "business", "writing", "qa"]:
        try:
            data = json.loads(fetch(f"https://jobicy.com/api/v2/remote-jobs?count=50&industry={ind}"))
        except Exception:
            continue
        for j in data.get("jobs", []):
            loc = j.get("jobLocation") or "Anywhere"
            salary = ""
            if j.get("annualSalaryMin"):
                salary = f"${j.get('annualSalaryMin'):,}-{j.get('annualSalaryMax',0):,} {j.get('salaryCurrency','')}"
            collect(j.get("jobTitle", ""), j.get("companyName", ""), loc, True, [],
                    j.get("url", ""), clean(j.get("jobDescription", ""))[:1500], "jobicy", salary)


def _ba_field(card, field):
    m = re.search(rf'id="eintrag-\d+-{field}"[^>]*>(.*?)</div>', card, re.S)
    if not m:
        return ""
    txt = re.sub(r"<[^>]+>", "", m.group(1))
    txt = txt.replace("&nbsp;", " ").strip()
    txt = re.sub(r"^\d{1,2}\.\s(?=\D)", "", txt)  # "1. Title" -> "Title" but keep "50.000 €"
    return txt.strip()


def src_arbeitsagentur():
    """Bundesagentur fuer Arbeit jobsuche - HTML scrape (API key is 403).

    Broad terms covering all of the candidate's job families, homeoffice filter on.
    ~25 results per page; cap pages to stay polite.
    """
    terms = ["software", "IT", "daten", "support", "test", "analyst",
             "entwickler", "englisch", "python", "automation", "administrator",
             "helpdesk", "customer", "technical writer", "redaktion", "qa"]
    seen_ids = set()
    for term in terms:
        for page in range(1, 11):
            url = (f"https://www.arbeitsagentur.de/jobsuche/suche?was={urllib.parse.quote(term)}"
                   f"&wo=deutschland&arbeitsmodelle=homeoffice&seite={page}")
            try:
                html = fetch(url).decode("utf-8", "replace")
            except Exception as e:
                print(f"  BA {term} p{page} stop: {ascii_safe(str(e))[:50]}")
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
                salary = _ba_field(card, "gehaltsspanne")
                ho = _ba_field(card, "homeoffice")
                desc = f"{ort} | {salary} | HO: {ho} | {title}"
                if not title:
                    continue
                collect(title, firma, ort or "Deutschland (Homeoffice)", True, [],
                        url_job, desc[:600], "arbeitsagentur", salary)
                n_new += 1
            if n_new == 0:
                break
            time.sleep(0.4)


def src_testdevjobs():
    for feed in ["https://testdevjobs.com/feed", "https://testdevjobs.com/feed.xml",
                 "https://testdevjobs.com/rss.xml", "https://testdevjobs.com/rss"]:
        try:
            root = ET.fromstring(fetch(feed))
            items = list(root.iter("item"))
            if not items:
                continue
            for item in items:
                collect(item.findtext("title", ""), "", "check listing", False, [],
                        item.findtext("link", ""), clean(item.findtext("description", ""))[:1000],
                        "testdevjobs")
            return
        except Exception:
            continue


UA_CHROME = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


def src_unjobs():
    """UNjobs.org aggregator - UN agencies + NGOs, home-based/remote sections."""
    for section in ["home-based", "remote"]:
        for page in range(1, 18):
            url = f"https://unjobs.org/duty_stations/{section}/{page}" if page > 1 \
                else f"https://unjobs.org/duty_stations/{section}"
            try:
                req = urllib.request.Request(url, headers={"User-Agent": UA_CHROME})
                html = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace")
            except Exception as e:
                print(f"  unjobs {section} p{page} stop: {ascii_safe(str(e))[:50]}")
                break
            # entries: <a class="jtitle" href=".../vacancies/ID">Title, Loc, Home based</a><br>Org<br>Updated:
            n = 0
            for m in re.finditer(
                    r'<a[^>]*class="jtitle"[^>]*href="(https://unjobs\.org/vacancies/\d+)"[^>]*>(.*?)</a><br>(.*?)<br>Updated:',
                    html, re.S):
                url_job = m.group(1)
                text = clean(m.group(2))
                org = clean(m.group(3))
                if not text or len(text) < 3:
                    continue
                # text may contain ", Home based" suffix -> strip trailing location-ish
                title = re.sub(r",\s*(Home based|Remote|Hybrid)[^,]*$", "", text).strip()
                collect(title, org, "Remote/Home-based", True, [],
                        url_job, text[:600], "unjobs")
                n += 1
            if n == 0:
                break
            time.sleep(0.35)


def src_council_europe():
    """Council of Europe jobs - searchable listing page."""
    try:
        url = "https://www.coe.int/en/web/jobs/vacancies"
        req = urllib.request.Request(url, headers={"User-Agent": UA_CHROME})
        html = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace")
    except Exception as e:
        print(f"  council_europe fail: {ascii_safe(str(e))[:60]}")
        return
    # find vacancy links
    for m in re.finditer(r'href="(/en/web/jobs/[^"]*-/job/[^"]+|https://jobs\.coe\.net/[^"]+)"[^>]*>(.*?)</a>',
                         html, re.S):
        url_job = m.group(1)
        if url_job.startswith("/"):
            url_job = "https://www.coe.int" + url_job
        title = clean(m.group(2))
        if not title or len(title) < 4:
            continue
        collect(title, "Council of Europe", "Strasbourg/Remote", False, [],
                url_job, title[:600], "council_europe")


def src_nodesk():
    """NoDesk RSS - small (10 items) but free. Regex-parsed (entities break ET)."""
    try:
        raw = fetch("https://nodesk.co/remote-jobs/index.xml").decode("utf-8", "replace")
    except Exception as e:
        print(f"  nodesk fail: {ascii_safe(str(e))[:60]}")
        return
    for m in re.finditer(r"<item>.*?<title>(.*?)</title>.*?<link>(.*?)</link>.*?<description>(.*?)</description>.*?</item>", raw, re.S):
        title = clean(m.group(1))
        link = m.group(2).strip()
        desc = clean(m.group(3))
        if title and link:
            collect(title, "", "REMOTE", True, [], link, desc[:1000], "nodesk")


GREENHOUSE_SLUGS = [
    # tracker history + verified
    "canonical", "remotepeople", "xai", "mozilla",
    # big tech / remote-friendly
    "stripe", "airbnb", "anthropic", "datadog", "figma", "coinbase", "robinhood",
    "reddit", "gitlab", "shopify", "automatticcareers", "splice", "contentstack",
    "marqeta", "earnin", "avride", "elastic", "hashicorp", "digitalocean", "cloudflare",
    "twilio", "mongodb", "confluent", "palantir", "asana", "mural", "miro", "n26",
    "getyourguide", "hellofresh", "zalando", "deliveryhero", "klarna", "coursera",
    "udemy", "datacamp", "pluralsight", "udacity", "duolingo", "openclassrooms",
    "klaviyo", "braze", "iterable", "amplitude", "mixpanel", "hotjar", "optimizely",
    "launchdarkly", "toast", "adyen", "chargebee", "zuora", "sofi", "chime", "affirm",
    "wealthfront", "betterment", "expedia", "tripadvisor", "lyft", "uber", "instacart",
    "doordash", "grubhub", "niantic", "ubisoft", "ea", "king", "supercell", "rovio",
    "wargaming", "ccp", "riotgames", "epicgames", "unity", "roblox", "discord",
    "slack", "zoom", "dropbox", "box", "notion", "asana", "monday", "clickup",
    "smartsheet", "wrike", "proofhub", "teamwork", "nifty", "hive", "airtable",
    "coda", "quip", "confluence", "notion", "evernote", "onenote", "bear", "ulysses",
    "grammarly", "hemingway", "prowritingaid", "languagetool", "deepl", "crowdin",
    "lokalise", "phrase", "transifex", "poeditor", "weglot", "gengo", "unbabel",
    "cloudflare", "fastly", "akamai", "imperva", "radware", "f5", "citrix", "vmware",
    "redhat", "suse", "canonical", "docker", "kubernetes", "rancher", "portainer",
    "grafana", "prometheus", "datadog", "newrelic", "splunk", "elastic", "sumologic",
    "logz", "papertrail", "logdna", "mezmo", "honeycomb", "lightstep", "instana",
    "dynatrace", "appdynamics", "newrelic", "pingdom", "statuspage", "uptimerobot",
]


def src_greenhouse():
    """Greenhouse public boards API - no key. Bad slugs 404 gracefully."""
    print(f"  greenhouse: trying {len(GREENHOUSE_SLUGS)} slugs")
    ok = 0
    for slug in GREENHOUSE_SLUGS:
        try:
            data = json.loads(fetch(
                f"https://boards-api.greenhouse.io/v1/boards/{urllib.parse.quote(slug)}/jobs"))
        except Exception:
            continue
        jobs = data.get("jobs", [])
        if not jobs:
            continue
        ok += 1
        for j in jobs:
            loc = (j.get("location") or {}).get("name", "") if isinstance(j.get("location"), dict) else str(j.get("location") or "")
            remote = "remote" in loc.lower()
            collect(j.get("title", ""), j.get("company_name", slug), loc, remote,
                    [], j.get("absolute_url", "") or f"https://job-boards.greenhouse.io/{slug}",
                    "", "greenhouse")
        time.sleep(0.2)
    print(f"  greenhouse: {ok} boards live")


LEVER_SLUGS = [
    "spotify", "netflix", "shopee", "agoda", "kayak", "opentable", "expedia",
    "lyft", "uber", "doordash", "instacart", "sofi", "chime", "affirm", "toast",
    "adyen", "chargebee", "zuora", "wealthfront", "betterment", "duolingo",
    "niantic", "ubisoft", "discord", "slack", "zoom", "dropbox", "box", "airtable",
    "grammarly", "crowdin", "lokalise", "cloudflare", "fastly", "redhat", "suse",
    "docker", "grafana", "splunk", "netflix", "hulu", "disney", "warner", "nbc",
    "cbs", "abc", "fox", "pbs", "npr", "bbc", "guardian", "nytimes", "washingtonpost",
    "economist", "ft", "bloomberg", "reuters", "ap", "cnn", "nbcnews", "abcnews",
]


def src_lever():
    """Lever public postings API - no key. Bad slugs 404 gracefully."""
    print(f"  lever: trying {len(LEVER_SLUGS)} slugs")
    ok = 0
    for slug in LEVER_SLUGS:
        try:
            data = json.loads(fetch(
                f"https://api.lever.co/v0/postings/{urllib.parse.quote(slug)}?mode=json"))
        except Exception:
            continue
        if not isinstance(data, list) or not data:
            continue
        ok += 1
        for j in data:
            cats = j.get("categories") or {}
            loc = cats.get("location", "")
            remote = "remote" in loc.lower()
            collect(j.get("text", ""), slug, loc, remote,
                    [cats.get("department", "") or "", cats.get("team", "") or ""],
                    j.get("hostedUrl", "") or j.get("applyUrl", "") or f"https://jobs.lever.co/{slug}",
                    clean(j.get("description", ""))[:1200], "lever")
        time.sleep(0.2)
    print(f"  lever: {ok} boards live")


def src_matcha():
    """Matcha.fm - ItemList JSON-LD per category, includes $pay in snippet."""
    cats = ["customer-support", "operations", "software-engineer", "new-grad"]
    for cat in cats:
        for suffix in ["/eu", ""]:
            try:
                html = fetch(f"https://matcha.fm/jobs/{cat}{suffix}").decode("utf-8", "replace")
            except Exception:
                continue
            found = False
            for m in re.finditer(r'<script type="application/ld\+json">(.*?)</script>', html, re.S):
                try:
                    d = json.loads(m.group(1))
                except Exception:
                    continue
                if not isinstance(d, dict) or d.get("@type") != "ItemList":
                    continue
                for e in d.get("itemListElement", []):
                    name = e.get("name", "")
                    url = e.get("url", "")
                    desc = re.sub(r"<[^>]+>", " ", e.get("description", ""))
                    desc = re.sub(r"\s+", " ", desc).strip()
                    if not name or not url:
                        continue
                    # name like "Customer Care Agent - Remote from anywhere at VIDRUSH"
                    title, _, company = name.partition(" at ")
                    loc = "REMOTE" if "remote" in name.lower() else ""
                    pay_m = re.search(r"\$[\d,.]+K?\s*[-–—]\s*\$?[\d,.]+K?", desc)
                    collect(title.strip(), (company or "").strip(), loc, bool(loc),
                            [], url, desc[:800], "matcha",
                            pay_m.group(0) if pay_m else "")
                    found = True
            if found:
                break
            time.sleep(0.3)


def src_wantremote():
    """WantRemote - category pages, /job/ detail links with card text."""
    cats = ["customer-support", "customer-success-manager", "implementation-engineer",
            "solutions-architect", "solutions-consultant", "backend-developer",
            "software-engineer"]
    for cat in cats:
        try:
            html = fetch(f"https://wantremote.com/jobs/{cat}").decode("utf-8", "replace")
        except Exception:
            continue
        # split into card-ish chunks around job links
        for m in re.finditer(r'<a[^>]*href="(/job/[a-z0-9-]+)"[^>]*>(.*?)</a>', html, re.S):
            url = "https://wantremote.com" + m.group(1)
            anchor = clean(m.group(2))
            if len(anchor) < 4 or len(anchor) > 120:
                continue
            collect(anchor, "", "REMOTE", True, [], url, anchor[:300], "wantremote")
        time.sleep(0.3)


def src_dynamite():
    """DynamiteJobs - /category/remote-X-jobs pages."""
    cats = ["remote-customer-support-jobs", "remote-customer-success-jobs",
            "remote-technical-support-jobs", "remote-qa-jobs", "remote-data-analyst-jobs",
            "remote-software-engineer-jobs", "remote-data-entry-jobs",
            "remote-virtual-assistant-jobs"]
    for cat in cats:
        try:
            html = fetch(f"https://dynamitejobs.com/category/{cat}").decode("utf-8", "replace")
        except Exception:
            continue
        for m in re.finditer(r'href="(/company/[a-z0-9-]+/remote-job/[a-z0-9-]+)"', html):
            url = "https://dynamitejobs.com" + m.group(1)
            title = m.group(1).split("/remote-job/")[-1].replace("-", " ").title()
            collect(title, "", "REMOTE", True, [], url, title[:300], "dynamite")
        time.sleep(0.3)


def src_dailyremote():
    """DailyRemote - /remote-X-jobs pages, /remote-job/ links."""
    cats = ["remote-customer-support-jobs", "remote-customer-success-jobs",
            "remote-technical-support-jobs", "remote-qa-jobs", "remote-data-analyst-jobs"]
    for cat in cats:
        try:
            html = fetch(f"https://dailyremote.com/{cat}").decode("utf-8", "replace")
        except Exception:
            continue
        for m in re.finditer(r'<a[^>]*href="(/remote-job/[a-z0-9-]+)"[^>]*>(.*?)</a>', html, re.S):
            url = "https://dailyremote.com" + m.group(1)
            anchor = clean(m.group(2))
            if len(anchor) < 5 or len(anchor) > 140:
                continue
            collect(anchor, "", "REMOTE", True, [], url, anchor[:300], "dailyremote")
        time.sleep(0.3)


# ---------- ELIMINATION PIPELINE ----------

# Easily commutable from the candidate's home base (<= ~1h): local + 1h-train ring.
# EXAMPLE ring around Cologne - edit this list for your own home city.
COMMUTABLE = ["koeln", "cologne", "bonn", "duesseldorf", "dusseldorf", "leverkusen",
              "troisdorf", "siegburg", "bruehl", "bruhl", "huerth", "hurth",
              "dormagen", "neuss", "bergisch gladbach", "wesseling",
              "aachen", "koblenz", "muenster", "muenstermaifeld"]


def commutable(location):
    loc = location.lower()
    return any(c in loc for c in COMMUTABLE)


# Region logic: a job survives only if its LOCATION allows Germany.
# EU/EMEA markers -> OK. Non-EU markers without EU markers -> kill.
# Boards where location is authoritative (remoteok/jobicy/ashby): unknown
# non-EU city -> kill. "Worldwide/Anywhere/Global" -> always OK.
GLOBAL_OK = ["worldwide", "anywhere", "global", "any location", "location independent",
             "work from anywhere", "earth", "distributed"]

EU_EMEA = ["germany", "deutschland", "dach", "europe", "emea", "european union", " eu ", "e.u.",
           "berlin", "munich", "münchen", "hamburg", "cologne", "köln", "frankfurt", "stuttgart",
           "düsseldorf", "dusseldorf", "dresden", "leipzig", "hannover", "nuremberg", "nürnberg",
           "bremen", "bonn", "karlsruhe", "heidelberg", "mannheim", "freiburg", "aachen",
           "thuringia", "thüringen", "bavaria", "bayern", "saxony",
           "austria", "vienna", "wien", "graz", "linz", "salzburg", "innsbruck",
           "switzerland", "zurich", "zürich", "geneva", "genf", "basel", "bern", "lausanne",
           "poland", "warsaw", "krakow", "kraków", "wroclaw", "gdansk", "poznan", "pl-",
           "czech", "prague", "brno", "slovakia", "bratislava", "hungary", "budapest",
           "romania", "bucharest", "cluj", "timisoara", "bulgaria", "sofia", "plovdiv",
           "france", "paris", "lyon", "marseille", "toulouse", "lille", "nantes", "bordeaux",
           "netherlands", "amsterdam", "rotterdam", "utrecht", "eindhoven", "the hague",
           "belgium", "brussels", "antwerp", "ghent", "luxembourg", "benelux",
           "spain", "madrid", "barcelona", "valencia", "seville", "bilbao", "malaga",
           "portugal", "lisbon", "porto", "braga", "italy", "milan", "rome", "turin",
           "ireland", "dublin", "cork", "galway", "limerick", "uk", "united kingdom",
           "london", "manchester", "edinburgh", "glasgow", "bristol", "leeds", "birmingham",
           "cambridge", "oxford", "belfast", "cardiff", "sweden", "stockholm", "gothenburg",
           "malmö", "malmo", "uppsala", "denmark", "copenhagen", "aarhus", "odense",
           "finland", "helsinki", "tampere", "turku", "oulu", "norway", "oslo", "bergen",
           "estonia", "tallinn", "tartu", "latvia", "riga", "lithuania", "vilnius", "kaunas",
           "croatia", "zagreb", "split", "slovenia", "ljubljana", "malta", "cyprus", "nicosia",
           "iceland", "reykjavik", "remote - europe", "remote europe", "remote, emea",
           "remote - emea", "remote eu", "european", "cet", "cest", "gmt", "bst"]

NON_EU = ["united states", "u.s.", "usa", "us-ca", "us-ny", "us-tx", "us-wa", "us-co", "us-ma",
          "us-fl", "us-il", "us-ga", "us-az", "us-or", "us-dc", "namer", "amer", "apac", "latam",
          "anz", "north america", "south america", "americas", "san francisco", "new york", "nyc",
          "sf bay", "bay area", "silicon valley", "boston", "austin", "miami", "chicago", "seattle",
          "denver", "boulder", "los angeles", "la ", "san diego", "menlo park", "redwood city",
          "foster city", "mountain view", "palo alto", "sunnyvale", "san jose", "oakland",
          "atlanta", "dallas", "houston", "phoenix", "portland", "raleigh", "salt lake city",
          "nashville", "philadelphia", "baltimore", "detroit", "minneapolis", "st louis",
          "kansas city", "cleveland", "columbus", "cincinnati", "indianapolis", "milwaukee",
          "pittsburgh", "buffalo", "richmond", "charlotte", "orlando", "tampa", "jacksonville",
          "new orleans", "memphis", "louisville", "oklahoma city", "albuquerque", "tucson",
          "las vegas", "reno", "sacramento", "fresno", "long beach", "colorado springs", "omaha",
          "tulsa", "wichita", "des moines", "little rock", "jackson", "birmingham", "huntsville",
          "anchorage", "honolulu", "hawaii", "washington dc", "washington, dc", " dc ", "arlington",
          "alexandria", "bethesda", "canada", "toronto", "vancouver", "montreal", "ottawa",
          "calgary", "edmonton", "waterloo", "quebec", "mexico", "mexico city", "cdmx",
          "guadalajara", "monterrey", "brazil", "brasil", "sao paulo", "rio de janeiro",
          "argentina", "buenos aires", "chile", "santiago", "colombia", "bogota", "peru", "lima",
          "costa rica", "san jose cr", "puerto rico", "san juan", "jamaica", "dominican",
          "india", "bengaluru", "bangalore", "chennai", "mumbai", "delhi", "new delhi",
          "hyderabad", "pune", "kolkata", "ahmedabad", "noida", "gurgaon", "gurugram", "jaipur",
          "kochi", "coimbatore", "indore", "dehradun", "pakistan", "karachi", "lahore",
          "islamabad", "bangladesh", "dhaka", "sri lanka", "colombo", "nepal", "kathmandu",
          "philippines", "manila", "cebu", "vietnam", "hanoi", "ho chi minh", "thailand",
          "bangkok", "malaysia", "kuala lumpur", "indonesia", "jakarta", "bali", "singapore",
          "hong kong", "taiwan", "taipei", "japan", "tokyo", "osaka", "kyoto", "korea", "seoul",
          "china", "beijing", "shanghai", "shenzhen", "guangzhou", "chengdu", "hangzhou",
          "australia", "sydney", "melbourne", "brisbane", "perth", "adelaide", "canberra",
          "gold coast", "sunshine coast", "warana", "new south wales", "queensland", "victoria au",
          "new zealand", "auckland", "wellington", "christchurch", "taranaki", "nelson",
          "canterbury", "otago", "palmerston", "hamilton nz", "dunedin", "uae", "dubai",
          "abu dhabi", "saudi", "riyadh", "jeddah", "qatar", "doha", "kuwait", "bahrain",
          "oman", "muscat", "israel", "tel aviv", "jerusalem", "haifa", "turkey", "istanbul",
          "ankara", "egypt", "cairo", "morocco", "casablanca", "tunisia", "algeria", "nigeria",
          "lagos", "kenya", "nairobi", "ghana", "accra", "south africa", "cape town",
          "johannesburg", "durban", "pretoria", "zimbabwe", "uganda", "tanzania", "ethiopia",
          "trinidad", "port of spain", "johannesburg", "remote - us", "remote us", "remote, us",
          "remote-us", "remote - amer", "remote, amer", "remote - apac", "remote, apac",
          "remote - canada", "remote - mexico", "remote - latam", "us remote", "usa remote",
          "ukraine", "kyiv", "kiev", "moldova", "chisinau", "georgia", "tbilisi", "armenia",
          "yerevan", "belarus", "minsk", "russia", "moscow", "kazakhstan", "astana", "almaty"]


def _has_marker(loc, markers):
    for m in markers:
        if len(m) <= 4:
            if re.search(rf"\b{re.escape(m)}\b", loc):
                return True
        elif m in loc:
            return True
    return False


def region_ok(j):
    loc = j["location"].lower().strip()
    loc = re.sub(r"[.]", "", loc)  # "U.S." -> "us" so markers match
    if _has_marker(loc, GLOBAL_OK):
        return True
    has_eu = _has_marker(loc, EU_EMEA)
    has_noneu = _has_marker(loc, NON_EU)
    if has_noneu and not has_eu:
        return False
    if has_eu:
        return True
    if not loc or loc in ("remote", "remote-first", "fully remote", "100% remote", "remote-flag",
                          "check listing", "deutschland (homeoffice)"):
        return True
    # boards where the location field is authoritative: unknown place -> kill
    if j["source"] in ("remoteok", "jobicy", "ashby"):
        return False
    return True


def src_ashby():
    """Ashby public posting API - no key needed. Bad slugs 404 gracefully."""
    # registry from github saeedghandali/ashbyhq + known heavy Ashby users
    slugs = set()
    try:
        reg = json.loads(fetch(
            "https://raw.githubusercontent.com/saeedghandali/ashbyhq/main/src/sources/registry.json"))
        for r in reg:
            if r.get("enabled", True):
                slugs.add(r["ashbySlug"])
    except Exception as e:
        print(f"  ashby registry fetch fail: {ascii_safe(str(e))[:50]}")
    slugs.update([
        "openai", "Airwallex", "Snowflake", "LILT", "Crusoe", "Bjak", "Fluidstack",
        "ElevenLabs", "Halter", "Clera", "Legora", "AppliedIntuition", "Harvey",
        "Leland", "ICEYE", "Talkiatry", "Deliveroo", "Mistral", "Linear", "Docker",
        "Cohere", "cursor", "Perplexity", "ScaleAI", "Vercel", "Supabase", "Retool",
        "n8n", "Posthog", "Brex", "Mercury", "Vanta", "Drata", "Rippling", "Remote",
        "OysterHR", "Lovable", "Replit", "Windsurf", "Cognition", "Sierra", "Decagon",
        "Glean", "Writer", "Heap", "dbt", "Fivetran", "Airbyte", "Hightouch", "Hex",
        "Mode", "Metabase", "Sigma", "Dagster", "Prefect", "Astronomer", "Temporal",
        "Render", "Railway", "Fly.io", "Netlify", "Datadog", "PagerDuty", "incident.io",
        "FireHydrant", "Rootly", "Sentry", "Honeycomb", "Chronosphere", "GrafanaLabs",
        "Elastic", "Confluent", "Redpanda", "Aiven", "ClickHouse", "Starburst", "Dremio",
        "MotherDuck", "Tinybird", "Materialize", "SingleStore", "CockroachDB",
        "PlanetScale", "Neon", "Xata", "Turso", "MongoDB", "Redis", "Algolia",
        "Typesense", "Meilisearch", "Pinecone", "Weaviate", "Qdrant", "LangChain",
        "WeightsBiases", "Arize", "WhyLabs", "Evidently", "Soda", "MonteCarlo",
        "Metaplane", "Anomalo", "Atlan", "Secoda", "Castor", "SelectStar", "Matillion",
        "Rivery", "Estuary", "Polytomic", "Decodable", "Conduktor", "WarpStream", "Buf",
        "Speakeasy", "Stainless", "Fern", "ReadMe", "Mintlify", "GitBook", "Stoplight",
        "Postman", "Tailscale", "Twingate", "Teleport", "strongDM", "HashiCorp",
        "Kraken", "Bitpanda", "Trade Republic", "Scalable Capital", "Raisin", "N26",
        "Moss", "Pleo", "Spendesk", "Qonto", "Shine", "Agicap", "Pennylane", "Spendflow",
        "Taxfix", "Forto", "sennder", "Forto", "Flix", "GetYourGuide", "Omio",
        "HomeToGo", "Holidu", "Limehome", "Raus", "Wunderflats", "Homelike", "Habyt",
        "Livisi", "Tado", "1KOMMA5", "Enpal", "Zolar", "thermondo", "Octopus Energy",
        "Tibber", "Ostrom", "Lumenaza", "gridX", "The Mobility House", "ubitricity",
        "Ionity", "Fastned", "Allego", "Elvah", "ChargeX", "Compleo", "Wirelane",
        "Personio", "Hibob", "Factorial", "Kenjo", "Workmotion", "Lano", "Localyze",
        "Circula", "Moss", "Finn", "Clark", "Wefox", "Getsafe", "Adam Riese", "Friday",
        "Ottonova", "Feather", "Luko", "Lemonade", "Wefox", "Element", "Coya",
    ])
    print(f"  ashby: trying {len(slugs)} slugs")
    ok = 0
    for slug in sorted(slugs):
        try:
            data = json.loads(fetch(
                f"https://api.ashbyhq.com/posting-api/job-board/{urllib.parse.quote(slug)}"))
        except Exception:
            continue
        jobs = data.get("jobs", [])
        if not jobs:
            continue
        ok += 1
        for j in jobs:
            locs = j.get("location") or ""
            if isinstance(locs, list):
                locs = "; ".join(l.get("name", "") for l in locs)
            remote = bool(j.get("isRemote")) or "remote" in str(locs).lower()
            comp = ""
            c = j.get("compensation")
            if isinstance(c, dict):
                comp = c.get("compensationTierSummary", "") or ""
            collect(j.get("title", ""), slug, str(locs), remote,
                    [j.get("department", "") or "", j.get("employmentType", "") or ""],
                    j.get("jobUrl", "") or f"https://jobs.ashbyhq.com/{slug}",
                    clean(j.get("descriptionHtml", "") or j.get("descriptionPlain", ""))[:1500],
                    "ashby", comp)
        time.sleep(0.25)
    print(f"  ashby: {ok} boards live")

def parse_pay(salary, desc):
    text = (salary + " " + desc[:400]).lower()
    m = re.findall(r"(\d{2,3})[.,]?(\d{3})\s*(eur|euro|usd|\$|€)", text)
    if m:
        vals = [int(a.replace(",", "")) * 1000 // 1000 + int(b) for a, b, _ in m]
        vals = [int(a) * 1000 + int(b) for a, b, _ in m]
        return max(vals) / 1000 if max(vals) > 100000 else max(vals)
    m2 = re.findall(r"(\d{2,3})\s*(eur|euro|usd|\$|€)\s*(pro stunde|per hour|/h|hourly|/std)", text)
    if m2:
        return float(m2[0][0]) / 1000  # signal hourly
    return None


def eliminate(j):
    t = (j["title"] + " ").lower()
    full = (j["title"] + " " + j["location"] + " " + j["desc"] + " " + j["salary"]).lower()

    # 1. not remote - but KEEP if commutable from the candidate's home base (hybrid/onsite ok)
    is_remote = j["remote_flag"] or any(w in full for w in REMOTE_WORDS)
    if not is_remote and not commutable(j["location"] + " " + j["desc"][:200]):
        return "not_remote"
    # 2. region blocked - location must allow Germany
    if not region_ok(j):
        return "region_blocked"
    if any(w in full for w in ["authorized to work in the us", "us work authorization",
                               "must be authorized to work in the united states",
                               "us citizens only", "us-based only", "located in the us only",
                               "right to work in the uk", "must be based in the uk", "uk-based only"]):
        return "region_blocked"
    # 3. seniority
    if any(w in t for w in SENIORITY):
        return "seniority"
    # 4. internship / low wage student
    if any(w in t for w in INTERNSHIP):
        return "internship"
    # 5. alien stack demanded by title
    if any(w in t for w in ALIEN_STACK):
        return "alien_stack"
    # 6. licensed profession
    if any(w in t for w in LICENSED):
        return "licensed_job"
    # 7. C1 German required
    if any(w in full for w in GERMAN_C1):
        return "german_c1"
    # C-Level German (with context guard: "present to C-level" execs must not match)
    for m in re.finditer(r"c-?level", full):
        ctx = full[max(0, m.start() - 60):m.end() + 60]
        if any(k in ctx for k in ["deutsch", "german", "sprachkenntnis", "sprachniveau"]):
            return "german_c1"
    # 7b. posting language - body written in French/Spanish/Portuguese
    desc_low = j["desc"].lower()
    if any(w in desc_low for w in FRENCH_POST):
        return "french_posting"
    if any(w in desc_low for w in SPANISH_POST):
        return "spanish_posting"
    if any(w in desc_low for w in PORTUGUESE_POST):
        return "portuguese_posting"
    fr_hits = sum(len(re.findall(rf"\b{re.escape(w)}\b", desc_low)) for w in FRENCH_STOP)
    if fr_hits > 12 and len(j["desc"]) > 300:
        return "french_posting"
    # 8. hybrid disguised as remote - keep only if commutable from the candidate's home base
    if any(w in full for w in HYBRID_TELLS):
        if not commutable(j["location"] + " " + j["desc"][:300]):
            return "hybrid_disguised"
    # 9. low pay (only if quoted)
    pay = parse_pay(j["salary"], j["desc"])
    if pay is not None:
        if 0.5 < pay < LOW_PAY_HOUR:      # hourly below floor
            return "low_pay"
        if 10 < pay < LOW_PAY_YEAR:       # yearly below floor
            return "low_pay"
    # 10. clearly irrelevant field
    if any(w in t for w in IRRELEVANT):
        return "irrelevant_field"
    return None


def family_of(title, desc):
    t = (title + " " + desc[:300]).lower()
    for fam, keys in FAMILIES.items():
        if any(k in t for k in keys):
            return fam
    return "other-tech"


def score(j):
    t = (j["title"] + " " + j["desc"] + " " + " ".join(j["tags"])).lower()
    s = 0
    if any(w in t for w in ["junior", "jr", "entry level", "einsteiger", "associate", "l1", "l2",
                            "tier 1", "tier 2", "no experience", "keine erfahrung", "quereinsteiger"]):
        s += 3
    for sk in ["python", "sql", "typescript", "playwright", "pytest", "excel", "power bi", "tableau",
               "etl", "api", "rest", "postgres", "jira", "zendesk", "intercom", "linux", "git",
               "automation", "n8n", "zapier", "html", "css", "json", "csv", "troubleshoot"]:
        if sk in t:
            s += 1
    if "english" in t and ("german" in t or "bilingual" in t):
        s += 2
    if any(w in t for w in REGION_OK):
        s += 1
    if j["salary"]:
        s += 1
    return s


def why_fit(j):
    t = (j["title"] + " " + j["desc"]).lower()
    hits = []
    mapping = {
        "customer service history (Lloyds 5y)": ["customer", "kunden"],
        "analysis work (Lloyds call analysis)": ["analys", "trend", "reporting", "insights", "report"],
        "Python portfolio": ["python"],
        "SQL/ETL portfolio": ["sql", "etl", "datenbank", "database"],
        "testing portfolio (Playwright/Vitest/Supertest)": ["test", "qa", "playwright", "quality"],
        "automation portfolio (n8n, LLM)": ["automation", "automatisierung", "n8n", "workflow", "llm", " ai ", "ki-"],
        "sysadmin history (Mindstretchers)": ["admin", "server", "infrastructure", "it support", "linux"],
        "production ops (Amazon line)": ["operations", "production", "prozess", "process"],
        "English native": ["english"],
        "German professional": ["german", "deutsch"],
        "degree-level CS": ["degree", "informatik", "computer science", "it-kentnisse", "technical"],
        "writing/communication": ["document", "writing", "content", "kommunikation", "communication"],
    }
    for label, keys in mapping.items():
        if any(k in t for k in keys):
            hits.append(label)
    return "; ".join(hits[:5])


def main():
    for fn in [src_arbeitnow, src_remoteok, src_remotive, src_wwr, src_jobicy,
               src_arbeitsagentur, src_testdevjobs, src_ashby, src_unjobs,
               src_nodesk, src_greenhouse, src_lever, src_matcha, src_wantremote,
               src_dynamite, src_dailyremote]:
        print(f"{fn.__name__}...", flush=True)
        try:
            fn()
        except Exception as e:
            print(f"  CRASH {fn.__name__}: {ascii_safe(str(e))[:80]}")
        print(f"  raw total: {len(RAW)}", flush=True)

    # dedupe
    seen = set()
    uniq = []
    for j in RAW:
        key = (j["title"].lower()[:55], j["company"].lower()[:25])
        if key in seen or not j["title"]:
            continue
        seen.add(key)
        uniq.append(j)
    print(f"unique: {len(uniq)}")

    killed = []
    kept = []
    for j in uniq:
        reason = eliminate(j)
        if reason:
            j["kill_reason"] = reason
            killed.append(j)
        else:
            j["family"] = family_of(j["title"], j["desc"])
            j["score"] = score(j)
            j["why"] = why_fit(j)
            kept.append(j)

    kept.sort(key=lambda j: -j["score"])

    # ---- incremental: split kept into NEW vs already-seen
    try:
        seen = json.loads(SEEN_FILE.read_text(encoding="utf-8")) if SEEN_FILE.exists() else {}
    except Exception:
        seen = {}
    fresh = []
    for j in kept:
        key = j["url"] or (j["title"] + j["company"])
        if key not in seen:
            j["is_new"] = True
            fresh.append(j)
        seen[key] = j["title"][:80]
    SEEN_FILE.write_text(json.dumps(seen, ensure_ascii=False, indent=1), encoding="utf-8")

    # ---- write new-jobs file (the daily actionable list)
    from datetime import date
    today = date.today().isoformat()
    nlines = [f"# NEW JOBS - {today}", "",
              f"{len(fresh)} new roles since last sweep (out of {len(kept)} surviving).", ""]
    cur = None
    for j in sorted(fresh, key=lambda x: -x["score"]):
        if j["family"] != cur:
            cur = j["family"]
            nlines.append(f"\n## {cur.upper()}\n")
        comp = f" @ {j['company']}" if j["company"] else ""
        nlines.append(f"### [ ] {j['title']}{comp}  (score {j['score']})")
        nlines.append(f"- loc: {j['location']}")
        if j["salary"]:
            nlines.append(f"- pay: {j['salary']}")
        if j["why"]:
            nlines.append(f"- fit: {j['why']}")
        nlines.append(f"- url: {j['url']}")
        nlines.append(f"- src: {j['source']}")
        nlines.append("")
    OUT_NEW.write_text("\n".join(nlines), encoding="utf-8")

    # ---- write survivors
    lines = ["# MEGA SWEEP - remote jobs surviving elimination - 21 Sep 2026", "",
             f"raw fetched: {len(RAW)} | unique: {len(uniq)} | kept: {len(kept)} | eliminated: {len(killed)}", ""]
    cur = None
    for j in kept:
        if j["family"] != cur:
            cur = j["family"]
            lines.append(f"\n## {cur.upper()} ({sum(1 for x in kept if x['family']==cur)})\n")
        comp = f" @ {j['company']}" if j["company"] else ""
        lines.append(f"### {j['title']}{comp}  (score {j['score']})")
        lines.append(f"- loc: {j['location']}")
        if j["salary"]:
            lines.append(f"- pay: {j['salary']}")
        if j["why"]:
            lines.append(f"- fit: {j['why']}")
        lines.append(f"- url: {j['url']}")
        lines.append(f"- src: {j['source']}")
        lines.append("")
    OUT_OK.write_text("\n".join(lines), encoding="utf-8")

    # ---- write eliminated
    kc = Counter(j["kill_reason"] for j in killed)
    lines = ["# ELIMINATED - funnel transparency", ""]
    for reason, n in kc.most_common():
        lines.append(f"## {reason}: {n}")
        ex = [j for j in killed if j["kill_reason"] == reason][:8]
        for j in ex:
            lines.append(f"- {j['title']} @ {j['company']} ({j['source']})")
        lines.append("")
    OUT_KILL.write_text("\n".join(lines), encoding="utf-8")

    print(f"\nKEPT {len(kept)} ({len(fresh)} NEW) | KILLED {len(killed)}")
    print("kill breakdown:", dict(kc))
    print("kept families:", dict(Counter(j['family'] for j in kept)))


if __name__ == "__main__":
    main()
