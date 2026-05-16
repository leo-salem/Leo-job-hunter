# Job Hunter

A personal, local-first job-hunting assistant. It scrapes public job sources on
demand, filters the results to junior / backend / Java roles in either the
United States and Europe or in Egypt, optionally scores each job with Claude
for fit against a stored resume summary, and serves a dashboard for you to
triage and track applications.

Everything runs in Docker on your own machine. No notifications, no auto-apply,
no third-party logins, no telemetry.

---

## What it does

- Pulls jobs from public APIs and search endpoints (Greenhouse, Lever, Ashby,
  LinkedIn guest search, Wuzzuf, Bayt, and optionally Workday and Wellfound).
- Filters by job title (Software / Backend / Java / Junior / New Grad), drops
  the obvious noise (senior, manager, frontend, mobile, QA, ML, DevOps,
  internships), and accepts only United States / Europe / Remote, or Egypt,
  depending on which region the source is tagged with.
- Deduplicates by a stable SHA-256 fingerprint of `(source, external_id)`.
- Stores everything in PostgreSQL so your Applied, Favorited, and Notes state
  survives restarts.
- Optionally scores each job 0 to 100 against your resume using Claude
  (Anthropic API key required; otherwise scoring is silently skipped and the
  dashboard falls back to sorting by newest).
- Marks jobs that disappear from the source as Closed instead of deleting
  them, so your history is preserved.
- Maintains a tombstone table so jobs you permanently delete via the
  "Submitted" button are never re-added on a future scrape, even if the
  source still lists them.

---

## Architecture

```
                Docker Compose
+--------------------------------------------------+
|  postgres 16       redis 7                       |
|       ^              ^                           |
|       |              |                           |
|  +----+--+      +----+----+      +-----------+   |
|  | api   | ---> | worker  |      | migrate   |   |
|  | FastAPI|     | Celery  |      | (one-shot |   |
|  | + HTMX |     | (AI +   |      |  Alembic) |   |
|  +--+----+      |  per-   |      +-----------+   |
|     |           |  company|                      |
|     |           |  tasks) |                      |
|     |           +---+-----+                      |
|     |               |                            |
|     v               v                            |
|  Pipeline:                                       |
|     scrapers/<source>.py                         |
|       -> filter (title + region rules)           |
|       -> dedupe (sha256 fingerprint)             |
|       -> tombstone check                         |
|       -> upsert into Postgres                    |
|       -> mark unseen rows as Closed              |
|       -> AI score new rows (optional)            |
+--------------------------------------------------+
```

No scheduler. Scrapes only run when you ask:

- Running `start.bat` (or `start.ps1` / `start.sh`) brings up the stack and
  runs a fresh scrape every time.
- Clicking "Refresh now" in the dashboard runs the same pipeline
  synchronously and reloads the page when finished.

---

## Quick start

Prerequisites: Docker Desktop installed and running.

```
git clone https://github.com/<your-account>/job-hunter.git
cd job-hunter
start.bat
```

That single command:

1. Creates `.env` from `.env.example` if it does not exist.
2. Builds the images (cached after the first run).
3. Starts Postgres, Redis, the migrator, the API, and the Celery worker.
4. Waits for the API to respond.
5. Seeds the companies list from `app/companies.yaml`.
6. Runs a fresh scrape across every active company (about two minutes).
7. Opens `http://localhost:8000` in your browser.

To stop everything:

```
stop.bat
```

Data in the `pgdata` and `redisdata` volumes is preserved across stop and
start cycles. To wipe the database completely, run `docker compose down -v`.

If you are on Linux or macOS, use `./start.sh` and `./stop.sh` instead.
If you are on PowerShell, you can also use `.\start.ps1` and `.\stop.ps1`.

---

## The home page

Opening `/` shows two cards, one per region:

- "Europe and United States" routes to `/international` and lists jobs from
  Greenhouse, Lever, Ashby, and (if enabled) Workday and Wellfound.
- "Egypt" routes to `/egypt` and lists jobs from LinkedIn (guest search),
  Wuzzuf, and (if reachable from your network) Bayt.

Each region has its own filters and counts. The same Apply, Submitted,
Favorite, Archive, and Notes actions are available in both.

---

## Job lifecycle and statuses

Two independent fields per job:

| Lifecycle  | Meaning                                                         |
| ---------- | --------------------------------------------------------------- |
| ACTIVE     | Currently posted on the source.                                 |
| CLOSED     | Was posted but has disappeared from the source. Kept in the DB. |
| ARCHIVED   | You manually archived it.                                       |

| Application status | Meaning                                                  |
| ------------------ | -------------------------------------------------------- |
| NOT_APPLIED        | Default.                                                 |
| APPLIED            | You clicked the green Apply button. Row hidden from the default view. |
| REJECTED           | You clicked Mark Rejected on the job detail page.        |
| INTERVIEWING       | Optional progression state.                              |
| OFFER              | Optional progression state.                              |

Plus a separate hard-delete path:

- The red Submitted button hard-deletes the job and writes its fingerprint
  to the `deleted_jobs` tombstone table. The orchestrator checks this
  table before inserting, so the job is never re-added on future scrapes.

User-controlled fields (Apply state, Favorite, Notes, AI score) are never
overwritten by a scrape. Only volatile job fields (title, description,
location, etc.) get updated.

---

## Filters

Title is matched against a regex include list (software engineer, backend
engineer, Java developer, Spring Boot, junior, new grad, entry-level,
graduate, associate, software engineer I) and an exclude list (senior, lead,
staff, principal, director, frontend, full-stack, mobile, ML, data, SRE,
DevOps, security, designer, QA, sales, marketing, internship, contract).

Location rules depend on the region:

- INTERNATIONAL accepts United States cities, common EU countries, and any
  job marked as remote.
- EGYPT accepts Egyptian cities (Cairo, Giza, Alexandria, Mansoura, etc.)
  and remote jobs that mention MENA / Middle East / Arab world / Africa.

Experience filter: if the description requires 3 or more years of
experience and contains no junior / new grad / 0-2 hint, the job is
rejected.

---

## Configuration

### Environment variables

Copy `.env.example` to `.env`. The interesting keys are:

| Variable           | Purpose                                                    |
| ------------------ | ---------------------------------------------------------- |
| `ANTHROPIC_API_KEY`| Enables AI scoring + cover letter + resume tailoring.      |
| `ANTHROPIC_MODEL`  | Defaults to `claude-sonnet-4-6`.                           |
| `AI_ENABLED`       | Set to `false` to disable AI even if a key is present.     |
| `AI_MAX_JOBS_PER_RUN` | Caps AI calls per refresh (default 80).                 |
| `RESUME_SUMMARY`   | Short paragraph the AI uses to score fit. Edit to match you. |
| `WELLFOUND_ENABLED`| Default `false`. Set `true` to enable the Wellfound Playwright scraper. |
| `HTTP_USER_AGENT`  | Default is a current Chrome on Windows.                    |

### Companies list

`app/companies.yaml` is the source of truth for what gets scraped. Each entry
maps a source to its public identifier:

- Greenhouse: the board token from `boards.greenhouse.io/<token>`.
- Lever: the org slug from `jobs.lever.co/<org>`.
- Ashby: the org slug from `jobs.ashbyhq.com/<org>`.
- LinkedIn: a saved search; configure `keywords` and `location` under `config`.
- Wuzzuf: a saved search; configure `keywords` under `config`.
- Bayt: a saved search; configure `keywords` under `config`.
- Workday: a per-tenant config under `config` (`host`, `tenant`, `site`).

The `target_region` field on each entry decides which dashboard the resulting
jobs appear in: `INTERNATIONAL` or `EGYPT` (default is `INTERNATIONAL`).

After editing `app/companies.yaml`, run `start.bat` again to seed and
re-scrape. The seed is idempotent: existing rows are updated, new rows are
inserted, nothing is deleted.

### Adding a new company

Append to `app/companies.yaml`:

```yaml
- slug: my-cool-startup
  name: My Cool Startup
  source: greenhouse
  external_id: my-cool-startup
  careers_url: https://example.com/careers
  target_region: INTERNATIONAL
```

Run `start.bat`. The next scrape includes the new company.

### Adding a new scraper source

1. Create `app/scrapers/<name>.py`, implementing `class FooScraper(BaseScraper)`
   with an `async def fetch(self, company) -> Iterable[RawJob]`.
2. Add the new value to the `Source` enum in `app/db/models.py`.
3. Register the class in `app/scrapers/registry.py`.
4. Add company entries to `app/companies.yaml`.
5. Run `start.bat`.

The orchestrator, filters, dedup, tombstone check, lifecycle handling, and
AI scoring all work transparently for the new source.

---

## Folder structure

```
job-hunter/
  docker-compose.yml
  Dockerfile
  .env.example
  pyproject.toml
  alembic.ini
  start.bat / start.ps1 / start.sh
  stop.bat  / stop.ps1  / stop.sh
  alembic/                  database migrations
  scripts/
    seed_companies.py       idempotent loader for companies.yaml
    run_once.py             manual one-shot of the daily pipeline
    catchup.py              no-op script kept for compatibility
  app/
    main.py                 FastAPI app, dashboard routes, /refresh endpoint
    celery_app.py           Celery factory (no beat schedule)
    config.py               pydantic-settings from .env
    companies.yaml          companies and saved searches to scrape
    db/
      models.py             SQLAlchemy 2.x models
      session.py            async + sync sessions
    repositories/           data access layer
    schemas/                pydantic DTOs (RawJob, etc.)
    scrapers/
      base.py               BaseScraper interface
      greenhouse.py / lever.py / ashby.py         clean JSON APIs
      workday.py            generic configurable scraper
      wellfound.py          Playwright, opt-in
      linkedin.py           guest-search endpoint (no login)
      wuzzuf.py             HTML scraping for Egypt
      bayt.py               HTML scraping for the Middle East
      registry.py           source -> scraper class
    pipeline/
      filters.py            title + region rules
      dedupe.py             fingerprint helper
      normalizer.py         RawJob -> Job
      orchestrator.py       runs the full pipeline per company
    ai/
      client.py             Anthropic SDK wrapper
      analyzer.py           scores and summarizes a job
      cover_letter.py       per-job cover letter
      resume_tailor.py      per-job tailored summary
      prompts/              plain-text prompt templates
    tasks/                  Celery tasks (analyze; scrape kept for manual API trigger)
    api/                    JSON endpoints
    dashboard/              Jinja templates + minimal CSS, HTMX for actions
    utils/                  http (httpx + tenacity), hashing, time
```

---

## Common commands

```
start.bat                 build + start + seed + scrape + open browser
stop.bat                  stop containers (data preserved)
docker compose down -v    stop and WIPE pgdata + redisdata (destructive)
docker compose logs -f    tail all container logs
docker compose ps         list running services
```

Manual scripts inside the api container:

```
docker compose exec api python -m scripts.seed_companies
docker compose exec api python -m scripts.run_once
docker compose exec api alembic upgrade head
docker compose exec api alembic current
```

---

## Stack

- Python 3.11
- FastAPI 0.115, Uvicorn
- SQLAlchemy 2.x async, asyncpg, psycopg
- Alembic for migrations
- Pydantic 2 and pydantic-settings
- Celery 5 with a Redis broker (worker only, no beat)
- httpx + tenacity for HTTP with retries and jitter
- BeautifulSoup4 + lxml for HTML parsing
- Playwright (only used when Wellfound is enabled)
- Anthropic SDK for Claude
- Jinja2 + HTMX 1.9 for the dashboard
- Postgres 16 and Redis 7 via Docker

---

## Known limitations

- Bayt.com returns HTTP 403 to requests from typical cloud / Docker IPs,
  apparently due to a Cloudflare-class fingerprint check. The scraper is
  correct but blocked at the network layer; entries are kept in
  `companies.yaml` in case the scraper succeeds from a different network.
- LinkedIn's guest endpoint is rate-limited and the scraper deliberately
  uses jittered delays. Expect 50-150 jobs across all configured searches.
- Wuzzuf's HTML structure uses hashed CSS class names that change over time.
  The parser falls back to href-shape detection, but a major site redesign
  could still break it.
- Workday and Wellfound are off by default. Workday requires per-tenant
  configuration; Wellfound requires Playwright and is fragile against
  Cloudflare. Enable only if you need them.
- The scrape job is a long, synchronous HTTP request when triggered from
  the Refresh button. Keep the browser tab open until it completes.
- There is no authentication. Do not expose port 8000 to the public network.

---

## License

This is a personal project. Use, fork, and adapt freely. No warranty.
