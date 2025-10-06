#!/usr/bin/env python3

import uuid
from datetime import datetime, timedelta

import pytz
import requests
from icalendar import Calendar, Event

from config import ICAL_URL, RULES

# === CONFIGURATION ===
OUTPUT_FILE = "sirius_modified.ics"


def move_to_day_and_time(old_dt, new_weekday_name, new_time_str):
    # map weekday names to numbers
    weekdays = [
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday",
    ]
    new_weekday = weekdays.index(new_weekday_name)
    current_weekday = old_dt.weekday()

    # difference in days
    diff = new_weekday - current_weekday
    new_date = old_dt + timedelta(days=diff)

    # parse new time
    hours, minutes = map(int, new_time_str.split(":"))
    return new_date.replace(hour=hours, minute=minutes, second=0, microsecond=0)


def get_categories(component):
    """Return categories as a list of plain strings."""
    cats_raw = component.get("CATEGORIES", None)

    # Normalize to an iterable of atomic items
    if cats_raw is None:
        items = []
    elif hasattr(cats_raw, "cats"):  # single vCategory with multiple values
        items = list(cats_raw.cats)
    elif isinstance(cats_raw, (list, tuple)):
        items = list(cats_raw)
    else:  # single value (vCategory/str/bytes)
        items = [cats_raw]

    # Convert each item to plain str
    out = []
    for it in items:
        if hasattr(it, "to_ical"):  # vCategory / vText, etc.
            v = it.to_ical()
            out.append(v.decode() if isinstance(
                v, (bytes, bytearray)) else str(v))
        else:
            out.append(it.decode() if isinstance(
                it, (bytes, bytearray)) else str(it))
    return out


def add_repeating_event(
    cal: Calendar, name: str, start_time: str, duration: int, freq: str, weeks: int
):
    tz = pytz.timezone("Europe/Prague")
    start = tz.localize(datetime.strptime(start_time, "%Y-%m-%d %H:%M"))
    end = start + timedelta(minutes=duration)

    event = Event()
    event.add("summary", name)
    event.add("dtstart", start)
    event.add("dtend", end)
    event.add("dtstamp", datetime.now(tz))
    event.add("uid", f"{uuid.uuid4()}@custom")
    event.add("rrule", {"freq": "weekly", "count": weeks})
    cal.add_component(event)


# Define timezone
tz = pytz.timezone("Europe/Prague")

print("Fetching Sirius calendar...")
resp = requests.get(ICAL_URL)
resp.raise_for_status()


old_cal = Calendar.from_ical(resp.text)

# Create new calendar
cal = Calendar()
for prop in ("prodid", "version", "calscale", "method"):
    if prop in old_cal:
        cal.add(prop, old_cal[prop])

for component in old_cal.walk():
    if component.name != "VEVENT":
        continue

    summary = component["SUMMARY"]

    categories = get_categories(component)
    # safe even if 0/1 cat present
    lesson_name, lesson_type = (categories + ["", ""])[:2]
    lesson = f"{lesson_name}:{lesson_type}"

    # print(f"Name: {lesson_name}, Type: {lesson_type}")
    # print(f"Lesson: {lesson}")

    dtstart = component.get("DTSTART").dt
    dtend = component.get("DTEND").dt
    duration = dtend - dtstart

    if lesson in RULES:
        rule = RULES[lesson]
        print(f"Modifying: {lesson}")

        # Calculate new datetime
        new_weekday = rule["new_day"]
        new_time_str = rule["new_time_start"]
        duration_minutes = rule["duration_minutes"]

        print(f"Original: {dtstart} ({dtstart.strftime('%A %H:%M')})")
        new_start = move_to_day_and_time(dtstart, new_weekday, new_time_str)
        print(f"New:      {new_start} ({new_start.strftime('%A %H:%M')})\n")

        new_end = new_start + timedelta(minutes=duration_minutes)

        # apply changes
        component["DTSTART"].dt = new_start
        component["DTEND"].dt = new_end

    cal.add_component(component)

add_repeating_event(cal, "Beach volejbal",
                    "2025-09-24 11:00", 60, "weekly", 13)

# Write to file
with open(OUTPUT_FILE, "wb") as f:
    f.write(cal.to_ical())

print(f"✅ Modified calendar saved to {OUTPUT_FILE}")
