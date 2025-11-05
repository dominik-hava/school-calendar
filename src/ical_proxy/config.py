from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from . import default_config_path, project_root


CONFIG_ENV_VAR = "SIRIUS_CALENDAR_CONFIG"
SOURCE_URL_ENV_VAR = "CALENDAR_ICAL_URL"


class ConfigError(RuntimeError):
    """Raised when configuration is invalid or missing required values."""


@dataclass(frozen=True)
class HttpConfig:
    timeout_seconds: float
    read_timeout_seconds: float
    max_retries: int
    backoff_seconds: float

    @property
    def timeout_tuple(self) -> tuple[float, float]:
        """Return a (connect, read) timeout tuple for requests."""
        return (self.timeout_seconds, self.read_timeout_seconds)


@dataclass(frozen=True)
class ServeConfig:
    host: str
    port: int
    tls_cert: Path
    tls_key: Path


@dataclass(frozen=True)
class RuleConfig:
    category_primary: str
    category_secondary: str
    new_day: str
    new_time_start: str
    duration_minutes: int
    summary_override: str | None = None
    location: str | None = None
    description: str | None = None
    rrule_freq: str | None = None

    @property
    def key(self) -> str:
        return f"{self.category_primary}:{self.category_secondary}"


@dataclass(frozen=True)
class RecurringEventConfig:
    summary: str
    start: datetime
    duration_minutes: int
    freq: str
    count: int | None
    until: datetime | None
    timezone: str | None
    description: str | None = None
    location: str | None = None
    categories: tuple[str, ...] = ()


@dataclass(frozen=True)
class CalendarConfig:
    timezone: str


@dataclass(frozen=True)
class AppConfig:
    calendar: CalendarConfig
    http: HttpConfig
    serve: ServeConfig
    rules: tuple[RuleConfig, ...]
    recurring_events: tuple[RecurringEventConfig, ...]
    source_url: str

    def rule_by_key(self, key: str) -> RuleConfig | None:
        for rule in self.rules:
            if rule.key == key:
                return rule
        return None


def load_config(path: Path | None = None) -> AppConfig:
    config_path = path or _config_path_from_env() or default_config_path()
    if not config_path.exists():
        raise ConfigError(f"Configuration file not found at {config_path}")

    source_url = os.getenv(SOURCE_URL_ENV_VAR)
    if not source_url:
        raise ConfigError(
            f"{SOURCE_URL_ENV_VAR} environment variable must be set to the upstream ICS URL"
        )

    with config_path.open("rb") as f:
        raw = tomllib.load(f)

    calendar_section = raw.get("calendar")
    if not isinstance(calendar_section, Mapping):
        raise ConfigError("[calendar] section missing from configuration")
    timezone = _require_str(calendar_section, "timezone")

    http_section = raw.get("http")
    if not isinstance(http_section, Mapping):
        raise ConfigError("[http] section missing from configuration")
    http = HttpConfig(
        timeout_seconds=_require_float(http_section, "timeout_seconds"),
        read_timeout_seconds=_get_float(
            http_section, "read_timeout_seconds", fallback=None
        )
        or _require_float(http_section, "timeout_seconds"),
        max_retries=_require_int(http_section, "max_retries"),
        backoff_seconds=_require_float(http_section, "backoff_seconds"),
    )

    serve_section = raw.get("serve")
    if not isinstance(serve_section, Mapping):
        raise ConfigError("[serve] section missing from configuration")
    serve = ServeConfig(
        host=_require_str(serve_section, "host"),
        port=_require_int(serve_section, "port"),
        tls_cert=_resolve_path(_require_str(serve_section, "tls_cert")),
        tls_key=_resolve_path(_require_str(serve_section, "tls_key")),
    )

    rules_raw = raw.get("rules")
    if not isinstance(rules_raw, Sequence) or not rules_raw:
        raise ConfigError("At least one [[rules]] entry is required")
    rules = tuple(_load_rule(entry, index) for index, entry in enumerate(rules_raw))

    recurring_raw = raw.get("recurring_events", [])
    if not isinstance(recurring_raw, Sequence):
        raise ConfigError("[[recurring_events]] must be an array if provided")
    recurring_events = tuple(
        _load_recurring_event(entry, index, timezone)
        for index, entry in enumerate(recurring_raw)
    )

    return AppConfig(
        calendar=CalendarConfig(timezone=timezone),
        http=http,
        serve=serve,
        rules=rules,
        recurring_events=recurring_events,
        source_url=source_url,
    )


def _load_rule(entry: Mapping[str, Any], index: int) -> RuleConfig:
    try:
        category_primary = _require_str(entry, "category_primary")
        category_secondary = _require_str(entry, "category_secondary")
        new_day = _require_str(entry, "new_day")
        new_time_start = _require_str(entry, "new_time_start")
        duration_minutes = _require_int(entry, "duration_minutes")
    except ConfigError as exc:
        raise ConfigError(f"Invalid rule at index {index}: {exc}") from exc

    summary_override = _get_str(entry, "summary_override", None)
    location = _get_str(entry, "location", None)
    description = _get_str(entry, "description", None)
    rrule_freq = _get_str(entry, "rrule_freq", None)

    if duration_minutes <= 0:
        raise ConfigError("duration_minutes must be a positive integer")

    return RuleConfig(
        category_primary=category_primary,
        category_secondary=category_secondary,
        new_day=new_day,
        new_time_start=new_time_start,
        duration_minutes=duration_minutes,
        summary_override=summary_override,
        location=location,
        description=description,
        rrule_freq=rrule_freq,
    )


def _load_recurring_event(
    entry: Mapping[str, Any], index: int, default_timezone: str
) -> RecurringEventConfig:
    try:
        summary = _require_str(entry, "summary")
        start_raw = _require_str(entry, "start")
        duration_minutes = _require_int(entry, "duration_minutes")
        freq = _require_str(entry, "freq")
    except ConfigError as exc:
        raise ConfigError(
            f"Invalid recurring event at index {index}: {exc}"
        ) from exc

    timezone_name = entry.get("timezone") or default_timezone
    start = _parse_datetime(start_raw, timezone_name)
    count = _get_int(entry, "count", None)
    until_raw = _get_str(entry, "until", None)
    until = _parse_datetime(until_raw, timezone_name) if until_raw else None
    timezone = _get_str(entry, "timezone", None)
    description = _get_str(entry, "description", None)
    location = _get_str(entry, "location", None)
    categories = tuple(_ensure_str_list(entry.get("categories", [])))

    return RecurringEventConfig(
        summary=summary,
        start=start,
        duration_minutes=duration_minutes,
        freq=freq,
        count=count,
        until=until,
        timezone=timezone,
        description=description,
        location=location,
        categories=categories,
    )


def _parse_datetime(value: str, timezone: str) -> datetime:
    """Parse ISO-like strings, assuming local timezone if absent."""
    normalized = value.replace(" ", "T")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ConfigError(f"Invalid datetime value: {value!r}") from exc

    if parsed.tzinfo is not None:
        return parsed

    try:
        from zoneinfo import ZoneInfo
    except ImportError as exc:  # pragma: no cover - Python <3.9 not supported
        raise ConfigError("zoneinfo module unavailable") from exc

    return parsed.replace(tzinfo=ZoneInfo(timezone))


def _resolve_path(value: str) -> Path:
    candidate = Path(value)
    if candidate.is_absolute():
        return candidate
    return project_root() / candidate


def _config_path_from_env() -> Path | None:
    override = os.getenv(CONFIG_ENV_VAR)
    if not override:
        return None
    candidate = Path(override)
    if candidate.is_absolute():
        return candidate
    return project_root() / candidate


def _require_str(mapping: Mapping[str, Any], key: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{key} must be a non-empty string")
    return value.strip()


def _get_str(mapping: Mapping[str, Any], key: str, fallback: str | None) -> str | None:
    value = mapping.get(key, fallback)
    if value is None:
        return fallback
    if not isinstance(value, str):
        raise ConfigError(f"{key} must be a string if provided")
    return value.strip()


def _require_int(mapping: Mapping[str, Any], key: str) -> int:
    value = mapping.get(key)
    if not isinstance(value, int):
        raise ConfigError(f"{key} must be an integer")
    return value


def _get_int(mapping: Mapping[str, Any], key: str, fallback: int | None) -> int | None:
    value = mapping.get(key, fallback)
    if value is None:
        return fallback
    if not isinstance(value, int):
        raise ConfigError(f"{key} must be an integer if provided")
    return value


def _require_float(mapping: Mapping[str, Any], key: str) -> float:
    value = mapping.get(key)
    if not isinstance(value, (int, float)):
        raise ConfigError(f"{key} must be a number")
    return float(value)


def _get_float(
    mapping: Mapping[str, Any], key: str, fallback: float | None
) -> float | None:
    value = mapping.get(key, fallback)
    if value is None:
        return None
    if not isinstance(value, (int, float)):
        raise ConfigError(f"{key} must be a number if provided")
    return float(value)


def _ensure_str_list(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        return (value,)
    if not isinstance(value, Iterable):
        raise ConfigError("categories must be iterable")
    out: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise ConfigError("categories must contain strings")
        out.append(item)
    return out
