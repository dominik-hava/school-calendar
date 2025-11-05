#!/usr/bin/env python3

from __future__ import annotations

import argparse
import logging
import logging.handlers
import random
import sys
import time
from typing import Sequence
from pathlib import Path

import requests

CURRENT_DIR = Path(__file__).resolve().parent
SRC_PATH = CURRENT_DIR / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from ical_proxy import default_calendar_path  # noqa: E402
from ical_proxy.config import AppConfig, ConfigError, load_config  # noqa: E402
from ical_proxy.ics_engine import build_calendar, parse_calendar  # noqa: E402

logger = logging.getLogger("sirius.modify_calendar")


def _setup_logging(log_dir: Path | None = None) -> None:
    """Configure logging with rotation to prevent unbounded log growth."""
    log_format = "%(asctime)s %(levelname)s %(message)s"
    
    if log_dir and log_dir.exists():
        handler = logging.handlers.RotatingFileHandler(
            log_dir / "modify_calendar.log",
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
        )
        handler.setFormatter(logging.Formatter(log_format))
        logging.root.addHandler(handler)
        logging.root.setLevel(logging.INFO)
    else:
        logging.basicConfig(
            level=logging.INFO,
            format=log_format,
        )


class FetchError(RuntimeError):
    """Raised when the upstream calendar cannot be retrieved."""


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download and rewrite the Sirius calendar feed."
    )
    parser.add_argument(
        "--config",
        type=Path,
        help="Path to configuration TOML (defaults to env or project config)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help=f"Destination .ics path (defaults to {default_calendar_path()})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate the calendar but do not write the output file.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    
    log_dir = CURRENT_DIR / "logs" if not args.dry_run else None
    _setup_logging(log_dir)

    try:
        config = load_config(args.config)
    except ConfigError as exc:
        logger.error("configuration error: %s", exc)
        return 2

    destination = args.output or default_calendar_path()
    destination = destination.expanduser().resolve()

    if not args.dry_run:
        destination.parent.mkdir(parents=True, exist_ok=True)

    try:
        upstream_bytes = _fetch_with_retry(config)
    except FetchError as exc:
        logger.error("failed to download calendar: %s", exc)
        return 1

    try:
        source_calendar = parse_calendar(upstream_bytes)
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("failed to parse upstream calendar: %s", exc)
        return 3

    modified_calendar = build_calendar(
        source_calendar,
        config,
    )

    payload = modified_calendar.to_ical()
    if args.dry_run:
        logger.info("dry-run requested; skipping write to %s", destination)
    else:
        try:
            _write_atomic(destination, payload)
        except OSError as exc:  # pragma: no cover - unlikely filesystem issue
            logger.error("failed to write calendar file: %s", exc)
            return 4

        logger.info("calendar written to %s", destination)
    return 0


def _fetch_with_retry(config: AppConfig) -> bytes:
    http = config.http
    attempt = 0
    last_error: Exception | None = None
    timeout = (http.timeout_seconds, http.read_timeout_seconds)

    while attempt <= http.max_retries:
        try:
            logger.info("fetching upstream calendar (attempt %s)", attempt + 1)
            response = requests.get(
                config.source_url,
                timeout=timeout,
            )
            response.raise_for_status()
            return response.content
        except (requests.RequestException, OSError) as exc:
            last_error = exc
            attempt += 1
            if attempt > http.max_retries:
                break
            sleep_for = http.backoff_seconds * attempt + random.uniform(0, 0.5)
            logger.warning(
                "upstream fetch failed (%s); retrying in %.2fs", exc, sleep_for
            )
            time.sleep(sleep_for)

    raise FetchError(str(last_error))


def _write_atomic(destination: Path, payload: bytes) -> None:
    tmp_path = destination.with_name(destination.name + ".tmp")
    with tmp_path.open("wb") as handle:
        handle.write(payload)
    tmp_path.replace(destination)


if __name__ == "__main__":
    raise SystemExit(main())
