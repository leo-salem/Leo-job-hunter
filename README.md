# Job Hunter

A personal, local-first job-hunting assistant. It scrapes public job sources on
demand, filters to junior / backend / Java roles in either the United States
and Europe or in Egypt, scores each job 0-100 with a deterministic local rule
engine (no AI, no API keys, no telemetry), and serves an HTMX dashboard for
triaging and tracking applications.

Everything runs in Docker on your own machine. One command to start, one to
stop. Refresh re-scrapes every source on demand and never re-surfaces a job
you marked as Submitted.

---

## Quick start

Prerequisites: Docker Desktop installed and running.

```
git clone https://github.com/leo-salem/Leo-job-hunter.git
cd Leo-job-hunter
start.bat
```

That one command:

1. Creates `.env` from `.env.example` if it does not exist.
2. Builds the images (cached after the first run).
3. Starts Postgres, Redis, the migrator, the API, and the Celery worker.
4. Waits for the API to respond.
5. Seeds the companies list from `app/companies.yaml`.
6. Runs a fresh scrape across every active source in parallel.
7. Opens `http://localhost:8000` in your browser.

To stop everything:

```
stop.bat
```

Data in the `pgdata` and `redisdata` Docker volumes is preserved across
stop and start cycles. To wipe the database completely, run
`docker compose down -v`.

On Linux or macOS, use `./start.sh` and `./stop.sh` instead.

---

## What you get

### Home page (two regions)

Opening `/` shows two cards:

- **Europe & United States** routes to `/international` and lists jobs from
  Greenhouse, Lever, Ashby, and (optionally) Workday and Wellfound.
- **Egypt** routes to `/egypt` and lists jobs from LinkedIn (guest search),
  Wuzzuf, and (if reachable) Bayt.

Each region has its own filters, counts, and ranking strategy. The same Apply,
Submitted, Favorite, Archive, and Notes actions are available in both.

### Job lifecycle and statuses

| Lifecycle  | Meaning                                                         |
| ---------- | --------------------------------------------------------------- |
| ACTIVE     | Currently posted on the source.                                 |
| CLOSED     | Was posted, has disappeared from the source. Kept in the DB.    |
| ARCHIVED   | You manually archived it.                                       |

| Application status | Meaning                                                  |
| ------------------ | -------------------------------------------------------- |
| NOT_APPLIED        | Default.                                                 |
| APPLIED            | You clicked Apply. Row hidden from default view, kept in DB. |
| REJECTED           | You marked it rejected.                                  |
| INTERVIEWING       | Optional progression state.                              |
| OFFER              | Optional progression state.                              |

Plus a hard-delete path:

- **Submitted** (red button) hard-deletes the job and writes its fingerprint
  to the `deleted_jobs` tombstone table. The orchestrator checks the
  tombstones before inserting, so the job is **never** re-added on future
  scrapes, even if the source still lists it.

User-controlled fields (Apply state, Favorite, Notes) are never overwritten
by a scrape. Only volatile job fields (title, location, description) get
updated.

---

## Local rule-based ranking (no AI)

Each job gets a 0-100 score from a transparent rule engine. The score becomes
the default sort order on the dashboard. Every score has a one-line `quality
label`:

| Range | Label         |
| ----- | ------------- |
| 80-100 | Excellent Fit |
| 65-79  | Strong Fit    |
| 50-64  | Decent Fit    |
| 35-49  | Weak Fit      |
| 0-34   | Poor Fit      |

Every job has a `confidence` 0-100 reflecting how trustworthy the score is
(higher when the description is substantive and signals are aligned, lower
on thin descriptions or conflicting signals like "Junior in title" + "5+
years required").

### Region-aware strategy

The same rule fires with a different weight depending on which region you
are looking at:

| Strategy             | Boosts                                              | Dampens                          |
| -------------------- | --------------------------------------------------- | -------------------------------- |
| **EGYPT**            | Java / Spring / Hibernate / Kafka stack, backend specialization, recognized Egypt employers | Generic SWE titles, frontend/fullstack |
| **INTERNATIONAL**    | Generic Software Engineer (engineering-heavy), new-grad pipelines, Tier-S companies (Stripe/OpenAI/Google/etc.), visa/relocation signals, modern engineering signals (distributed systems, platform, scale) | Pure Java enterprise roles |

### Signal categories the engine reads

| Category | Examples |
|---|---|
| **Seniority** | junior / new grad / associate / mid / senior / staff / lead — detected from title; falls back to years-in-description |
| **Specialization** | backend / generic-swe / frontend / fullstack / mobile / ML / data / devops / qa / security / embedded / game |
| **Stack synergy** | Coherent Java backend (Java + Spring + Hibernate + JPA + REST), modern backend (Docker + K8s + Postgres + Redis + Kafka), frontend-heavy penalty |
| **Experience** | required / preferred years; grad-friendly phrases ("0-2 years", "new grad welcome"); penalties for 5+ years required |
| **Location** | USA / Europe / Remote / Egypt cities; remote always boosted |
| **Company tier** | Tier-S iconic (Stripe/OpenAI/Google/Meta/Netflix/...) / Tier-A strong (Asana/Twilio/Booking-class) / Tier-B recognized / Egypt Tier-1 (Instabug/Halan/Valu/...) / spam recruiter / vague ("Confidential / Our Client") |
| **Visa / relocation** | "visa sponsorship", "relocation support", "international candidates welcome" (strongly amplified for INTERNATIONAL) |
| **Modern engineering** | "distributed systems", "millions of users", "platform engineer", "cloud-native", "CI/CD", "observability" |
| **Career growth** | "mentorship", "ownership", "career growth", "graduate program", "rotational" |
| **Role intent penalties** | help desk / tier-1 support / legacy mainframe / WordPress / CMS / low-code |
| **Anti-spam** | "URGENT HIRING!!!", "Apply now!!!", WhatsApp emails, buzzword stuffing (rockstar / ninja / guru) |
| **Recency** | small boost for jobs posted in the last week; small penalty for >60 days old |
| **Description quality** | small penalty for very thin descriptions, small boost for substantive ones |

### Explainability

Every job row's score badge is a link to `/jobs/{id}/score-debug`. That
page shows:

- Final score and raw-pre-clamp score
- Confidence
- Strategy used (Egypt or International)
- Every triggered rule with weight, multiplier math, and a human-readable reason
- Positive signals (green)
- Negative signals (red)
- Detected features: normalized title, seniority, specialization, stack-in-title vs stack-in-description, required years

### Tuning the engine

Edit `app/pipeline/scoring_rules.py` (rule weights), `scoring_strategy.py`
(per-region multipliers), `scoring_signals.py` (regex banks), or
`scoring_company.py` (tier membership), then:

```
docker compose exec api python -m pytest tests/        # tests should still pass
docker compose exec api python -m scripts.rescore      # apply to all jobs (~2s)
```

No re-scrape needed. Dashboard re-sorts instantly.

---

## Refresh is on-demand only

There is no midnight cron, no startup-catchup, no background scheduler. Scrapes
only happen when:

- You run `start.bat` (calls `scripts/run_once.py` which calls `run_daily()`).
- You click "Refresh now" in the dashboard (POST `/refresh` runs the same
  pipeline synchronously, then the browser auto-reloads).

Two reasons this is deliberate:

1. You said "every refresh = fresh re-search" — no cached results.
2. Predictability — you know exactly when the tool talks to the internet.

---

## Performance and politeness

### Two-layer concurrency

1. **Global cap** (`DAILY_CONCURRENCY=4`): total companies processed in
   parallel during a scrape.
2. **Per-source caps**: layered on top so that even with 4 global slots
   free, at most N go to the same rate-limited source:
   - `LINKEDIN_CONCURRENCY=1`  (LinkedIn is the most aggressively rate-limited)
   - `WUZZUF_CONCURRENCY=2`
   - `BAYT_CONCURRENCY=2`
   - `WORKDAY_CONCURRENCY=2`
   - `WELLFOUND_CONCURRENCY=1`
   - Greenhouse / Lever / Ashby have no per-source cap (stable JSON APIs).

### Detail-fetch optimizations

Each detail-fetching scraper (LinkedIn, Wuzzuf, Bayt) does two skips before
hitting the expensive per-job HTTP:

1. **Title pre-check** — cards whose title doesn't match the filter regex
   are skipped immediately. Most LinkedIn results don't match (you only want
   junior / backend / Java), so this cuts ~80% of detail fetches.
2. **Known-fingerprint skip** — if a job's fingerprint is already in your
   DB (from any past run), the detail HTTP is skipped and a stub card is
   emitted so the orchestrator can still update `last_seen_at`.

### Politeness inside each scraper

LinkedIn / Wuzzuf / Bayt use jittered sleep delays between pagination pages
(`1.2-2.8s`) and between detail fetches (`0.4-1.5s`). Tenacity retries with
exponential backoff handle transient server hiccups (1s → 3s → 9s → 15s).

### Typical timings

| Profile | DAILY_C. | LINKEDIN_C. | Approx wall time |
|---|---:|---:|---:|
| Safe (default) | 4 | 1 | ~2-3 min |
| Balanced | 4 | 2 | ~1-2 min |
| Fast (small rate-limit risk) | 6 | 3 | ~1 min |

---

## Architecture

```
                 Docker Compose
+--------------------------------------------------+
|  postgres 16       redis 7                       |
|       ^              ^                           |
|       |              |                           |
|  +----+--+      +----+----+      +-----------+   |
|  | api    | --> | worker  |      | migrate   |   |
|  | FastAPI|     | Celery  |      | (one-shot |   |
|  | + HTMX |     | (per-   |      |  Alembic) |   |
|  +---+----+     | company |      +-----------+   |
|      |          |  tasks) |                      |
|      |          +---+-----+                      |
|      v              v                            |
|  Pipeline:                                       |
|    pre-load known fingerprints                   |
|       -> scraper.fetch(skip_fingerprints)        |
|       -> orchestrator filter (title + region)    |
|       -> dedupe (sha256 fingerprint)             |
|       -> tombstone check                         |
|       -> upsert into Postgres                    |
|       -> mark unseen rows as CLOSED              |
|       -> heuristic_score + breakdown saved       |
+--------------------------------------------------+

       Per-source concurrency:
       Greenhouse / Lever / Ashby:  global only (4)
       LinkedIn:                    1
       Wuzzuf, Bayt, Workday:       2
       Wellfound:                   1
```

---

## Folder structure

```
job-hunter/
  start.bat / start.ps1 / start.sh      one-command startup
  stop.bat  / stop.ps1  / stop.sh       graceful shutdown
  docker-compose.yml                    postgres + redis + api + worker + migrate
  Dockerfile
  .env.example                          copy to .env on first run
  pyproject.toml                        Python deps (no AI deps)
  alembic.ini  + alembic/               6 migrations: 0001 init, 0002 region,
                                        0003 tombstones, 0004 heuristic_score,
                                        0005 score metadata, 0006 drop AI
  scripts/
    seed_companies.py                   idempotent loader for companies.yaml
    run_once.py                         in-process daily pipeline (used by start.bat)
    rescore.py                          recompute heuristic_score for every job
    catchup.py                          deprecated no-op (kept for compatibility)
  tests/
    test_scoring.py                     51 tests covering every rule + ranking
  app/
    main.py                             FastAPI: home + region dashboards + /refresh +
                                        /jobs/{id}/score-debug + HTMX action endpoints
    celery_app.py                       Celery (worker only, no beat schedule)
    config.py                           pydantic-settings from .env
    companies.yaml                      companies + saved searches per source/region
    db/
      models.py                         Company, Job, ScrapeLog, SystemState, DeletedJob
      session.py                        async + sync sessions
    repositories/                       data access (companies, jobs, scrape_logs)
    schemas/                            pydantic DTOs (RawJob)
    pipeline/
      filters.py                        title + region location rules
      dedupe.py                         sha256 fingerprint
      normalizer.py                     RawJob -> Job (with scoring)
      orchestrator.py                   parallel runner + closed-detection + tombstones
      scoring.py                        public score_job(...) facade
      scoring_features.py               title normalization + seniority + spec + stack
      scoring_strategy.py               region multipliers (EGYPT vs INTERNATIONAL)
      scoring_rules.py                  rule evaluators + ScoreResult + quality_label
      scoring_signals.py                regex banks (visa/scale/growth/spam/etc.)
      scoring_company.py                tier-S / A / B / Egypt-T1 / spam / vague
    scrapers/
      base.py                           BaseScraper interface
      registry.py                       source -> scraper class
      greenhouse.py / lever.py / ashby.py    stable JSON APIs
      linkedin.py                       guest-search HTML (no login)
      wuzzuf.py                         Egypt-focused HTML
      bayt.py                           Mideast HTML (often CDN-blocked)
      workday.py                        configurable per tenant
      wellfound.py                      Playwright, opt-in
    tasks/
      daily.py                          Celery task for queued daily runs
      scrape.py                         Celery tasks for manual per-company/source
    api/
      deps.py
      routes/                           JSON API: jobs / companies / logs / trigger
    dashboard/
      templates/                        Jinja templates: home, index, job_detail,
                                        score_debug, logs, partials/job_row
      static/app.css                    minimal styling
    utils/
      http.py                           httpx + tenacity (retries + jitter)
      hashing.py                        sha256 fingerprint + prompt_hash
      time.py                           dt parsing helpers
```

---

## Configuration

### `.env`

Copy `.env.example` to `.env`. Notable keys:

| Variable                    | Default | Purpose                                          |
| --------------------------- | -------:| ------------------------------------------------ |
| `DAILY_CONCURRENCY`         | `4`     | Total concurrent companies                       |
| `LINKEDIN_CONCURRENCY`      | `1`     | LinkedIn searches in parallel                    |
| `WUZZUF_CONCURRENCY`        | `2`     | Wuzzuf searches in parallel                      |
| `BAYT_CONCURRENCY`          | `2`     | Bayt searches in parallel                        |
| `WORKDAY_CONCURRENCY`       | `2`     | Workday tenants in parallel                      |
| `WELLFOUND_CONCURRENCY`     | `1`     | Wellfound (Playwright) in parallel               |
| `WELLFOUND_ENABLED`         | `false` | Enable the Wellfound Playwright scraper          |
| `PLAYWRIGHT_HEADLESS`       | `true`  | Used only when Wellfound is enabled              |
| `HTTP_TIMEOUT_SECONDS`      | `30`    | Per-request HTTP timeout                         |
| `HTTP_MAX_RETRIES`          | `4`     | Tenacity retry attempts                          |
| `HTTP_USER_AGENT`           | Chrome  | Sent on every request                            |
| `CATCHUP_THRESHOLD_HOURS`   | `20`    | Reserved for future use                          |
| `TIMEZONE`                  | `Africa/Cairo` | Display timezone                          |

### `app/companies.yaml`

Source-of-truth for what gets scraped. Each entry maps a source to its
public identifier and tags it with a `target_region` (`INTERNATIONAL` or
`EGYPT`):

```yaml
- slug: stripe
  name: Stripe
  source: greenhouse
  external_id: stripe
  careers_url: https://stripe.com/jobs
  target_region: INTERNATIONAL

- slug: linkedin-egypt-java
  name: LinkedIn - Java in Egypt
  source: linkedin
  external_id: linkedin-egypt-java
  careers_url: https://www.linkedin.com/jobs/
  target_region: EGYPT
  config:
    keywords: java
    location: Egypt
    time_posted: r2592000     # past 30 days
    max_pages: 6
    fetch_details: true
```

After editing, run `start.bat` again — seed is idempotent.

### Identifiers per source

- **Greenhouse**: the slug after `boards.greenhouse.io/`
- **Lever**: the slug after `jobs.lever.co/`
- **Ashby**: the slug after `jobs.ashbyhq.com/`
- **LinkedIn**: any slug; configure `keywords` + `location` in `config`
- **Wuzzuf** / **Bayt**: any slug; configure `keywords` in `config`
- **Workday**: any slug; configure `host` + `tenant` + `site` in `config`

---

## Adding a new scraper source

1. Create `app/scrapers/<name>.py`, implement `class FooScraper(BaseScraper)`
   with `async def fetch(self, company, *, skip_fingerprints=None) -> Iterable[RawJob]`.
2. Add the new value to the `Source` enum in `app/db/models.py`.
3. Register the class in `app/scrapers/registry.py`.
4. Optionally add a per-source concurrency knob in `config.py`.
5. Add company entries to `app/companies.yaml`.
6. Run `start.bat`.

The orchestrator, filters, dedup, tombstone check, lifecycle handling, and
scoring all work transparently for the new source.

---

## Common commands

```
start.bat                          one-command startup + open browser
stop.bat                           graceful shutdown (data preserved)

docker compose down -v             stop + WIPE database and volumes (destructive)
docker compose ps                  list running services
docker compose logs -f             tail all container logs

# Inside the api container
docker compose exec api python -m scripts.seed_companies     # reload companies.yaml
docker compose exec api python -m scripts.run_once           # run pipeline now
docker compose exec api python -m scripts.rescore            # recompute all scores
docker compose exec api alembic upgrade head                 # apply migrations
docker compose exec api alembic current                      # current schema version
docker compose exec api python -m pytest tests/              # run scoring tests
```

---

## Testing

51 tests in `tests/test_scoring.py` covering:

- Title normalization (SWE / SDE / Jr / Sr expansion)
- Seniority detection (intern / junior / mid / senior / staff / lead)
- Specialization detection (backend / frontend / mobile / ML / data / etc.)
- Stack synergy (coherent Java stack, modern backend stack)
- Experience reasoning (grad-friendly phrases, high-years penalty)
- Region strategy (Java higher in Egypt, generic SWE higher in International)
- Company tiers (S / A / B / Egypt-T1 / spam / vague)
- Visa signals
- Modern engineering signals
- Career growth signals
- Role-intent penalties (support, legacy, low-eng)
- Anti-spam (URGENT HIRING, buzzword stuffing, keyword stuffing)
- Ranking comparisons (junior > senior, Stripe SWE > random shop backend)
- False positives (JavaScript != Java, senior overrides stack)
- Quality labels (Excellent / Strong / Decent / Weak / Poor)
- Score calibration (perfect job rarely hits 100, average job in middle)

Run:

```
docker compose exec api python -m pytest tests/ -v
```

---

## Stack

- Python 3.11
- FastAPI 0.115, Uvicorn
- SQLAlchemy 2.x async + asyncpg + psycopg
- Alembic for migrations
- Pydantic 2 and pydantic-settings
- Celery 5 with a Redis broker
- httpx + tenacity for HTTP with retries and jitter
- BeautifulSoup4 + lxml for HTML parsing
- Playwright (only if Wellfound is enabled)
- Jinja2 + HTMX 1.9 for the dashboard
- Postgres 16 and Redis 7 via Docker
- Pytest for tests

---

## Known limitations

- **Bayt.com** returns HTTP 403 to requests from typical cloud and Docker IPs
  because of a Cloudflare-class fingerprint check. The scraper is correct but
  blocked at the network layer; entries are kept in `companies.yaml` in case
  the scraper succeeds from a different network.
- **LinkedIn's guest endpoint** is rate-limited and the scraper deliberately
  uses jittered delays. Expect 50-150 jobs across all configured searches.
- **Wuzzuf's HTML** uses hashed CSS class names that change over time. The
  parser falls back to href-shape detection, but a major site redesign could
  still break it.
- **Workday** and **Wellfound** are off by default. Workday requires per-tenant
  configuration; Wellfound requires Playwright and is fragile against
  Cloudflare. Enable only if you need them.
- **Refresh button** triggers a synchronous scrape that can take 1-3 minutes.
  Keep the tab open until it completes; the page reloads automatically.
- **No authentication.** Do not expose port 8000 to the public network.

---

## License

Personal project. Use, fork, and adapt freely. No warranty.
