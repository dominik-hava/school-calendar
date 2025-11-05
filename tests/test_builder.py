from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from icalendar import Calendar, Event

# Ensure the application package is importable when tests run from repo root.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from ical_proxy.config import (  # noqa: E402
    AppConfig,
    CalendarConfig,
    HttpConfig,
    RuleConfig,
    ServeConfig,
)
from ical_proxy.ics_engine.builder import build_calendar  # noqa: E402


def _base_config(rule: RuleConfig) -> AppConfig:
    return AppConfig(
        calendar=CalendarConfig(timezone="Europe/Prague"),
        source_url="https://example.invalid/source.ics",
        http=HttpConfig(
            timeout_seconds=3.05,
            read_timeout_seconds=5.0,
            max_retries=1,
            backoff_seconds=1.0,
        ),
        serve=ServeConfig(
            host="0.0.0.0",
            port=9300,
            tls_cert=Path(__file__),
            tls_key=Path(__file__),
        ),
        rules=(rule,),
        recurring_events=tuple(),
    )


def _sample_event() -> Event:
    event = Event()
    event.add("uid", "sample-uid")
    event.add("dtstart", datetime(2024, 9, 6, 12, 0, tzinfo=timezone.utc))
    event.add("categories", ["BI-TZP.21", "přednáška"])
    event.add("summary", "Original summary")
    return event


def test_rrule_frequency_is_respected() -> None:
    event = _sample_event()
    event.add("rrule", {"freq": "daily"})

    rule = RuleConfig(
        category_primary="BI-TZP.21",
        category_secondary="přednáška",
        new_day="Monday",
        new_time_start="16:15",
        duration_minutes=90,
        rrule_freq="MONTHLY",
    )

    calendar = Calendar()
    calendar.add_component(event)

    rewritten = build_calendar(calendar, _base_config(rule))
    ical_bytes = rewritten.to_ical()

    assert b"RRULE:FREQ=MONTHLY" in ical_bytes
    assert b"RRULE:FREQ=DAILY" not in ical_bytes


def test_duration_is_preserved_when_dtend_missing() -> None:
    event = _sample_event()
    original_duration = timedelta(minutes=45)
    event.add("duration", original_duration)

    rule = RuleConfig(
        category_primary="BI-TZP.21",
        category_secondary="přednáška",
        new_day="Wednesday",
        new_time_start="08:15",
        duration_minutes=60,
    )

    calendar = Calendar()
    calendar.add_component(event)

    rewritten = build_calendar(calendar, _base_config(rule))
    vevent = next(comp for comp in rewritten.subcomponents if comp.name == "VEVENT")

    # DTSTART updated to requested slot.
    assert vevent["DTSTART"].dt.weekday() == 2  # Wednesday
    assert vevent["DTSTART"].dt.hour == 8
    assert vevent["DTSTART"].dt.minute == 15

    # No DTEND was present; DURATION should reflect rule duration.
    assert "DTEND" not in vevent
    assert vevent["DURATION"].dt == timedelta(minutes=60)
