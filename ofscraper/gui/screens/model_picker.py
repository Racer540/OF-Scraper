"""
Model picker screen: subscription list with multi-select and sorting.

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

# All columns sort client-side (click the header).  id/price carry raw
# numeric values so 1000 sorts after 999 and $10 after $9; the human display
# for price goes through a body-cell-price slot.  Dates are zero-padded
# YYYY-MM-DD, which sorts correctly as text.
COLUMNS = [
    {"name": "name", "label": "Name", "field": "name",
     "align": "left", "sortable": True},
    {"name": "id", "label": "ID", "field": "id",
     "align": "left", "sortable": True},
    {"name": "price", "label": "Price", "field": "price",
     "align": "left", "sortable": True},
    {"name": "status", "label": "Status", "field": "status",
     "align": "left", "sortable": True},
    {"name": "renewed", "label": "Renewal", "field": "renewed",
     "align": "left", "sortable": True},
    {"name": "last_seen", "label": "Last seen", "field": "last_seen",
     "align": "left", "sortable": True},
]


def fetch_models():
    """Fetch the subscription list on a worker thread (network + auth).

    A successful fetch is persisted to the models cache so the next GUI
    session starts with this list instead of an empty table.
    """

    def work():
        state = get_state()
        state.models_fetch_in_flight = True
        try:
            import ofscraper.managers.manager as manager_module

            if not isinstance(manager_module.Manager, manager_module.mainManager):
                manager_module.Manager = manager_module.mainManager()
            model_manager = manager_module.Manager.current_model_manager
            model_manager.sync_models()
            state.models = model_manager.all_subs
            state.models_fetch_error = ""
            state.models_cache_note = ""
            if state.models:
                from ofscraper.gui import models_cache

                models_cache.save_models(state.models)
                state.models_cache_fetched_at = time.time()
        except Exception as E:
            state.models_fetch_error = str(E)
        finally:
            state.models_fetch_in_flight = False
        state.models_fetched_at = time.time()

    threading.Thread(target=work, name="gui-model-fetch", daemon=True).start()


def ensure_models():
    """Guarantee the model list is usable without blocking.

    1. If the in-memory list is empty, hydrate it instantly from the
       persisted cache (no auth needed).
    2. If the list is stale per the configured interval AND the auth check
       confirmed the session, refresh it in the background — the table
       updates via the existing poll when the fetch lands.
    """
    state = get_state()
    if not state.models:
        from ofscraper.gui import models_cache

        models, fetched_at = models_cache.load_models()
        if models:
            state.models = models
            state.models_cache_fetched_at = fetched_at
            state.models_cache_note = (
                f"cached {models_cache.cache_age_text(fetched_at)}"
            )
            state.models_fetched_at = time.time()  # trigger row re-render

    from ofscraper.gui import models_cache

    if (
        models_cache.auto_refresh_due(state.models_cache_fetched_at)
        and state.auth_ok is True
        and not state.models_fetch_in_flight
    ):
        fetch_models()


def _rows(models) -> list:
    rows = []
    for model in models:
        try:
            price = model.regular_price
            rows.append(
                {
                    "name": model.name,
                    "id": model.id,
                    "price": float(price) if price is not None else -1.0,
                    "price_display": f"${price}" if price is not None else "Free",
                    "status": "active" if model.active else "expired",
                    "renewed": model.renewed_string or "",
                    "last_seen": model.last_seen_formatted or "",
                }
            )
        except Exception:
            continue
    return rows


@screens.register("Models")
def render(nav):
    state = get_state()
    # hydrate from the persisted cache instantly; kick a background
    # refresh only if the list is stale and the auth check confirmed
    ensure_models()

    with ui.row().classes("w-full items-center"):
        ui.label("Models").classes("text-2xl font-bold")
        ui.space()
        suffix = (
            f" ({state.models_cache_note})" if state.models_cache_note else ""
        )
        status_label = ui.label(
            "idle"
            if not state.models
            else f"{len(state.models)} loaded{suffix}"
        ).classes("text-sm text-gray-400")
        ui.button("Refresh list", on_click=fetch_models)

    ui.label(
        "Select the accounts to process, then switch to the Scrape screen — "
        "your selection carries over. Requires a working login (Auth screen)."
    ).classes("text-sm text-gray-400")

    error_label = ui.label(state.models_fetch_error).classes("text-sm text-red-500")

    def _set_selection(rows):
        # programmatic selection doesn't emit the 'selection' event, so
        # update the shared state ourselves
        table.selected = rows
        state.selected_usernames = [r["name"] for r in rows]
        selected_label.text = f"Selected: {len(rows)}"

    def select_all_active():
        _set_selection([r for r in table.rows if r["status"] == "active"])

    def clear_selection():
        _set_selection([])

    # selection controls live ABOVE the table so they stay reachable
    # without scrolling past every row
    with ui.row().classes("w-full items-center"):
        ui.button("Select all active", on_click=select_all_active).props("outline")
        ui.button("Clear selection", on_click=clear_selection).props("outline")
        ui.space()
        selected_label = ui.label(
            f"Selected: {len(state.selected_usernames)}"
        ).classes("text-sm")
        ui.button("Use in Scrape", on_click=lambda: nav("Scrape"))

    table = ui.table(
        columns=COLUMNS,
        rows=[],
        selection="multiple",
        row_key="name",
        # start where the old dropdown defaulted: active subs first
        pagination={"sortBy": "status", "descending": False, "rowsPerPage": 20},
    ).classes("w-full")
    table.props("flat bordered")
    # display "$9.99"/"Free" while the column sorts on the raw numeric price
    table.add_slot(
        "body-cell-price",
        """
        <q-td :props="props">{{ props.row.price_display }}</q-td>
        """,
    )

    def apply_rows():
        # rows rebuild keeps row keys stable, so the current selection survives
        table.rows = _rows(state.models)

    apply_rows()

    def sync_selection():
        state.selected_usernames = [r["name"] for r in table.selected]
        selected_label.text = f"Selected: {len(table.selected)}"

    table.on("selection", sync_selection)

    # poll fetch results; re-render rows when a fetch lands
    last_rendered = state.models_fetched_at
    # the auth check may land after this screen rendered — retry the
    # stale-cache auto-refresh once it does (exactly once per visit)
    auto_refresh_attempted = False

    def poll():
        nonlocal last_rendered, auto_refresh_attempted
        if state.models_fetched_at and state.models_fetched_at != last_rendered:
            last_rendered = state.models_fetched_at
            apply_rows()
            suffix = (
                f" ({state.models_cache_note})" if state.models_cache_note else ""
            )
            status_label.text = (
                f"{len(state.models)} loaded{suffix}"
                if state.models and not state.models_fetch_error
                else "fetch failed"
            )
        if not auto_refresh_attempted and state.auth_ok is True:
            auto_refresh_attempted = True
            from ofscraper.gui import models_cache

            if (
                models_cache.auto_refresh_due(state.models_cache_fetched_at)
                and not state.models_fetch_in_flight
            ):
                fetch_models()
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
