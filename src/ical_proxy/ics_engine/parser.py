from __future__ import annotations

from icalendar import Calendar


class ParseError(RuntimeError):
    """Raised when calendar parsing fails."""


def parse_calendar(raw: bytes) -> Calendar:
    """Parse the upstream ICS bytes into an icalendar.Calendar."""
    if not raw or not raw.strip():
        raise ParseError("Empty or whitespace-only calendar data")
    
    try:
        calendar = Calendar.from_ical(raw)
    except Exception as exc:
        raise ParseError(f"Failed to parse calendar: {exc}") from exc
    
    if calendar.name != "VCALENDAR":
        raise ParseError(f"Expected VCALENDAR, got {calendar.name}")
    
    return calendar
