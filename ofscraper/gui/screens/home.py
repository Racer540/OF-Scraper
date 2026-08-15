"""
Home screen: dashboard with auth status, profile, job state, and navigation.

Auth status is checked in a worker thread via `init.getstatus()` (the same
call checkers.py uses) so the UI never blocks on the network.
"""

import shlex
import threading

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
    try:
        import ofscraper.utils.auth.file as auth_file

        auth = auth_file.read_auth()
        if not auth:
            return "no auth.json"
        user = auth.get("username") or auth.get("auth_uid_") or "unknown user"
        return f"saved as {user}"
    except Exception as E:
        return f"auth.json error: {E}"


def _check_auth(status_label):
    def work():
        try:
            import ofscraper.data.api.init as init

            result = init.getstatus()
        except Exception as E:
            result = f"error: {E}"
        status_label.text = f"Auth status: {result}"

    threading.Thread(target=work, name="gui-auth-check", daemon=True).start()


@screens.register("Home")
def render(nav):
    state = get_state()

    with ui.row().classes("w-full items-center gap-4"):
        ui.label("OF-Scraper").classes("text-3xl font-bold")
        ui.badge(f"v{_version()}", color="blue")

    with ui.grid(columns=2).classes("w-full gap-4"):
        with ui.card().classes("min-w-0"):
            ui.label("Authentication").classes("text-xl font-semibold")
            status_label = ui.label("Auth status: unknown")
            ui.label(_auth_file_summary()).classes("text-sm text-gray-400")
            ui.button("Check auth status", on_click=lambda: _check_auth(status_label))

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

    refresh_job()
    ui.timer(1.0, refresh_job)

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
