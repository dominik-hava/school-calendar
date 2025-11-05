from __future__ import annotations

import sys
from datetime import datetime, timezone
from email.utils import format_datetime, parsedate_to_datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse

CURRENT_DIR = Path(__file__).resolve().parent
SRC_PATH = CURRENT_DIR.parent / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from ical_proxy import default_calendar_path  # noqa: E402


CALENDAR_FILE = default_calendar_path()

app = FastAPI(
    title="Sirius Calendar",
    version="0.1.0",
    docs_url=None,
    redoc_url=None,
)


@app.api_route("/calendar.ics", methods=["GET", "HEAD"])
async def serve_calendar(request: Request) -> Response:
    if not CALENDAR_FILE.exists():
        raise HTTPException(status_code=404, detail="Calendar not generated yet")

    stat = CALENDAR_FILE.stat()
    etag = _generate_etag(stat.st_mtime_ns, stat.st_size)
    last_modified_dt = datetime.fromtimestamp(stat.st_mtime, timezone.utc).replace(
        microsecond=0
    )
    last_modified = format_datetime(last_modified_dt, usegmt=True)

    if _is_not_modified(request, etag, last_modified_dt):
        return Response(
            status_code=304,
            headers={
                "ETag": etag,
                "Last-Modified": last_modified,
                "Cache-Control": "no-cache",
            },
        )

    headers = {
        "Cache-Control": "no-cache",
        "ETag": etag,
        "Last-Modified": last_modified,
    }
    return FileResponse(
        path=CALENDAR_FILE,
        media_type="text/calendar; charset=utf-8",
        filename="calendar.ics",
        headers=headers,
    )


def _generate_etag(mtime_ns: int, size: int) -> str:
    return f'"{mtime_ns:x}-{size:x}"'


def _is_not_modified(request: Request, etag: str, last_modified: datetime) -> bool:
    if_none_match = request.headers.get("if-none-match")
    if if_none_match:
        candidates = {tag.strip() for tag in if_none_match.split(",")}
        normalized = {tag.strip('"') for tag in candidates}
        if etag in candidates or etag.strip('"') in normalized:
            return True

    if_modified_since = request.headers.get("if-modified-since")
    if if_modified_since:
        try:
            parsed = parsedate_to_datetime(if_modified_since)
            if parsed is not None:
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                if last_modified <= parsed:
                    return True
        except (TypeError, ValueError):
            pass

    return False
