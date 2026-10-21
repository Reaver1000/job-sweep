# job-sweep

A multi-source remote job sweep pipeline. Fetches from 24+ sources, filters with hard rules, and outputs a triage-ready list of what is actually applicable.

The design philosophy is elimination, not matching. It pulls wide, then kills what you cannot do, so whatever survives the funnel is worth reading. Expect a 95%+ kill rate and treat that as the tool working.

## Sources

| Script | Sources |
|--------|---------|
| `job_sweep.py` | Arbeitnow API, RemoteOK, Remotive, WeWorkRemotely RSS, Jobicy, Arbeitsagentur scrape, **Himalayas API, Jobgether JSON-LD**, Ashby boards (~250 companies incl. AI labs: OpenAI, DeepL, Synthesia, Character.AI, Fireworks, ElevenLabs, Mistral, Cohere, n8n...), Greenhouse boards (~150 incl. Stability AI, Together AI, Imbue), Lever, Matcha, WantRemote, Dynamite Jobs, DailyRemote, NoDesk, TestDevJobs, UN Jobs, Council of Europe |
| `corporate_sweep.py` | Workday CX API for large non-tech employers (Unilever, Sartorius, AstraZeneca — extensible tenant list) |
| `indeed_sweep.py` | Indeed Germany + UK via Playwright, remote filter, last 7 days |
| `stepstone_sweep.py` | StepStone Germany via Playwright, JSON-LD + DOM extraction |
| `linkedin_sweep.py` | LinkedIn Germany via logged-in browser context, guest API fragments through the session (bypasses IP rate limits), 4 pages per query |
| `devjobs_sweep.py` | DEVjobs.de — server-rendered category search, remote+level card filtering |
| `glassdoor_sweep.py` | Glassdoor Germany via persistent real-Chrome profile (Cloudflare Turnstile), targeted junior/remote queries |
| `ba_sweep.py` | Arbeitsagentur deep-dive with configurable search terms |

## Quickstart

```bash
pip install playwright requests
python -m playwright install chromium

# Scrapling for the Indeed verification lane (solves the Turnstile wall)
pip install scrapling patchright browserforge msgspec
python -m patchright install chromium

# one-time: log into LinkedIn once, session is saved for future sweeps
python li_login.py

# run everything
python job_sweep.py        # API/RSS/API-board sources, writes jobs_found.md (incremental)
python corporate_sweep.py  # Workday CX tenants, writes corporate_jobs.md
python indeed_sweep.py     # writes indeed_jobs.md
python stepstone_sweep.py  # writes stepstone_jobs.md
python linkedin_sweep.py   # writes linkedin_jobs.md (needs the saved session)
python devjobs_sweep.py    # writes devjobs_jobs.md
python glassdoor_sweep.py  # writes glassdoor_jobs.md (needs the Chrome profile)
python ba_sweep.py         # writes ba_new.md

# diff everything against the previous run
python diff_new.py
```

## The filter pipeline

`job_sweep.py` kills in order: not remote, region-locked (US/APAC-only), seniority titles, internships, alien stacks, licensed professions, C1-German demands, French/Spanish/Portuguese postings, disguised hybrids, low pay, irrelevant fields. Everything else is scored and family-tagged into `new_jobs.md`, incrementally, so re-running shows only what is new since last time.

## Verification

Board listings lie. Titles oversell, locations are wrong, requirements hide in the fine print. The verification layer exists because of that:

- `verify_indeed_scrapling.py` — Indeed job pages via Scrapling's StealthyFetcher with Cloudflare Turnstile auto-solve (vanilla Playwright gets 401/challenge-walled). The mobile endpoint (`/m/viewjob`) serves the full description server-side and detects expired postings.
- Ashby posting API (`/posting-api/job-board/{slug}`) returns full descriptions incl. `isRemote` flags — catches postings whose location string omits "remote" (a real bug class: one n8n role was invisible for weeks because of it).
- Workday CX API returns full job descriptions for corporate roles.

## Hard-won notes

- LinkedIn's search-results DOM renders cards without anchor tags (JS click-handlers). Extracting `/jobs/view/` links from the DOM finds 1 job instead of 25. The working approach: hit the guest API fragment endpoint from inside the logged-in browser context.
- Workday CX returns `total` only on page 1 — reading it on later pages breaks pagination.
- Glassdoor search pages pass with a persistent real-Chrome profile (`channel="chrome"`, persistent user-data dir) but job detail pages 403 vanilla requests regardless.
- Some boards (JustRemote, Flexa) are fully JS-rendered — they need a browser fetcher, not HTTP.
- The German-IT-consultancy posting pattern (client travel + "verhandlungssichere Deutschkenntnisse" + prior consulting title) is a coherent lane — if that is not your profile, filter it early.

## Output files (gitignored)

`jobs_found.md` (pool), `*_jobs.md` / `*_new.md` (per-source), `*_prev.md` (snapshots for diffing), `indeed_verify.md` (verification results).
