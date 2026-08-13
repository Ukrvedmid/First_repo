# Personal Marine Job Agent

Self-hosted vacancy monitor for a senior marine engineer moving toward a shore-based career in Germany while keeping relevant sea/offshore options open.

## Search policy

The current matching policy is deliberately strict:

- shore vacancies must be connected to shipping, ships, shipbuilding, ports, classification, subsea, offshore marine operations or marine equipment;
- the job location must be explicitly confirmed as Germany, a German federal state or a recognised German city;
- generic factory maintenance, automotive fleet, ordinary onshore wind, software and other non-maritime jobs are rejected;
- vacancies in Spain, India, the UK, the Netherlands and other countries are rejected, including generic `Remote Europe` roles.

The matching profile covers these career routes:

1. Technical Superintendent / Technical Vessel Manager / Port Engineer.
2. Marine Surveyor / Technical Inspector / Plan Approval Engineer.
3. Marine OEM Field Service / Commissioning / Technical Support.
4. Shipbuilding, retrofit, drydock and technical project roles.
5. Offshore wind with a clear SOV/CSOV or marine-operations connection.
6. Relevant Chief Engineer, DP/offshore, subsea and ROV roles located in Germany.

Current public sources include the Bundesagentur für Arbeit, BSM, RINA, Lloyd's Register, Wärtsilä, Everllence, Kongsberg Maritime, Vestas, Siemens Energy, Boskalis, DOF, Subsea7 and additional maritime employers.

No crawler can guarantee every vacancy on the internet. This project monitors configured public pages and does not bypass login pages, CAPTCHAs, robots restrictions or anti-bot controls.

## First start

```bash
cp .env.example .env
docker compose up -d --build
docker compose logs -f --tail=200 agent
```

## Telegram

Set in `.env`:

```env
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
```

Then restart:

```bash
docker compose up -d
```

A notification contains:

- A/B/C relevance tier and numerical score;
- confirmed German location and career route;
- a short Ukrainian explanation of what the vacancy is about;
- Ukrainian bullet lists with the main duties, key requirements and stated working conditions;
- matched experience terms, possible gaps, source and direct vacancy link.

## Ukrainian vacancy summaries

Only vacancies that pass both the Germany-only filter and the maritime relevance filter are summarised. The agent does not spend summarisation resources on rejected jobs.

The summary system has two modes:

### Built-in fallback — enabled automatically

No additional key is required. The agent analyses the job title, route and description, recognises common marine responsibilities and requirements, and generates a compact Ukrainian summary. This mode is deterministic and free, but less detailed than an LLM-generated summary.

### OpenAI summary — optional

When an OpenAI API key is present, the agent sends only the matched vacancy text to the Responses API and asks for a structured Ukrainian summary. Results are cached in SQLite, so the same unchanged vacancy is not summarised repeatedly.

Add to `.env`:

```env
JOB_SUMMARY_PROVIDER=auto
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-5-nano
OPENAI_BASE_URL=https://api.openai.com/v1
JOB_SUMMARY_TIMEOUT_SECONDS=45
JOB_SUMMARY_MAX_INPUT_CHARS=18000
```

`JOB_SUMMARY_PROVIDER` values:

- `auto` — use OpenAI when a key is configured, otherwise use the built-in fallback;
- `openai` — request OpenAI summaries, falling back safely when the key is absent or the request fails;
- `fallback` — never call an external summary API.

The OpenAI request uses `store: false`, strict JSON schema output, a bounded vacancy-text length and a low-cost model configurable through `OPENAI_MODEL`. API use requires a separately configured OpenAI API key and API billing.

## Safe automatic deployment

The repository has two release stages:

1. Changes are committed to `main`.
2. GitHub Actions compiles the application, imports it, runs the test suite, validates YAML and checks deployment scripts.
3. Only a successful `main` commit is fast-forwarded to `production`.
4. The server timer checks `production` every five minutes.
5. The server builds the candidate image, performs an import smoke test, starts it and verifies that the container stays healthy.
6. A failed release is rolled back automatically and is not retried until a newer production commit exists.

One-time installation on the server:

```bash
cd /home/ultbear/job-agent
git checkout main
git pull --ff-only
sudo bash ops/install-autodeploy.sh
```

Useful diagnostics:

```bash
systemctl status job-agent-autodeploy.timer --no-pager
systemctl status job-agent-autodeploy.service --no-pager
journalctl -u job-agent-autodeploy.service -n 100 --no-pager
systemctl list-timers job-agent-autodeploy.timer --no-pager
```

To force an immediate check:

```bash
sudo systemctl start job-agent-autodeploy.service
```

The `.env` file, Telegram token, optional OpenAI key and SQLite Docker volume are not committed or removed during deployments.

## Manual update

Normally this is no longer required after automatic deployment is installed:

```bash
cd ~/job-agent
git fetch origin production
git checkout -B production origin/production
docker compose up -d --build --force-recreate
```

## Run one diagnostic scan

This runs one complete scan and exits instead of waiting 30 minutes:

```bash
docker compose run --rm -e RUN_ONCE=1 agent
```

## Stop

```bash
docker compose down
```

## Data

Seen vacancy fingerprints and generated summaries are stored in the Docker volume `agent_data` as SQLite database `/data/agent.db`.

The matching signature changes automatically after profile, location or summary-policy edits. That causes still-open vacancies to be re-analysed under the new policy without creating normal recurring duplicates.
