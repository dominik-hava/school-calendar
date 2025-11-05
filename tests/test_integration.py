from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

from icalendar import Calendar

# Ensure src/ is importable when running from repo root.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from ical_proxy.config import (
    AppConfig,
    CalendarConfig,
    HttpConfig,
    RecurringEventConfig,
    RuleConfig,
    ServeConfig,
)
from ical_proxy.ics_engine import build_calendar, parse_calendar

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "upstream_sample.ics"


def _config() -> AppConfig:
    rule = RuleConfig(
        category_primary="BI-TZP.21",
        category_secondary="přednáška",
        new_day="Monday",
        new_time_start="16:15",
        duration_minutes=90,
        rrule_freq="MONTHLY",
    )
    recurring = RecurringEventConfig(
        summary="Beach volejbal",
        start=datetime(2025, 9, 24, 11, 0, tzinfo=timezone.utc),
        duration_minutes=60,
        freq="WEEKLY",
        count=13,
        until=None,
        timezone="Europe/Prague",
        description=None,
        location=None,
        categories=tuple(),
    )
    return AppConfig(
        calendar=CalendarConfig(timezone="Europe/Prague"),
        source_url="https://example.invalid/source.ics",
        http=HttpConfig(timeout_seconds=3, read_timeout_seconds=5, max_retries=1, backoff_seconds=1),
        serve=ServeConfig(
            host="0.0.0.0",
            port=9300,
            tls_cert=Path(__file__),
            tls_key=Path(__file__),
        ),
        rules=(rule,),
        recurring_events=(recurring,),
    )


def test_pipeline_preserves_timezone_and_rules() -> None:
    raw = FIXTURE_PATH.read_bytes()
    parsed = parse_calendar(raw)

    result = build_calendar(parsed, _config(), generated_at=datetime(2024, 8, 1, tzinfo=timezone.utc))
    serialized = result.to_ical()

    # Ensure VTIMEZONE block is present in output.
    assert b"BEGIN:VTIMEZONE" in serialized

    # Ensure recurrence frequency was updated to MONTHLY.
    assert b"RRULE:FREQ=MONTHLY" in serialized
    assert b"RRULE:FREQ=WEEKLY" in serialized  # recurring injection

    rebuilt = Calendar.from_ical(serialized)
    events = [c for c in rebuilt.subcomponents if c.name == "VEVENT"]
    assert len(events) == 3  # two from upstream, one injected

    # Confirm the recurring event has timezone-aware DTSTART.
    recurring_event = next(event for event in events if event["SUMMARY"] == "Beach volejbal")
    assert recurring_event["DTSTART"].dt.tzinfo is not None

