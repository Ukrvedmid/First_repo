# Personal Marine Job Agent

Self-hosted vacancy monitor for a senior marine engineer moving toward a shore-based career in Germany while keeping relevant sea/offshore options open.

## What it searches

The matching profile covers six career routes:

1. Technical Superintendent / Technical Vessel Manager / Port Engineer.
2. Marine Surveyor / Technical Inspector / Plan Approval Engineer.
3. Marine OEM Field Service / Commissioning / Technical Support.
4. Shipbuilding, retrofit, drydock and technical project roles.
5. Offshore wind, maintenance, reliability, O&M and asset management.
6. Chief Engineer, DP/offshore, subsea and ROV roles in parallel.

Current public sources include:

- Bundesagentur für Arbeit Jobsuche
- BSM Germany
- Carnival Maritime Hamburg
- DNV Germany
- RINA Germany Marine
- Lloyd's Register Germany
- Hapag-Lloyd official career board
- Wärtsilä Germany
- Everllence Germany
- Kongsberg Maritime
- Vestas Germany
- Siemens Energy Germany
- Boskalis
- DOF
- Subsea7

The agent searches English and German title variants, adds extra weight for relevant German locations, removes student/apprentice roles, detects closed vacancies, ranks matches, stores fingerprints in SQLite and suppresses duplicates.

No crawler can guarantee every vacancy on the internet. This project monitors the configured public pages and does not bypass login pages, CAPTCHAs, robots restrictions or anti-bot controls.

## First start

```bash
cp .env.example .env
docker compose up -d --build
docker compose logs -f --tail=200 agent
```

## Update an existing installation

```bash
cd ~/job-agent
git pull --ff-only
docker compose up -d --build
docker compose ps
docker compose logs --tail=200 agent
```

## Run one diagnostic scan

This runs one complete scan and exits instead of waiting 30 minutes:

```bash
docker compose run --rm -e RUN_ONCE=1 agent
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
- career route;
- detected German location;
- matched experience terms;
- source and direct vacancy link.

## Stop

```bash
docker compose down
```

## Data

Seen vacancy fingerprints are stored in the Docker volume `agent_data` as SQLite database `/data/agent.db`.

The matching signature changes automatically after profile edits. That causes still-open vacancies to be re-analysed under the new profile without creating normal recurring duplicates.
