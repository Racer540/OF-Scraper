"""
Home screen: dashboard with auth status, profile, job state, and navigation.

Auth status comes from the shared background check (gui/authstatus.py), the
same worker that drives the header badge and the Auth screen.
"""

import shlex

from nicegui import ui

import ofscraper.gui.screens as screens
from ofscraper.gui.state import get_state


def _version() -> str:
    try:
        from ofscraper._version import __version__

        return __version__
    except Exception:
        return "dev"


def _profile_name() -> str:
    try:
        import ofscraper.utils.profiles.data as profile_data

        return profile_data.get_current_config_profile() or "default"
    except Exception:
        return "?"


def _auth_file_summary() -> str:
    """What auth.json actually contains.  It never stores a username — the
    account name only exists after a live check (see refresh_auth below),
    so this reports the auth_id instead of guessing "unknown user"."""
    try:
        import ofscraper.utils.auth.utils.dict as auth_dict

        auth = auth_dict.get_auth_dict() or {}
        if not auth:
            return "auth.json: not saved yet — use the Auth screen"
        notes = []
        if auth.get("sess"):
            notes.append("sess cookie saved")
        auth_id = auth.get("auth_id") or auth.get("auth_uid_")
        if auth_id:
            notes.append(f"account id {auth_id}")
        if not auth.get("x-bc"):
            notes.append("x-bc missing")
        return "auth.json: " + (", ".join(notes) or "file exists but is empty")
    except Exception:
        return "auth.json: not found — use the Auth screen"


@screens.register("Home")
def render(nav):
    state = get_state()

    with ui.row().classes("w-full items-center gap-4"):
        ui.label("OF-Scraper").classes("text-3xl font-bold")
        ui.badge(f"v{_version()}", color="blue")

    with ui.grid(columns=2).classes("w-full gap-4"):
        with ui.card().classes("min-w-0"):
            ui.label("Authentication").classes("text-xl font-semibold")
            login_label = ui.label("Login: unknown")
            ui.label(_auth_file_summary()).classes("text-sm text-gray-400")

            def check_auth():
                from ofscraper.gui.authstatus import start_auth_check

                start_auth_check()
                login_label.text = "checking… (can take ~30s)"

            ui.button("Check auth status", on_click=check_auth)

        with ui.card().classes("min-w-0"):
            ui.label("Profile").classes("text-xl font-semibold")
            ui.label(f"Current profile: {_profile_name()}")

        with ui.card().classes("min-w-0"):
            ui.label("Job").classes("text-xl font-semibold")
            job_status = ui.label()
            if state.job_description:
                ui.label(state.job_description).classes("text-sm text-gray-400")

        with ui.card().classes("min-w-0"):
            ui.label("Shortcuts").classes("text-xl font-semibold")
            with ui.row():
                ui.button("Job Monitor", on_click=lambda: nav("Job"))
                ui.button("Scrape", on_click=lambda: nav("Scrape"))
                ui.button("Auth", on_click=lambda: nav("Auth"))

    def refresh_job():
        status = state.status.value.capitalize()
        suffix = f" — {state.job_result}" if state.job_result else ""
        error = f" (error: {state.job_error})" if state.job_error else ""
        job_status.text = f"Status: {status}{suffix}{error}"
        if state.auth_checking:
            login_label.text = "checking… (can take ~30s)"
        elif state.auth_ok is True:
            who = f" as {state.auth_username}" if state.auth_username else ""
            login_label.text = f"Logged in{who}"
        elif state.auth_ok is False:
            login_label.text = "Not logged in — open the Auth screen"
        else:
            login_label.text = "Login: unknown — press Check auth status"

    refresh_job()
    ui.timer(1.0, refresh_job)

    with ui.card().classes("w-full"):
        ui.label("Maintenance").classes("text-lg")
        ui.label(
            "Move already-downloaded files into the current folder layout "
            "(dir_format) instead of re-downloading — runs offline over "
            "every model database, and also happens automatically before "
            "each download."
        ).classes("text-sm text-gray-400")
        screens.run_button(
            ["restructure"], "Restructure downloaded files", label="Restructure files"
        )

    with ui.card().classes("w-full"):
        ui.label("Quick job (advanced)").classes("text-lg")
        ui.label(
            "Run any command exactly as you would in the terminal, minus the "
            "program name — e.g. -u ALL -da Timeline -a download"
        ).classes("text-sm text-gray-400")

        def quick_argv():
            text = quick_input.value or ""
            return shlex.split(text)

        quick_input = ui.input(
            placeholder="-u ALL -da Timeline -a download"
        ).classes("w-full")
        screens.run_button(quick_argv, "Quick job", label="Run quick job")
