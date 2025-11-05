"""Core package for Sirius calendar proxy utilities."""

from pathlib import Path


def project_root() -> Path:
    """Return the repository root directory."""
    return Path(__file__).resolve().parents[2]


def default_calendar_path() -> Path:
    """Return the path to the generated calendar file."""
    return project_root() / "calendar.ics"


def default_config_path() -> Path:
    """Return the path to the TOML configuration file."""
    return project_root() / "config.toml"


__all__ = [
    "project_root",
    "default_calendar_path",
    "default_config_path",
]
