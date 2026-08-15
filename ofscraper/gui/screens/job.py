"""
Job monitor screen: live log pane, progress bars, cancel button, outcome.

- Logs drain from the LogBuffer (written by worker threads) on a 0.25 s timer.
- Progress snapshots the Rich progress singletons on a 0.5 s timer.
- Cancel sets the cancel event; the progress-update hooks installed by
  patches.py raise KeyboardInterrupt at the next update (cooperative, usually
  sub-second during downloads).
"""

from nicegui import ui

import ofscraper.gui.screens as screens
from ofscraper.gui.bridges import progress as progress_bridge
from ofscraper.gui.state import JobStatus, get_state

MAX_DOWNLOAD_ROWS = 20


def _bar(task, show_text=True) -> None:
    frac = task.fraction
    percent = int(frac * 100) if task.total else 0
    label = task.description or "working"
    if task.total:
        label = f"{label} — {int(task.completed)}/{int(task.total)}"
    ui.linear_progress(frac, show_value=False).classes("w-full")
    if show_text:
        ui.label(label).classes("text-xs text-gray-400 truncate")


def _render_task_list(tasks, title, empty="idle"):
    if not tasks:
        return
    visible = [t for t in tasks if t.visible]
    if not visible:
        return
    with ui.column().classes("w-full gap-1"):
        ui.label(title).classes("text-sm font-semibold")
        for task in visible[:MAX_DOWNLOAD_ROWS]:
            _bar(task)


@screens.register("Job")
def render(nav):
    state = get_state()

    with ui.row().classes("w-full items-center"):
        ui.label("Job Monitor").classes("text-2xl font-bold")
        ui.space()
        status_label = ui.label().classes("text-lg")
        cancel_button = ui.button("Cancel", color="negative")

    desc_label = ui.label().classes("text-sm text-gray-400")

    progress_container = ui.column().classes("w-full gap-2")

    ui.separator()
    with ui.row().classes("w-full items-center"):
        ui.label("Log").classes("text-lg font-semibold")
        clear_button = ui.button("Clear", on_click=state.log_buffer.clear)

    log = ui.log(max_lines=1000).classes("w-full h-72 font-mono text-xs")

    def refresh_status():
        status = state.status
        status_label.text = f"Status: {status.value.capitalize()}"
        desc_label.text = state.job_description
        if state.job_result:
            status_label.text += f" — {state.job_result}"
        if state.job_error:
            status_label.text += f" (error: {state.job_error})"
        cancel_button.set_enabled(status == JobStatus.RUNNING)
        if status == JobStatus.CANCELLING:
            status_label.text += " — stopping (waiting for job to unwind)"

    def refresh_progress():
        snap = progress_bridge.snapshot()
        progress_container.clear()
        with progress_container:
            activity_desc = snap["activity_desc"]
            if activity_desc and activity_desc[0].visible:
                ui.label(activity_desc[0].description).classes("font-mono text-sm")
            _render_task_list(snap["activity_counter"], "Overall")
            _render_task_list(snap["download"]["overall"], "Downloads (total)")
            _render_task_list(snap["download"]["job"], "Downloads")
            _render_task_list(snap["api"]["overall"], "API (total)")
            _render_task_list(snap["api"]["job"], "API")
            _render_task_list(snap["metadata"]["overall"], "Metadata")
            _render_task_list(snap["like"]["overall"], "Likes")
            _render_task_list(snap["userlist"]["overall"], "Model list")
            if not progress_container.slots and not any(
                snap[k] for k in ("activity_desc",)
            ):
                ui.label("No active progress").classes("text-sm text-gray-400")

    def refresh_log():
        for line in state.log_buffer.drain():
            log.push(line)

    refresh_status()
    refresh_progress()
    ui.timer(0.5, refresh_status)
    ui.timer(0.5, refresh_progress)
    ui.timer(0.25, refresh_log)

    cancel_button.on_click(state.request_cancel)
