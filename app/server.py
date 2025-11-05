from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import uvicorn

CURRENT_DIR = Path(__file__).resolve().parent
SRC_PATH = CURRENT_DIR.parent / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from ical_proxy import project_root  # noqa: E402
from ical_proxy.config import ConfigError, load_config  # noqa: E402


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    try:
        config = load_config()
    except ConfigError as exc:
        raise SystemExit(f"configuration error: {exc}") from exc

    serve_cfg = config.serve

    host = os.getenv("CALENDAR_HOST", serve_cfg.host)
    port = int(os.getenv("CALENDAR_PORT", str(serve_cfg.port)))
    cert_path = _resolve_path("CALENDAR_TLS_CERT", serve_cfg.tls_cert)
    key_path = _resolve_path("CALENDAR_TLS_KEY", serve_cfg.tls_key)

    missing = [path for path in (cert_path, key_path) if not path.exists()]
    if missing:
        missing_paths = ", ".join(str(p) for p in missing)
        raise SystemExit(
            "TLS material missing: "
            f"{missing_paths}. Provide files or override CALENDAR_TLS_CERT/KEY."
        )

    logging.info("Starting server on https://%s:%s", host, port)
    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        ssl_certfile=str(cert_path),
        ssl_keyfile=str(key_path),
        server_header=False,
        date_header=False,
    )


def _resolve_path(env_name: str, default: Path) -> Path:
    override = os.getenv(env_name)
    if override:
        candidate = Path(override)
        if not candidate.is_absolute():
            candidate = project_root() / candidate
        return candidate
    return default


if __name__ == "__main__":
    main()
