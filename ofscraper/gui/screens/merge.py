"""
Merge screen: fold one profile's database folder into another.

Calls merge_loop(curr_folder, new_db) directly (ofscraper/utils/merge.py:28)
on a worker thread — the same @run-decorated coroutine the CLI's prompt-
driven merge_runner uses, minus the terminal prompts.
"""

import threading
import time

from nicegui import ui

import ofscraper.gui.screens as screens
from ofscraper.gui.state import get_state


def _run_merge(curr_folder, new_db, after=None):
    def work():
        state = get_state()
        try:
            from ofscraper.utils.merge import merge_loop

            completed, skipped = merge_loop(curr_folder, new_db)
            state.merge_result = (
                f"completed: {completed}  skipped: {skipped}"
                if isinstance(completed, int)
                else f"completed: {len(completed or [])}  skipped: {len(skipped or [])}"
            )
            state.merge_error = ""
        except Exception as E:
            state.merge_result = ""
            state.merge_error = str(E)
        state.merge_finished_at = time.time()
        if after:
            after()

    threading.Thread(target=work, name="gui-merge", daemon=True).start()


@screens.register("Merge")
def render(nav):
    state = get_state()

    ui.label("Merge Databases").classes("text-2xl font-bold")
    ui.label(
        "Copy records from a source profile folder's database into a target "
        "profile's database. Back up your data folder first — this writes to "
        "the target DB."
    ).classes("text-sm text-gray-400")

    with ui.card().classes("w-full"):
        with ui.row().classes("w-full items-center"):
            curr = ui.input(
                "Source profile folder (its DB is read)",
                placeholder="C:\\Users\\you\\.config\\ofscraper\\profile_old",
            ).classes("grow")
        with ui.row().classes("w-full items-center"):
            new_db = ui.input(
                "Target profile folder (its DB is written)",
                placeholder="C:\\Users\\you\\.config\\ofscraper\\profile_new",
            ).classes("grow")

        def defaults():
            try:
                import ofscraper.utils.paths.db as db_paths

                curr.value = curr.value or str(db_paths.get_default_current() or "")
                new_db.value = new_db.value or str(db_paths.get_default_merge() or "")
            except Exception:
                pass

        ui.button("Fill default paths", on_click=defaults).props("outline")

        with ui.row().classes("w-full items-center"):
            result_label = ui.label(state.merge_result or "no merge run yet").classes(
                "text-sm"
            )
            ui.space()
            ui.button(
                "Run merge",
                color="warning",
                on_click=lambda: _run_merge(curr.value, new_db.value),
            )

    error_label = ui.label(state.merge_error).classes("text-sm text-red-500")

    last_rendered = state.merge_finished_at

    def poll():
        nonlocal last_rendered
        if state.merge_finished_at and state.merge_finished_at != last_rendered:
            last_rendered = state.merge_finished_at
            result_label.text = state.merge_result or "finished"
        error_label.set_text(state.merge_error)
        error_label.set_visibility(bool(state.merge_error))

    poll()
    ui.timer(0.5, poll)
