# Personal Marine Job Agent

Self-hosted vacancy monitor for marine/offshore roles.

Current sources:
- Boskalis Careers
- DOF Careers
- Subsea7 Careers

The agent crawls only public career pages, scores vacancies against configured keywords, stores fingerprints in SQLite, and suppresses duplicates. It can send matches to Telegram; if Telegram is not configured, matches are printed to Docker logs.

## Start

```bash
cp .env.example .env
docker compose up -d --build
docker compose logs -f agent
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

## Stop

```bash
docker compose down
```

## Data

Seen vacancy fingerprints are stored in the Docker volume `agent_data` as SQLite database `/data/agent.db`.
