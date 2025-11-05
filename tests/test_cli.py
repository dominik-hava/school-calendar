from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import modify_calendar  # noqa: E402

SAMPLE_ICS = (Path(__file__).parent / "fixtures" / "upstream_sample.ics").read_bytes()


def _write_config(tmp_dir: Path) -> Path:
    config_path = tmp_dir / "config.toml"
    config_path.write_text(
        """
[calendar]
timezone = "Europe/Prague"

[http]
timeout_seconds = 1.0
read_timeout_seconds = 1.0
max_retries = 0
backoff_seconds = 0.1

[serve]
host = "127.0.0.1"
port = 9999
tls_cert = "tls/cert.pem"
tls_key = "tls/key.pem"

[[rules]]
category_primary = "BI-TZP.21"
category_secondary = "přednáška"
new_day = "Monday"
new_time_start = "16:15"
duration_minutes = 90
rrule_freq = "MONTHLY"

[[rules]]
category_primary = "BI-LA1.21"
category_secondary = "cvičení"
new_day = "Wednesday"
new_time_start = "15:15"
duration_minutes = 60

[[recurring_events]]
summary = "Beach volejbal"
start = "2025-09-24T11:00:00+00:00"
duration_minutes = 60
freq = "WEEKLY"
count = 4
timezone = "Europe/Prague"
"""
    )
    return config_path


def test_cli_writes_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_path = _write_config(tmp_path)
    monkeypatch.setenv("CALENDAR_ICAL_URL", "https://example.invalid/calendar.ics")

    def fake_fetch(_config: object) -> bytes:
        return SAMPLE_ICS

    monkeypatch.setattr(modify_calendar, "_fetch_with_retry", fake_fetch)

    output = tmp_path / "calendar-out.ics"
    exit_code = modify_calendar.main(
        ["--config", str(config_path), "--output", str(output)]
    )

    assert exit_code == 0
    assert output.exists()
    content = output.read_bytes()
    assert b"BEGIN:VCALENDAR" in content


def test_cli_dry_run_skips_write(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_path = _write_config(tmp_path)
    monkeypatch.setenv("CALENDAR_ICAL_URL", "https://example.invalid/calendar.ics")

    def fake_fetch(_config: object) -> bytes:
        return SAMPLE_ICS

    monkeypatch.setattr(modify_calendar, "_fetch_with_retry", fake_fetch)

    output = tmp_path / "calendar-dry.ics"
    exit_code = modify_calendar.main(
        ["--config", str(config_path), "--output", str(output), "--dry-run"]
    )

    assert exit_code == 0
    assert not output.exists()


def test_cli_fetch_failure_keeps_existing_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path = _write_config(tmp_path)
    monkeypatch.setenv("CALENDAR_ICAL_URL", "https://example.invalid/calendar.ics")

    def failing_fetch(_config: object) -> bytes:
        raise modify_calendar.FetchError("boom")

    monkeypatch.setattr(modify_calendar, "_fetch_with_retry", failing_fetch)

    output = tmp_path / "existing.ics"
    original = b"prior-data"
    output.write_bytes(original)

    exit_code = modify_calendar.main(
        ["--config", str(config_path), "--output", str(output)]
    )

    assert exit_code == 1
    assert output.read_bytes() == original


def test_cli_errors_when_source_env_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_path = _write_config(tmp_path)
    monkeypatch.delenv("CALENDAR_ICAL_URL", raising=False)

    exit_code = modify_calendar.main(["--config", str(config_path), "--dry-run"])

    assert exit_code == 2
