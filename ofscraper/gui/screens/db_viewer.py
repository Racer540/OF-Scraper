"""
DB Viewer screen: browse a model's local database and export to CSV.

Instead of running the CLI `db` command (which prints a rich table per
model), this screen configures the same settings via argbuild and then calls
DBManager(name, id).get_wanted_media() directly — the prompt-free seam the
CLI's print step sits on top of (commands/db.py:47-52). The filtered/sorted
list lands in db_manager.media; write_to_csv() honors args.export.
"""

import pathlib
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

            # The CLI db() entrypoint calls actions.select_areas() before
            # touching DBManager — that is the step which resolves args.posts
            # (-o) into args.download_area.  Without it, DBManager.get_all_media
            # dies with 'TypeError: argument of type NoneType is not iterable'.
            import ofscraper.utils.args.accessors.areas as areas
            import ofscraper.utils.settings as settings

            args = settings.get_args()
            args.download_area = areas.get_download_area()
            settings.update_args(args)

            # A model that was never scraped has no user_data.db; the sqlite
            # layer would create an empty one, fail on the missing table and
            # tenacity-retry for ~30s before surfacing that.  Pre-check.
            import ofscraper.classes.placeholder as placeholder

            db_path = pathlib.Path(
                placeholder.databasePlaceholder().databasePathHelper(
                    model_id, model_name
                )
            )
            if not db_path.exists():
                raise FileNotFoundError(
                    f"No local database for {model_name} yet — run a "
                    "download or metadata job for this model first"
                )

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
                {m.name: m.name for m in state.models}
                or {"": "— fetching model list… —"},
                value=(state.models[0].name if state.models else None),
                label="Model",
            ).classes("w-72")
            # The Models screen is the primary fetch surface, but the DB
            # Viewer must not dead-end on an empty cache — pull the list
            # ourselves the first time.
            from ofscraper.gui.screens.model_picker import fetch_models

            if not state.models:
                fetch_models()
            ui.button("Refresh models", on_click=fetch_models).props("outline")
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

            def load_click():
                if not model_select.value:
                    ui.notify(
                        "Pick a model first (wait for the list to load)",
                        type="warning",
                    )
                    return
                _load_table(
                    model_select.value,
                    _model_id(model_select.value),
                    _build_argv(
                        areas, db_sort, db_asc, max_count, downloaded, unlocked,
                        preview, protected, media_id, export_path,
                    ),
                    after=None,
                )

            ui.button("Load table", on_click=load_click)

        table = ui.table(columns=RESULT_COLUMNS, rows=[], row_key="media_id").classes(
            "w-full"
        )
        table.props("flat bordered")

    error_label = ui.label(state.db_load_error).classes("text-sm text-red-500")

    last_rendered = state.db_loaded_at
    models_rendered = state.models_fetched_at

    def poll():
        nonlocal last_rendered, models_rendered
        if state.models_fetched_at and state.models_fetched_at != models_rendered:
            models_rendered = state.models_fetched_at
            if state.models:
                model_select.options = {m.name: m.name for m in state.models}
                if model_select.value not in model_select.options:
                    model_select.value = state.models[0].name
                model_select.update()
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
