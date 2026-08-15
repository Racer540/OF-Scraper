"""
Model picker screen: subscription list with multi-select.

Fetches models through ModelManager.sync_models() (the same API-backed fetch
the CLI uses) on a worker thread, then renders all_subs in a selectable
table.  Selection is stored on GuiState and consumed by the Scrape screen
(and any other screen that builds -u args).

Thread-safety: the worker only mutates GuiState; a ui.timer on this screen
polls the fetch timestamp and refreshes the table — no UI calls from the
worker thread.
"""

import threading
import time

from nicegui import ui

import ofscraper.gui.screens as screens
from ofscraper.gui.state import get_state

COLUMNS = [
    {"name": "name", "label": "Name", "field": "name", "align": "left"},
    {"name": "id", "label": "ID", "field": "id", "align": "left"},
    {"name": "price", "label": "Price", "field": "price", "align": "left"},
    {"name": "status", "label": "Status", "field": "status", "align": "left"},
    {"name": "renewed", "label": "Renewal", "field": "renewed", "align": "left"},
    {"name": "last_seen", "label": "Last seen", "field": "last_seen", "align": "left"},
]


def fetch_models():
    """Fetch the subscription list on a worker thread (network + auth)."""

    def work():
        state = get_state()
        try:
            import ofscraper.managers.manager as manager_module

            if not isinstance(manager_module.Manager, manager_module.mainManager):
                manager_module.Manager = manager_module.mainManager()
            model_manager = manager_module.Manager.current_model_manager
            model_manager.sync_models()
            state.models = model_manager.all_subs
            state.models_fetch_error = ""
        except Exception as E:
            state.models_fetch_error = str(E)
        state.models_fetched_at = time.time()

    threading.Thread(target=work, name="gui-model-fetch", daemon=True).start()


def _rows(models) -> list:
    rows = []
    for model in models:
        try:
            rows.append(
                {
                    "name": model.name,
                    "id": str(model.id),
                    "price": f"${model.regular_price}",
                    "status": "active" if model.active else "expired",
                    "renewed": model.renewed_string or "",
                    "last_seen": model.last_seen_formatted or "",
                }
            )
        except Exception:
            continue
    rows.sort(key=lambda r: (r["status"] != "active", r["name"].lower()))
    return rows


@screens.register("Models")
def render(nav):
    state = get_state()

    with ui.row().classes("w-full items-center"):
        ui.label("Models").classes("text-2xl font-bold")
        ui.space()
        status_label = ui.label(
            "idle" if not state.models else f"{len(state.models)} loaded"
        ).classes("text-sm text-gray-400")
        ui.button("Refresh list", on_click=fetch_models)

    ui.label(
        "Select the accounts to process, then switch to the Scrape screen — "
        "your selection carries over. Requires a working login (Auth screen)."
    ).classes("text-sm text-gray-400")

    error_label = ui.label(state.models_fetch_error).classes("text-sm text-red-500")

    table = ui.table(
        columns=COLUMNS,
        rows=_rows(state.models),
        selection="multiple",
        row_key="name",
    ).classes("w-full")
    table.props("flat bordered")

    selected_label = ui.label(f"Selected: {len(state.selected_usernames)}").classes(
        "text-sm"
    )

    def sync_selection():
        state.selected_usernames = [r["name"] for r in table.selected]
        selected_label.text = f"Selected: {len(table.selected)}"

    table.on("selection", sync_selection)

    with ui.row().classes("w-full items-center"):
        ui.space()
        ui.button("Use in Scrape", on_click=lambda: nav("Scrape"))

    # poll fetch results; re-render rows when a fetch lands
    last_rendered = state.models_fetched_at

    def poll():
        nonlocal last_rendered
        if state.models_fetched_at and state.models_fetched_at != last_rendered:
            last_rendered = state.models_fetched_at
            table.rows = _rows(state.models)
            status_label.text = (
                f"{len(state.models)} loaded"
                if state.models and not state.models_fetch_error
                else "fetch failed"
            )
        error = state.models_fetch_error
        if error:
            friendly = error
            lowered = error.lower()
            if "400" in error or "401" in error or "403" in error or "down" in lowered:
                friendly = (
                    "OnlyFans rejected the login — go to the Auth screen, "
                    "press Check status, and re-save working credentials. "
                    f"(detail: {error[:160]})"
                )
            elif "timed out" in lowered or "timeout" in lowered:
                friendly = f"Request timed out — retry. (detail: {error[:160]})"
            error_label.set_text(friendly)
        else:
            error_label.set_text("")
        error_label.set_visibility(bool(error))

    poll()
    ui.timer(0.5, poll)
