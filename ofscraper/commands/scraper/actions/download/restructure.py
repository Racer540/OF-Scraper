"""
Restructure pass: move already-downloaded files into the current folder
layout instead of re-downloading them.

OF-Scraper decides "already downloaded" by the database's downloaded flag
(filters/media/filters.py:previous_download_filter), never by file
location — so when `dir_format` (or `save_location`) changes, existing
files simply stay in the old tree forever.  This pass reads each model's
recorded media locations from user_data.db, recomputes the target
directory for the CURRENT `dir_format`, moves what it can, and rewrites
the recorded locations so the DB keeps matching disk.

What it deliberately does NOT do: rename files.  `file_format` involves
download-time state (quality selection, counts, naming scripts) that
cannot be faithfully recomputed from a DB row, so filenames are preserved
verbatim and only the containing folders change.

Placeholder support: `dir_format` is only recomputed when every
placeholder it uses is derivable from a DB row (username, model_id,
post_id, media_id, media_type, response_type, download_type, date and the
static site/profile ones).  Formats using {label}, {value}, {quality} or
filename placeholders are skipped with a warning — no files are touched.
"""

import logging
import os
import pathlib
import re
import shutil

import arrow

import ofscraper.utils.config.data as data
import ofscraper.utils.paths.common as common_paths
from ofscraper.utils.string import parse_safe

log = logging.getLogger("shared")

# temp names end with _{media_id}_{post_id}.part (DRM tracks use
# tempaudio_/tempvideo_ prefixes; normal temps use the final filename —
# both carry the id pair as the suffix)
_PART_NAME_RE = re.compile(r"_(\d+)_(\d+)\.part$", re.IGNORECASE)

# dir_format placeholders derivable without download-time state.  The
# no-underscore aliases mirror basePlaceholder.add_no_underline().
_ROW_VARIABLES = {
    "username",
    "user_name",
    "model_username",
    "first_letter",
    "model_id",
    "post_id",
    "media_id",
    "media_type",
    "response_type",
    "download_type",
    "date",
}
_STATIC_VARIABLES = {
    "site_name",
    "profile",
    "save_location",
    "root",
    "config_path",
}
SUPPORTED_PLACEHOLDERS = (
    _ROW_VARIABLES
    | _STATIC_VARIABLES
    | {v.replace("_", "") for v in _ROW_VARIABLES}
)

# prune emptied folders up the old tree, but never climb forever
_MAX_PRUNE_DEPTH = 5


def _response_type(api_type) -> str:
    """Mirror Post.modified_responsetype (classes/of/posts.py:308) using the
    DB row's api_type instead of a live post."""
    key = str(api_type or "").lower()
    if key == "archived":
        return data.get_archived_responsetype() or "Archived"
    if key in {"post", "posts"}:
        key = "timeline"
    mapped = data.responsetype().get(key)
    if mapped in (None, ""):
        return str(api_type or "").capitalize()
    return str(mapped).capitalize()


def _row_variables(row, username, model_id) -> dict:
    date_str = ""
    try:
        date_str = arrow.get(
            row.get("posted_at") or row.get("created_at") or 0
        ).format(data.get_date())
    except Exception:
        date_str = ""
    variables = {
        "username": username,
        "user_name": username,
        "model_username": username,
        "first_letter": str(username)[0].capitalize(),
        "model_id": model_id,
        "post_id": row.get("post_id"),
        "media_id": row.get("media_id"),
        "media_type": str(row.get("media_type") or "").capitalize(),
        "response_type": _response_type(row.get("api_type")),
        "download_type": "Protected" if "mpd" in (row.get("link") or "") else "Normal",
        "date": date_str,
    }
    # mirror basePlaceholder.add_no_underline: dir_format may use either
    # spelling ({responsetype} is the documented default)
    for key, val in list(variables.items()):
        if "_" in key:
            variables[key.replace("_", "")] = val
    return variables


def _format_supported() -> bool:
    # parse_safe yields a spurious None for some formats (e.g. trailing
    # slash) — drop falsy entries before checking support
    placeholders = {p for p in parse_safe(data.get_dirformat() or "") if p}
    unsupported = placeholders - SUPPORTED_PLACEHOLDERS
    if unsupported:
        log.warning(
            "Skipping restructure: dir_format uses placeholder(s) that cannot "
            f"be recomputed from the database: {sorted(unsupported)}"
        )
        return False
    return True


def _move_file(old_path: pathlib.Path, new_path: pathlib.Path) -> str:
    """Move with moveHelper semantics (larger file wins).  Returns the
    outcome key matching the stats dict: 'moved', 'replaced' or
    'dupe_removed'."""
    if not new_path.exists():
        new_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(old_path), str(new_path))
        return "moved"
    old_size = old_path.stat().st_size
    new_size = new_path.stat().st_size
    if old_size >= new_size:
        new_path.unlink()
        shutil.move(str(old_path), str(new_path))
        return "replaced"
    old_path.unlink()
    return "dupe_removed"


def _prune_empty_dirs(old_dir: pathlib.Path) -> None:
    """Remove now-empty folders left behind by moves, bottom-up."""
    current = old_dir
    root = pathlib.Path(common_paths.get_save_location())
    for _ in range(_MAX_PRUNE_DEPTH):
        try:
            if not current.is_dir() or any(current.iterdir()):
                return
            if current == current.parent or not current.is_relative_to(root):
                return
            current.rmdir()
        except OSError:
            return
        current = current.parent


async def restructure_model_downloads(username, model_id, db_path=None) -> dict:
    """Move one model's downloaded files to the current dir_format.

    db_path: optional explicit database file.  Without it the path is
    resolved from the metadata format (which may consult the live
    session); the standalone command always passes it so it can run
    offline.

    Returns counters ({moved, replaced, dupe_removed, unchanged, missing,
    error}) — always safe to call: unsupported formats, missing files and
    individual failures never raise.
    """
    stats = {
        "moved": 0,
        "replaced": 0,
        "dupe_removed": 0,
        "unchanged": 0,
        "missing": 0,
        "error": 0,
    }
    if not data.get_restructure_downloads():
        return stats
    if not _format_supported():
        return stats

    import ofscraper.db.operations_.media as media_ops

    try:
        rows = await media_ops.get_downloaded_media_locations(
            model_id=model_id, username=username, db_path=db_path
        )
    except Exception as E:
        log.warning(f"[{username}] restructure: could not read database: {E}")
        stats["error"] += 1
        return stats

    updates = []
    old_dirs = set()
    for row in rows:
        directory = row.get("directory")
        filename = row.get("filename")
        if not directory or not filename:
            continue
        old_path = pathlib.Path(directory) / filename
        if not old_path.exists():
            stats["missing"] += 1
            continue
        try:
            variables = _row_variables(row, username, model_id)
            variables.update(
                {
                    "site_name": "Onlyfans",
                    "profile": common_paths.get_profile_path().name,
                    "save_location": common_paths.get_save_location(),
                    "root": common_paths.get_save_location(),
                }
            )
            rel = data.get_dirformat().format(**variables)
            new_dir = pathlib.Path(
                os.path.normpath(
                    pathlib.Path(common_paths.get_save_location(), rel)
                )
            )
        except Exception as E:
            log.debug(f"[{username}] restructure: could not compute new dir for {filename}: {E}")
            stats["error"] += 1
            continue

        if os.path.normcase(str(new_dir)) == os.path.normcase(
            str(old_path.parent)
        ):
            stats["unchanged"] += 1
            continue

        new_path = new_dir / filename
        try:
            stats[_move_file(old_path, new_path)] += 1
            updates.append((str(new_dir), filename, row["media_id"], row["post_id"]))
            old_dirs.add(old_path.parent)
        except Exception as E:
            log.warning(f"[{username}] restructure: failed to move {old_path}: {E}")
            stats["error"] += 1

    if updates:
        try:
            await media_ops.update_media_locations(
                updates=updates, model_id=model_id, username=username,
                db_path=db_path,
            )
        except Exception as E:
            log.warning(
                f"[{username}] restructure: files moved but database update failed: {E}"
            )
            stats["error"] += 1

    for old_dir in old_dirs:
        _prune_empty_dirs(old_dir)

    total = stats["moved"] + stats["replaced"] + stats["dupe_removed"]
    if total or stats["error"]:
        log.info(
            f"[{username}] restructure: {total} file(s) now match the current "
            f"folder layout ({stats['moved']} moved, {stats['replaced']} "
            f"replaced, {stats['dupe_removed']} duplicates removed, "
            f"{stats['unchanged']} already correct, {stats['missing']} not "
            f"found, {stats['error']} errors)"
        )
    return stats


async def cleanup_orphan_parts(username, model_id, db_path=None) -> dict:
    """Delete .part temp files whose media is complete on disk.

    When a DRM video completes via a fresh download (instead of resume),
    the temp tracks from its earlier failed attempts stay behind forever —
    the outage era left hundreds of these.  A temp is removed ONLY when the
    database says downloaded=1 AND the final file exists at the recorded
    location; in-flight and failed downloads keep their temps so
    auto_resume can still use them.

    Returns {'removed': n, 'freed_bytes': n, 'kept': n} and never raises.
    """
    stats = {"removed": 0, "freed_bytes": 0, "kept": 0}
    import ofscraper.db.operations_.media as media_ops

    try:
        rows = await media_ops.get_downloaded_media_locations(
            model_id=model_id, username=username, db_path=db_path
        )
    except Exception as E:
        log.debug(f"[{username}] part cleanup: could not read database: {E}")
        return stats

    finals = {
        (row.get("media_id"), row.get("post_id")): (
            row.get("directory"),
            row.get("filename"),
        )
        for row in rows
        if row.get("media_id") is not None
    }
    if not finals:
        return stats

    roots = []
    model_root = pathlib.Path(common_paths.get_save_location(), str(username))
    if model_root.is_dir():
        roots.append(model_root)
    temp_dir = str(data.get_TempDir() or "")
    if temp_dir:
        temp_path = pathlib.Path(temp_dir)
        if temp_path.is_dir():
            roots.append(temp_path)

    for root in roots:
        try:
            parts = list(root.rglob("*.part"))
        except OSError:
            continue
        for part in parts:
            match = _PART_NAME_RE.search(part.name)
            if not match:
                continue
            entry = finals.get((int(match.group(1)), int(match.group(2))))
            if not entry:
                continue  # not recorded as downloaded — may still resume
            directory, filename = entry
            final = pathlib.Path(directory or "", filename or "")
            if not final.exists():
                stats["kept"] += 1
                continue
            try:
                size = part.stat().st_size
                part.unlink()
                stats["removed"] += 1
                stats["freed_bytes"] += size
            except OSError as E:
                log.debug(f"[{username}] part cleanup: could not remove {part}: {E}")

    if stats["removed"]:
        log.info(
            f"[{username}] removed {stats['removed']} orphan .part file(s) "
            f"({stats['freed_bytes'] / 1e9:.2f} GB freed; media already "
            "complete on disk)"
        )
    return stats
