# job-sweep

A multi-source remote job sweep pipeline. Fetches from 20 sources, filters with hard rules, and outputs a triage-ready list of what is actually applicable.

The design philosophy is elimination, not matching. It pulls wide, then kills what you cannot do, so whatever survives the funnel is worth reading. Expect a 95%+ kill rate and treat that as the tool working.

## Sources

| Script | Sources |
|--------|---------|
| `job_sweep.py` | Arbeitnow API, RemoteOK, Remotive, WeWorkRemotely RSS, Jobicy, Arbeitsagentur scrape, Ashby boards (~250 companies), Greenhouse boards (~150), Lever, Matcha, WantRemote, Dynamite Jobs, DailyRemote, NoDesk, TestDevJobs, UN Jobs |
| `indeed_sweep.py` | Indeed Germany + UK via Playwright, remote filter, last 7 days |
| `stepstone_sweep.py` | StepStone Germany via Playwright, JSON-LD + DOM extraction |
| `linkedin_sweep.py` | LinkedIn Germany via Playwright with a saved login session |
| `ba_sweep.py` | Arbeitsagentur deep-dive with configurable search terms |

## Quickstart

```bash
pip install playwright
python -m playwright install chromium

# one-time: log into LinkedIn once, session is saved for future sweeps
python li_login.py

# run everything
python job_sweep.py        # 16 API/RSS sources, writes jobs_found.md + new_jobs.md (incremental)
python indeed_sweep.py     # writes indeed_jobs.md
python stepstone_sweep.py  # writes stepstone_jobs.md
python linkedin_sweep.py   # writes linkedin_jobs.md (needs the saved session)
python ba_sweep.py         # writes ba_new.md

# deep-verify Indeed candidates (fill JOBS in verify_indeed.py first)
python verify_indeed.py
```

## The filter pipeline

`job_sweep.py` kills in order: not remote, region-locked (US/APAC-only), seniority titles, internships, alien stacks, licensed professions, C1-German demands, French/Spanish/Portuguese postings, disguised hybrids, low pay, irrelevant fields. Everything else is scored and family-tagged into `new_jobs.md`, incrementally, so re-running shows only what is new since last time.

All the kill rules live as plain lists at the top of `job_sweep.py`. Edit them for your own profile: your commuter cities, your languages, your pay floor, your stack.

## What I learned running this

- Aggregator titles flatter. LinkedIn especially: verify the actual posting body before believing any title. A "Technical Support Specialist" was a mid-senior strategic accounts role; an "Infrastructure Support Practitioner" wanted years of rollouts. Budget one body-fetch per candidate before it enters your application list.
- The kill-rate is the feature. Out of 22,000 raw entries, roughly 1,300 survive the filters, and of those maybe 20 are worth applying to. The tool's job is finding those 20 without you reading 22,000 listings.
- Bot walls are beatable with headless-first, headed-fallback Playwright. Indeed, StepStone, and LinkedIn all work this way. LinkedIn needs a one-time manual login saved to a persistent browser profile.

## Output files

`jobs_found.md`, `new_jobs.md`, `indeed_jobs.md`, `stepstone_jobs.md`, `linkedin_jobs.md`, `ba_new.md`, `indeed_verify.md` are all generated state and git-ignored. `diff_new.py` compares a fresh sweep against the previous one so you only read the delta.

## Disclaimer

Scrapers read public pages and respect each source's tolerance. Rate limits are built in (sleeps between requests), but you are responsible for how you use this against any site's terms of service.
