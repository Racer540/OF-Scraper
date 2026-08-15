"""
Check screen: run post/message/story/paid checks, browse results, download.

Runs the same checker() pipeline the CLI does; the Textual results table is
replaced by this screen via the check shim in gui/patches.py:

- Run a check -> worker fills GuiState.check_rows -> table appears here
- Select rows -> "Download selected" enqueues (index, row) into the real
  row_queue (classes/table/app.py), exactly like InputApp.add_to_row_queue
  (app.py:407-418): rows flip to "[downloading]", the shared consumer
  thread downloads them, and update_cell_state flows back through the shim
- "Finish" sets check_finished, unblocking the job thread so the job
  completes cleanly
"""

from nicegui import ui

import ofscraper.gui.screens as screens
from ofscraper.gui.state import get_state

CHECK_COMMANDS = {
    "post_check": {
        "label": "Post check (timeline/areas)",
        "input_label": "URLs or usernames (comma separated)",
        "url_flag": "-u",
        "areas": True,
    },
    "msg_check": {
        "label": "Message check",
        "input_label": "URLs or message IDs (comma separated)",
        "url_flag": "-u",
        "areas": False,
    },
    "story_check": {
        "label": "Story check",
        "input_label": "Usernames (comma separated)",
        "url_flag": "-u",
        "areas": False,
    },
    "paid_check": {
        "label": "Paid content check",
        "input_label": "Usernames or user IDs (comma separated)",
        "url_flag": "-u",
        "areas": False,
    },
}

POST_CHECK_AREAS = [
    "Timeline",
    "Archived",
    "Pinned",
    "Streams",
    "Labels",
    "all",
]

RESULT_COLUMNS = [
    {"name": "number", "label": "#", "field": "number", "align": "left"},
    {"name": "cart", "label": "State", "field": "download_cart", "align": "left"},
    {"name": "username", "label": "User", "field": "username", "align": "left"},
    {"name": "mediatype", "label": "Type", "field": "mediatype", "align": "left"},
    {"name": "post_date", "label": "Post date", "field": "post_date", "align": "left"},
    {"name": "price", "label": "Price", "field": "price", "align": "left"},
    {"name": "responsetype", "label": "Source", "field": "responsetype", "align": "left"},
    {"name": "media_id", "label": "Media ID", "field": "media_id", "align": "left"},
    {"name": "post_id", "label": "Post ID", "field": "post_id", "align": "left"},
]


def _split_targets(value) -> list:
    return [v.strip() for v in (value or "").split(",") if v.strip()]


@screens.register("Checks")
def render(nav):
    state = get_state()

    ui.label("Content Checks").classes("text-2xl font-bold")
    ui.label(
        "Scan a user's posts, messages, stories or purchases into a table, "
        "then pick what to download."
    ).classes("text-sm text-gray-400")

    with ui.card().classes("w-full"):
        command = ui.select(
            {k: v["label"] for k, v in CHECK_COMMANDS.items()},
            value="post_check",
        ).classes("w-96")
        targets = ui.input(
            CHECK_COMMANDS["post_check"]["input_label"],
            placeholder="name1,name2",
        ).classes("w-full")
        url_file = ui.input(
            "…or a file with one entry per line (-f)",
            placeholder="D:\\path\\to\\list.txt",
        ).classes("w-full")
        areas = screens.check_group(
            "Check areas (post check only)", POST_CHECK_AREAS, default=["Timeline"]
        )
        with ui.row().classes("w-full items-center"):
            force = ui.checkbox("Force fresh scan (ignore cache) (-fo)", value=False)
            unlocked_only = ui.toggle(
                {"": "all", "-ucl": "unlocked only", "-lc": "locked only"}, value=""
            )
            ui.space()
            screens.run_button(
                lambda: _build_argv(command, targets, url_file, areas, force, unlocked_only),
                "Check job",
                label="Run check",
            )

    # ------------------------------------------------------------ results
    with ui.card().classes("w-full"):
        with ui.row().classes("w-full items-center"):
            ui.label("Results").classes("text-lg font-semibold")
            result_status = ui.label("no check run yet").classes(
                "text-sm text-gray-400"
            )
            ui.space()
            download_button = ui.button(
                "Download selected", on_click=lambda: _download_selected(table)
            )
            finish_button = ui.button(
                "Finish", color="positive", on_click=_finish_check
            )

        table = ui.table(columns=RESULT_COLUMNS, rows=[], selection="multiple", row_key="media_id").classes(
            "w-full"
        )
        table.props("flat bordered")
        ui.label(
            "Select rows (click checkboxes) then 'Download selected'. "
            "Finish closes the check job."
        ).classes("text-xs text-gray-400")

    last_version = -1

    def poll_results():
        nonlocal last_version
        if state.check_rows_ready.is_set() and state.check_version != last_version:
            last_version = state.check_version
            table.rows = [
                {k: r.get(k, "") for k in
                 ("number", "download_cart", "username", "mediatype", "post_date",
                  "price", "responsetype", "media_id", "post_id")}
                for r in state.check_rows
            ]
            downloading = sum(
                1 for r in state.check_rows if r.get("download_cart") == "[downloading]"
            )
            result_status.text = (
                f"{len(state.check_rows)} rows — {downloading} downloading"
            )

    poll_results()
    ui.timer(0.5, poll_results)


def _build_argv(command, targets, url_file, areas, force, unlocked_only) -> list:
    spec = CHECK_COMMANDS.get(command.value, {})
    argv = [command.value]
    values = _split_targets(targets.value)
    if values:
        argv += [spec.get("url_flag", "-u"), ",".join(values)]
    if (url_file.value or "").strip():
        argv += ["-f", url_file.value.strip()]
    if spec.get("areas"):
        selected = areas()
        if selected:
            argv += ["-ca", ",".join(selected)]
    if force.value:
        argv.append("-fo")
    if unlocked_only.value:
        argv.append(unlocked_only.value)
    return argv


def _download_selected(table):
    import ofscraper.classes.table.app as table_app

    state = get_state()
    # table rows are 9-key projections; the queue consumer and the shim's
    # update_cell_state work with the FULL row dicts and their 'index' key
    selected_numbers = {str(r.get("number")) for r in table.selected}
    downloadable = {"[added]", "[]", ""}
    cart = []
    for full in state.check_rows:
        key = str(full.get("index"))
        if key in selected_numbers and full.get("download_cart") in downloadable:
            full["download_cart"] = "[downloading]"
            cart.append((key, full))
    if not cart:
        ui.notify("No downloadable rows selected", type="warning")
        return
    # mirror InputApp.add_to_row_queue: enqueue (index, row); the shared
    # consumer thread handles the rest
    for ele in cart:
        table_app.row_queue.put(ele)
    state.check_version += 1
    ui.notify(f"Queued {len(cart)} downloads", type="positive")


def _finish_check():
    state = get_state()
    state.check_finished.set()
    ui.notify("Finishing check job…", type="info")
