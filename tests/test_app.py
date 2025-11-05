from __future__ import annotations

import sys
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

sys.path.insert(0, str(PROJECT_ROOT))

from app.main import app  # noqa: E402


@pytest.fixture(name="calendar_file")
def calendar_file_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    calendar_path = tmp_path / "calendar.ics"
    calendar_path.write_text(
        "BEGIN:VCALENDAR\nVERSION:2.0\nBEGIN:VEVENT\nSUMMARY:Test\nEND:VEVENT\nEND:VCALENDAR\n"
    )
    target = Path(calendar_path)
    monkeypatch.setattr("app.main.CALENDAR_FILE", target)
    return target


def _expected_headers(path: Path) -> tuple[str, str]:
    stat = path.stat()
    etag = f'"{stat.st_mtime_ns:x}-{stat.st_size:x}"'
    last_modified_dt = datetime.fromtimestamp(stat.st_mtime, timezone.utc).replace(
        microsecond=0
    )
    last_modified = format_datetime(last_modified_dt, usegmt=True)
    return etag, last_modified


def test_calendar_served_with_expected_headers(calendar_file: Path) -> None:
    client = TestClient(app)
    etag, last_modified = _expected_headers(calendar_file)

    response = client.get("/calendar.ics")

    assert response.status_code == 200
    assert response.headers["Content-Type"] == "text/calendar; charset=utf-8"
    assert response.headers["Cache-Control"] == "no-cache"
    assert response.headers["ETag"] == etag
    assert response.headers["Last-Modified"] == last_modified
    assert response.content.startswith(b"BEGIN:VCALENDAR")


def test_head_request_returns_headers_without_body(calendar_file: Path) -> None:
    client = TestClient(app)
    etag, last_modified = _expected_headers(calendar_file)

    response = client.head("/calendar.ics")

    assert response.status_code == 200
    assert response.content == b""
    assert response.headers["ETag"] == etag
    assert response.headers["Last-Modified"] == last_modified


def test_calendar_if_none_match_returns_304(calendar_file: Path) -> None:
    client = TestClient(app)
    etag, _ = _expected_headers(calendar_file)

    first = client.get("/calendar.ics")
    assert first.status_code == 200

    response = client.get("/calendar.ics", headers={"If-None-Match": etag})
    assert response.status_code == 304
    assert response.headers["ETag"] == etag


def test_calendar_if_none_match_without_quotes(calendar_file: Path) -> None:
    client = TestClient(app)
    etag, _ = _expected_headers(calendar_file)

    first = client.get("/calendar.ics")
    assert first.status_code == 200

    response = client.get("/calendar.ics", headers={"If-None-Match": etag.strip('"')})
    assert response.status_code == 304


def test_calendar_if_modified_since_returns_304(calendar_file: Path) -> None:
    client = TestClient(app)
    etag, last_modified = _expected_headers(calendar_file)

    first = client.get("/calendar.ics")
    assert first.status_code == 200

    response = client.get(
        "/calendar.ics",
        headers={"If-Modified-Since": last_modified},
    )
    assert response.status_code == 304
    assert response.headers["ETag"] == etag
    assert response.headers["Last-Modified"] == last_modified
