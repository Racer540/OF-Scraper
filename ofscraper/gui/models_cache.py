"""
Model-list cache: persists the GUI's subscription list between sessions.

The Models screen fetches the list over the API (needs working auth);
without a cache every GUI restart shows an empty table until a manual
refresh.  This module stores the raw model dicts (Model is a thin wrapper
around the API JSON, classes/of/models.py) plus the fetch timestamp, so
the list can be restored instantly and refreshed in the background only
when it is stale AND the auth check says the session is usable.
"""

import json
import logging
import pathlib
import time

log = logging.getLogger("shared")

CACHE_NAME = "gui_models_cache.json"


def cache_path() -> pathlib.Path:
    import ofscraper.utils.paths.common as common_paths

    return pathlib.Path(common_paths.get_profile_path()) / CACHE_NAME


def save_models(models) -> None:
    """Persist model objects + timestamp (atomic replace, never raises)."""
    try:
        payload = {
            "fetched_at": time.time(),
            "models": [m.model for m in models],
        }
        path = cache_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload))
        tmp.replace(path)
    except Exception as E:
        log.debug(f"could not save models cache: {E}")


def load_models():
    """(models, fetched_at) — ([], None) when no usable cache exists."""
    try:
        data = json.loads(cache_path().read_text())
        fetched_at = float(data.get("fetched_at") or 0)
        raw = data.get("models") or []
        from ofscraper.classes.of.models import Model

        models = [
            Model(m)
            for m in raw
            if isinstance(m, dict) and m.get("username") and m.get("id")
        ]
        if not models or not fetched_at:
            return [], None
        return models, fetched_at
    except Exception:
        return [], None


def refresh_interval_hours() -> float:
    """Configured auto-refresh interval; 0 or negative = manual only."""
    import ofscraper.utils.config.data as data

    try:
        return float(data.get_models_refresh_interval() or 0)
    except Exception:
        return 24.0


def auto_refresh_due(fetched_at) -> bool:
    """True when the cached list is older than the configured interval
    (or no cache exists at all)."""
    hours = refresh_interval_hours()
    if hours <= 0:
        return False
    if not fetched_at:
        return True
    return (time.time() - fetched_at) >= hours * 3600


def cache_age_text(fetched_at) -> str:
    """Short human age for the status line ('3.2h old')."""
    if not fetched_at:
        return ""
    age_h = (time.time() - fetched_at) / 3600
    if age_h < 1:
        return f"{max(age_h * 60, 0):.0f}m old"
    if age_h < 48:
        return f"{age_h:.1f}h old"
    return f"{age_h / 24:.1f}d old"
