import os
import time
from datetime import datetime, timezone

import requests

from app.db import has_seen, mark_seen
from app.location import analyse_germany_location
from app.main import (
    _message_for_match,
    fetch_source,
    fingerprint,
    load_config,
    matching_signature,
)
from app.matcher import analyse_job
from app.notify import send_telegram, telegram_enabled
from app.summarizer import effective_summary_provider, summarize_job


def _source_priority(source: dict) -> int:
    try:
        return int(source.get("scan_priority", 1000))
    except (TypeError, ValueError):
        return 1000


def _deliver(items: list[dict], delay: float) -> int:
    delivered = 0
    items.sort(
        key=lambda item: (
            item["analysis"]["score"],
            item["title"].casefold(),
        ),
        reverse=True,
    )

    for item in items:
        try:
            summary = summarize_job(
                item["title"],
                item["description"],
                item["location"],
                item["analysis"],
            )
            print(
                "[INFO] Ukrainian summary ready: "
                f"provider={summary.get('provider')} "
                f"cached={summary.get('cached', False)} "
                f"title={item['title']}",
                flush=True,
            )
            send_telegram(_message_for_match(item, summary))
            mark_seen(
                item["fingerprint"],
                item["source"],
                item["title"],
                item["url"],
                item["first_seen_at"],
            )
            delivered += 1
            if telegram_enabled() and delay > 0:
                time.sleep(delay)
        except Exception as exc:
            print(
                f"[ERROR] notification failed for {item['title']}: {exc}",
                flush=True,
            )

    return delivered


def run_once() -> None:
    config = load_config()
    minimum_score = int(config.get("minimum_score", 1))
    match_signature = matching_signature(config)
    delay = float(config.get("notification_delay_seconds", 1.1))
    pending_fingerprints: set[str] = set()

    germany_confirmed = 0
    location_rejected = 0
    enabled_sources = 0
    successful_sources = 0
    failed_sources = 0
    fetched_total = 0
    total_matching = 0
    total_delivered = 0

    print(
        f"[INFO] Ukrainian summary provider: {effective_summary_provider()}",
        flush=True,
    )

    sources = sorted(
        config.get("sources", []),
        key=_source_priority,
    )

    with requests.Session() as session:
        for source in sources:
            if not source.get("enabled", True):
                continue

            enabled_sources += 1
            source_pending: list[dict] = []
            name = source.get("name", source.get("url", "source"))

            try:
                jobs = fetch_source(source, session, config)
            except Exception as exc:
                failed_sources += 1
                print(f"[ERROR] {name}: {exc}", flush=True)
                continue

            successful_sources += 1
            fetched_total += len(jobs)
            print(f"[INFO] {name}: fetched {len(jobs)} items", flush=True)

            for job in jobs:
                title = job.get("title", "").strip()
                url = job.get("url", "").strip()
                location = job.get("location", "").strip()
                description = job.get("description", "")
                if not title or not url:
                    continue

                fp = fingerprint(name, title, url, match_signature)
                if fp in pending_fingerprints or has_seen(fp):
                    continue

                now = datetime.now(timezone.utc).isoformat()
                location_result = analyse_germany_location(
                    title,
                    description,
                    location,
                )
                if not location_result["eligible"]:
                    location_rejected += 1
                    mark_seen(fp, name, title, url, now)
                    continue

                germany_confirmed += 1
                analysis = analyse_job(title, description, config)
                if (
                    analysis["score"] < minimum_score
                    or analysis.get("exclude", False)
                ):
                    mark_seen(fp, name, title, url, now)
                    continue

                pending_fingerprints.add(fp)
                source_pending.append(
                    {
                        "fingerprint": fp,
                        "first_seen_at": now,
                        "source": name,
                        "title": title,
                        "url": url,
                        "location": location_result["display"],
                        "description": description,
                        "analysis": analysis,
                    }
                )

            if source_pending:
                total_matching += len(source_pending)
                print(
                    f"[INFO] {name}: {len(source_pending)} new matching jobs; "
                    "delivering immediately",
                    flush=True,
                )
                total_delivered += _deliver(source_pending, delay)

    print(
        "[INFO] Germany-only location filter: "
        f"confirmed {germany_confirmed}, rejected {location_rejected}",
        flush=True,
    )
    print(
        "[INFO] source scan summary: "
        f"enabled {enabled_sources}, successful {successful_sources}, "
        f"failed {failed_sources}, fetched {fetched_total}",
        flush=True,
    )
    print(f"[INFO] new matching jobs: {total_matching}", flush=True)
    print(f"[INFO] delivered matching jobs: {total_delivered}", flush=True)


def _run_scan_with_logging() -> None:
    print(
        f"[INFO] scan started {datetime.now(timezone.utc).isoformat()}",
        flush=True,
    )
    try:
        run_once()
    except Exception as exc:
        print(f"[FATAL-SCAN] {exc}", flush=True)
        if os.getenv("RUN_ONCE", "").casefold() in {"1", "true", "yes"}:
            raise


def main() -> None:
    if os.getenv("RUN_ONCE", "").casefold() in {"1", "true", "yes"}:
        _run_scan_with_logging()
        return

    while True:
        config = load_config()
        interval = max(1, int(config.get("interval_minutes", 30)))
        _run_scan_with_logging()
        time.sleep(interval * 60)


if __name__ == "__main__":
    main()
