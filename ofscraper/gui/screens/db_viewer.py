"""
DB Viewer screen: browse a model's local database and export to CSV.

Instead of running the CLI `db` command (which prints a rich table per
model), this screen configures the same settings via argbuild and then calls
DBManager(name, id).get_wanted_media() directly — the prompt-free seam the
CLI's print step sits on top of (commands/db.py:47-52). The filtered/sorted
list lands in db_manager.media; write_to_csv() honors args.export.
"""

import threading
import time

from nicegui import ui

import ofscraper.gui.screens as screens
from ofscraper.gui.state import get_state

DB_AREAS = [
    "Timeline",
    "Archived",
    "Messages",
    "Pinned",
    "Highlights",
    "Stories",
    "Streams",
    "Profile",
    "all",
]

DB_SORTS = ["posted", "created", "filename", "length", "postid", "mediaid", "size"]

RESULT_COLUMNS = [
    {"name": "filename", "label": "Filename", "field": "filename", "align": "left"},
    {"name": "mediatype", "label": "Type", "field": "mediatype", "align": "left"},
    {"name": "posted_at", "label": "Posted", "field": "posted_at", "align": "left"},
    {"name": "size_human", "label": "Size", "field": "size_human", "align": "left"},
    {"name": "downloaded", "label": "Downloaded", "field": "downloaded", "align": "left"},
    {"name": "unlocked", "label": "Unlocked", "field": "unlocked", "align": "left"},
    {"name": "media_id", "label": "Media ID", "field": "media_id", "align": "left"},
    {"name": "post_id", "label": "Post ID", "field": "post_id", "align": "left"},
]


def _load_table(model_name, model_id, argv, after):
    """Configure settings from the form, then build the table on a worker."""

    def work():
        state = get_state()
        try:
            from ofscraper.gui import argbuild

            argbuild.build_job(argv)  # settings only; we do not run the job
            import ofscraper.commands.db as db_commands

            manager_obj = db_commands.DBManager(model_name, model_id)
            manager_obj.get_wanted_media()
            state.db_rows = list(manager_obj.media or [])
            state.db_load_error = ""
            # no-ops unless -ep was set in the form
            manager_obj.write_to_csv()
        except Exception as E:
            state.db_rows = []
            state.db_load_error = str(E)
        state.db_loaded_at = time.time()
        if after:
            after()

    threading.Thread(target=work, name="gui-db-load", daemon=True).start()


@screens.register("DB Viewer")
def render(nav):
    state = get_state()

    ui.label("DB Viewer").classes("text-2xl font-bold")
    ui.label(
        "Browse what your local database has recorded for a model — filter, "
        "sort, and export to CSV."
    ).classes("text-sm text-gray-400")

    with ui.card().classes("w-full"):
        with ui.row().classes("w-full items-center"):
            model_select = ui.select(
                {m.name: m.name for m in state.models} or {"": "— refresh models first —"},
                value=(state.models[0].name if state.models else None),
                label="Model",
            ).classes("w-72")
            ui.button("Refresh models", on_click=lambda: nav("Models")).props(
                "outline"
            )
        areas = screens.check_group(
            "Areas", DB_AREAS, default=["Timeline", "Messages"]
        )
        with ui.row().classes("w-full items-center"):
            db_sort = ui.select(
                {s: s for s in DB_SORTS}, label="Sort by", value="posted"
            ).classes("w-40")
            db_asc = ui.checkbox("Ascending", value=True)
            max_count = ui.number("Max rows", min=0, step=1)
        with ui.row().classes("w-full items-center"):
            downloaded = ui.toggle(
                {"": "all", "-dwl": "downloaded", "-ndw": "not downloaded"}, value=""
            )
            unlocked = ui.toggle(
                {"": "all", "-ucl": "unlocked", "-lc": "locked"}, value=""
            )
            preview = ui.toggle(
                {"": "all", "-pv": "preview", "-npv": "no preview"}, value=""
            )
            protected = ui.toggle(
                {"": "all", "-to": "protected", "-no": "normal"}, value=""
            )
        with ui.row().classes("w-full items-center"):
            media_id = ui.input("Media ID (-mid)").classes("grow")
            export_path = ui.input(
                "Export CSV path (-ep)", placeholder="D:\\exports\\table.csv"
            ).classes("grow")

    with ui.card().classes("w-full"):
        with ui.row().classes("w-full items-center"):
            status_label = ui.label("no table loaded").classes("text-sm text-gray-400")
            ui.space()
            ui.button(
                "Load table",
                on_click=lambda: _load_table(
                    model_select.value,
                    _model_id(model_select.value),
                    _build_argv(
                        areas, db_sort, db_asc, max_count, downloaded, unlocked,
                        preview, protected, media_id, export_path,
                    ),
                    after=None,
                ),
            )

        table = ui.table(columns=RESULT_COLUMNS, rows=[], row_key="media_id").classes(
            "w-full"
        )
        table.props("flat bordered")

    error_label = ui.label(state.db_load_error).classes("text-sm text-red-500")

    last_rendered = state.db_loaded_at

    def poll():
        nonlocal last_rendered
        if state.db_loaded_at and state.db_loaded_at != last_rendered:
            last_rendered = state.db_loaded_at
            table.rows = [
                {k: str(r.get(k, "")) for k in
                 ("filename", "mediatype", "posted_at", "size_human", "downloaded",
                  "unlocked", "media_id", "post_id")}
                for r in state.db_rows
            ]
            status_label.text = f"{len(state.db_rows)} rows"
        error_label.set_text(state.db_load_error)
        error_label.set_visibility(bool(state.db_load_error))

    poll()
    ui.timer(0.5, poll)


def _model_id(name):
    for m in get_state().models:
        if m.name == name:
            return m.id
    return None


def _build_argv(
    areas, db_sort, db_asc, max_count, downloaded, unlocked, preview,
    protected, media_id, export_path,
) -> list:
    argv = ["db"]
    selected = areas() or ["Timeline"]
    argv += ["-o", ",".join(selected)]
    if db_sort.value:
        argv += ["-dst", db_sort.value]
    if db_asc.value:
        argv.append("-bdc")  # --db-asc: table defaults to descending
    if max_count.value:
        argv += ["-mxc", str(int(max_count.value))]
    if downloaded.value:
        argv.append(downloaded.value)
    if unlocked.value:
        argv.append(unlocked.value)
    if preview.value:
        argv.append(preview.value)
    if protected.value:
        argv.append(protected.value)
    if media_id.value:
        argv += ["-mid", media_id.value]
    if (export_path.value or "").strip():
        argv += ["-ep", export_path.value.strip()]
    return argv
