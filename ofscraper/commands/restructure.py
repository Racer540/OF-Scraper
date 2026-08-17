"""
Standalone `restructure` command: move every model's downloaded files to
match the current folder layout.

Discovers model databases offline (no login required) by walking the
profile's live-database root for user_data.db files and reading each DB's
own models/profiles tables for the model_id and username, then runs the
same per-model pass the downloader runs before downloading
(commands/scraper/actions/download/restructure.py).
"""

import logging
import pathlib
import sqlite3

import ofscraper.utils.live.updater as progress_updater
import ofscraper.utils.paths.db as db_paths
from ofscraper.utils.context.run_async import run

log = logging.getLogger("shared")


def _model_from_db(db_path: pathlib.Path):
    """(model_id, username, db_path) read straight from a user_data.db."""
    try:
        con = sqlite3.connect(db_path)
        try:
            con.row_factory = sqlite3.Row
            model_row = con.execute("select model_id from models limit 1").fetchone()
            if not model_row:
                return None
            model_id = model_row[0]
            username_row = con.execute(
                "select username from profiles where user_id=(?)", [model_id]
            ).fetchone() or con.execute(
                "select username from profiles limit 1"
            ).fetchone()
            if not username_row:
                return None
            return model_id, username_row[0], db_path
        finally:
            con.close()
    except Exception:
        return None


def _discover_models() -> list:
    root = pathlib.Path(db_paths.get_default_current())
    if not root.exists():
        return []
    out = []
    for db_path in db_paths.get_all_db(root):
        found = _model_from_db(db_path)
        if found:
            out.append(found)
    return out


@run
async def restructure_all():
    from ofscraper.commands.scraper.actions.download.restructure import (
        restructure_model_downloads,
    )
    from ofscraper.commands.scraper.actions.download.restructure import (
        cleanup_orphan_parts,
    )

    models = _discover_models()
    if not models:
        log.warning(
            "No model databases found — nothing to restructure "
            f"(looked under {db_paths.get_default_current()})"
        )
        return

    log.info(
        f"Restructuring downloads for {len(models)} model(s) to match the "
        "current folder layout"
    )
    totals = {}
    parts_removed = 0
    parts_freed = 0
    for i, (model_id, username, db_path) in enumerate(models, start=1):
        progress_updater.activity.update_task(
            description=f"Restructuring {username} ({i}/{len(models)})",
            visible=True,
        )
        # db_path from discovery keeps this fully offline
        stats = await restructure_model_downloads(
            username, model_id, db_path=db_path
        )
        for key, value in stats.items():
            totals[key] = totals.get(key, 0) + value
        part_stats = await cleanup_orphan_parts(
            username, model_id, db_path=db_path
        )
        parts_removed += part_stats["removed"]
        parts_freed += part_stats["freed_bytes"]

    moved = totals.get("moved", 0) + totals.get("replaced", 0) + totals.get(
        "dupe_removed", 0
    )
    log.info(
        f"Restructure complete: {moved} file(s) rearranged across "
        f"{len(models)} model(s) — {totals.get('unchanged', 0)} already "
        f"correct, {totals.get('missing', 0)} not found, "
        f"{totals.get('error', 0)} errors; {parts_removed} orphan .part "
        f"file(s) removed ({parts_freed / 1e9:.2f} GB freed)"
    )
