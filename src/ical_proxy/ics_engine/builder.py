from __future__ import annotations

import uuid
from copy import deepcopy
from datetime import datetime, timedelta
from typing import Iterable

from icalendar import Calendar, Event, vRecur
from icalendar.cal import Component

from ..config import AppConfig, RecurringEventConfig


def build_calendar(
    source: Calendar, config: AppConfig, *, generated_at: datetime | None = None
) -> Calendar:
    """Return a rewritten calendar with rule and injection application."""
    rewritten = Calendar()

    for name, value in source.items():
        rewritten.add(name, value)

    for component in source.subcomponents:
        if component.name != "VEVENT":
            rewritten.add_component(deepcopy(component))

    for component in source.subcomponents:
        if component.name != "VEVENT":
            continue
        rewritten.add_component(
            _rewrite_event(deepcopy(component), config, generated_at=generated_at)
        )

    _inject_recurring_events(rewritten, config, generated_at=generated_at)
    return rewritten


def _rewrite_event(
    component: Component, config: AppConfig, *, generated_at: datetime | None
) -> Component:
    lesson_key = _derive_lesson_key(component)
    if not lesson_key:
        return component

    rule = config.rule_by_key(lesson_key)
    if not rule:
        return component

    dtstart_prop = component.get("DTSTART")
    if dtstart_prop is None:
        return component

    dtstart = dtstart_prop.dt
    if not isinstance(dtstart, datetime):
        # All-day events are left untouched
        return component

    new_start = _move_to_day_and_time(dtstart, rule.new_day, rule.new_time_start)
    new_end = new_start + timedelta(minutes=rule.duration_minutes)

    if "DTEND" in component:
        component["DTEND"].dt = new_end
    elif "DURATION" in component:
        component["DURATION"].dt = timedelta(minutes=rule.duration_minutes)
    else:
        component.add("DTEND", new_end)

    component["DTSTART"].dt = new_start

    if rule.summary_override:
        component["SUMMARY"] = rule.summary_override
    if rule.location:
        component["LOCATION"] = rule.location
    if rule.description:
        component["DESCRIPTION"] = rule.description

    if rule.rrule_freq:
        freq = rule.rrule_freq.upper()
        existing = component.get("RRULE")
        if existing:
            normalized = {key.upper(): value for key, value in existing.items()}
            normalized["FREQ"] = freq
            component["RRULE"] = vRecur(normalized)
        else:
            component["RRULE"] = vRecur({"FREQ": freq})

    return component


def _inject_recurring_events(
    calendar: Calendar, config: AppConfig, *, generated_at: datetime | None
) -> None:
    if not config.recurring_events:
        return

    for recurring in config.recurring_events:
        tzinfo = recurring.start.tzinfo
        if tzinfo is None:
            raise ValueError("Recurring event start datetime must be timezone-aware")
        if generated_at is not None:
            now = generated_at.astimezone(tzinfo)
        else:
            now = datetime.now(tz=tzinfo)
        _add_recurring_event(calendar, recurring, now)


def _add_recurring_event(
    calendar: Calendar, recurring: RecurringEventConfig, reference_now: datetime
) -> None:
    start = recurring.start
    if start.tzinfo is None:
        raise ValueError("Recurring event start datetime must be timezone-aware")

    event = Event()
    event.add("summary", recurring.summary)
    event.add("dtstart", start)

    duration = timedelta(minutes=recurring.duration_minutes)
    event.add("dtend", start + duration)
    event.add("dtstamp", reference_now.astimezone(start.tzinfo))
    event.add("uid", f"{uuid.uuid4()}@generated.sirius-calendar")

    freq = recurring.freq.upper()
    rrule: dict[str, object] = {"freq": freq}
    if recurring.count is not None:
        rrule["count"] = recurring.count
    if recurring.until is not None:
        rrule["until"] = recurring.until
    event.add("rrule", rrule)

    if recurring.description:
        event.add("description", recurring.description)
    if recurring.location:
        event.add("location", recurring.location)
    if recurring.categories:
        event.add("categories", list(recurring.categories))

    calendar.add_component(event)


def _derive_lesson_key(component: Component) -> str | None:
    categories = _extract_categories(component)
    if not categories:
        return None
    primary, secondary = (categories + ["", ""])[:2]
    if not primary or not secondary:
        return None
    return f"{primary}:{secondary}"


def _extract_categories(component: Component) -> list[str]:
    raw = component.get("CATEGORIES")
    if raw is None:
        return []

    items: Iterable[object]
    if hasattr(raw, "cats"):
        items = raw.cats  # type: ignore[attr-defined]
    elif isinstance(raw, (list, tuple)):
        items = raw
    else:
        items = (raw,)

    resolved: list[str] = []
    for item in items:
        if hasattr(item, "to_ical"):
            encoded = item.to_ical()
            if isinstance(encoded, (bytes, bytearray)):
                resolved.append(encoded.decode())
            else:
                resolved.append(str(encoded))
        elif isinstance(item, (bytes, bytearray)):
            resolved.append(item.decode())
        else:
            resolved.append(str(item))
    return resolved


def _move_to_day_and_time(original: datetime, weekday_name: str, time_str: str) -> datetime:
    target_weekday = _weekday_index(weekday_name)
    hours, minutes = _parse_time(time_str)
    delta_days = target_weekday - original.weekday()
    candidate = original + timedelta(days=delta_days)
    return candidate.replace(hour=hours, minute=minutes, second=0, microsecond=0)


def _weekday_index(name: str) -> int:
    weekdays = [
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday",
    ]
    try:
        return weekdays.index(name)
    except ValueError as exc:
        raise ValueError(f"Unknown weekday {name!r}") from exc


def _parse_time(value: str) -> tuple[int, int]:
    try:
        parsed = datetime.strptime(value, "%H:%M")
    except ValueError as exc:
        raise ValueError(f"Invalid time value {value!r}; expected HH:MM") from exc
    return parsed.hour, parsed.minute
