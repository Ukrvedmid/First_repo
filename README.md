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
- career route;
- confirmed German location;
- matched experience terms;
- source and direct vacancy link.

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

The `.env` file, Telegram token and SQLite Docker volume are not committed or removed during deployments.

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

Seen vacancy fingerprints are stored in the Docker volume `agent_data` as SQLite database `/data/agent.db`.

The matching signature changes automatically after profile edits. That causes still-open vacancies to be re-analysed under the new profile without creating normal recurring duplicates.
