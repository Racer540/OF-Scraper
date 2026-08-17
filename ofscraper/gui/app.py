"""
GUI entry point.

Bootstrap order matters and mirrors ofscraper/main/open/load.py:main() with
one critical difference: args are built from an EMPTY argv (not sys.argv) and
installed into the global args store BEFORE anything calls
`settings.get_settings()`.  `retriveArgs()` lazily parses the real sys.argv
(ofscraper/utils/args/accessors/read.py:8-14), which in a GUI process would
contain '--gui' and crash the parser.  Installing args first short-circuits
that lazy parse for the life of the process; every job afterwards goes through
argbuild.build_job.

`Manager.start()` is intentionally bypassed (it sleeps 3 s and calls
exit_manager.shutdown()); jobs go through gui.runner instead.
"""

import multiprocessing
import sys


def _sanitize_argv():
    """Strip GUI flags so any later parse of sys.argv stays valid."""
    for flag in ("--gui", "-g"):
        while flag in sys.argv[1:]:
            sys.argv.remove(flag)


def _bootstrap():
    import logging

    import ofscraper.main.open.load as load
    import ofscraper.utils.logs.logger as logger
    import ofscraper.utils.settings as settings

    from ofscraper.gui import argbuild

    log = logging.getLogger("shared")

    load.systemSet()
    # Install default args (empty argv -> program defaults) before anything
    # can lazily parse the real sys.argv.
    argbuild.build_job([])
    load.setdate()
    load.readConfig()
    settings.update_settings()  # re-merge now that config.json is loaded
    load.setLogger()
    load.make_folder()

    # The manager global the runner (and job code) expects.
    import ofscraper.managers.manager as manager_module

    if not isinstance(manager_module.Manager, manager_module.mainManager):
        manager_module.Manager = manager_module.mainManager()

    # Wire the log bridge onto the TextHandler seam.
    from ofscraper.gui.state import get_state

    logger.add_widget(get_state().log_buffer)
    log.info("GUI bootstrap complete")

    # One auth check at startup so the header badge reflects the login
    # without waiting for a manual check on the Home/Auth screen.  Skipped
    # under pytest (tests import this bootstrap via their fixture and must
    # not fire live requests).
    import sys as _sys

    if "pytest" not in _sys.modules:
        from ofscraper.gui.authstatus import start_auth_check

        start_auth_check()


def _fast_shutdown():
    """Close executor/cache without exit_manager.shutdown()'s 3 s sleep."""
    try:
        import ofscraper.main.close.exit as exit_manager

        exit_manager.closeThreadExecutor()
        exit_manager.closeCache()
    except Exception:
        pass


def _build_header():
    """Header: title, live Overall/Downloads progress bars, status badge.

    The bars are compact mirrors of the Job screen's 'Overall' and
    'Downloads (total)' bars (same progress bridge), so progress is visible
    from every tab while a job runs; the whole block hides when idle.
    Returns the status badge element (refreshed by the caller's timer).
    """
    from nicegui import ui

    from ofscraper.gui.bridges import progress as progress_bridge

    with ui.header().classes("items-center gap-4"):
        ui.label("OF-Scraper").classes("text-xl font-bold")
        header_progress = ui.column().classes("grow max-w-[480px] gap-1")

        def _header_bar(label: str, task) -> None:
            with ui.row().classes("w-full items-center gap-2"):
                ui.label(label).classes("text-xs w-20 shrink-0 text-gray-700")
                ui.linear_progress(task.fraction, show_value=False).classes("grow")
                count = (
                    f"{int(task.completed)}/{int(task.total)}" if task.total else "…"
                )
                ui.label(count).classes(
                    "text-xs w-14 shrink-0 text-right font-mono text-gray-700"
                )

        def refresh_header_progress():
            header_progress.clear()
            snap = progress_bridge.snapshot()

            def first_visible(tasks):
                return next((t for t in tasks if t.visible), None)

            overall = first_visible(snap["activity_counter"])
            downloads = first_visible(snap["download"]["overall"])
            header_progress.set_visibility(bool(overall or downloads))
            with header_progress:
                if overall:
                    _header_bar("Overall", overall)
                if downloads:
                    _header_bar("Downloads", downloads)

        refresh_header_progress()
        ui.timer(0.5, refresh_header_progress)
        return ui.badge("idle").classes("text-xs")


def _build_ui():
    from nicegui import ui

    import ofscraper.gui.screens as screens

    @ui.page("/")
    def index():
        ui.dark_mode().enable()

        def navigate(name: str):
            content.clear()
            with content:
                try:
                    screens.SCREENS[name](navigate)
                except Exception as E:
                    ui.label(f"Screen error: {E}").classes("text-red-500")

        status_badge = _build_header()
        with ui.left_drawer().classes("gap-2 p-4"):
            for name in screens.SCREENS:
                ui.button(
                    name,
                    on_click=lambda n=name: navigate(n),
                ).classes("w-full")
        content = ui.column().classes("w-full max-w-[1100px] mx-auto gap-4 p-4")

        def refresh_badge():
            from ofscraper.gui.state import get_state

            state = get_state()
            if state.job_running:
                status_badge.text = state.status.value
                status_badge._props["color"] = (
                    "orange" if state.status.value == "cancelling" else "green"
                )
            elif state.auth_checking:
                status_badge.text = "checking auth…"
                status_badge._props["color"] = "grey"
            elif state.auth_ok is True:
                status_badge.text = (
                    f"authed as {state.auth_username}"
                    if state.auth_username
                    else "authed"
                )
                status_badge._props["color"] = "green"
            elif state.auth_ok is False:
                status_badge.text = "not authed"
                status_badge._props["color"] = "red"
            else:
                status_badge.text = "idle"
                status_badge._props["color"] = "grey"
            status_badge.update()

        ui.timer(1.0, refresh_badge)
        navigate("Home")


def main():
    multiprocessing.freeze_support()
    _sanitize_argv()

    import ofscraper.gui.patches as patches

    patches.install()

    try:
        _bootstrap()
    except Exception as E:
        # Fatal bootstrap problems must still show the user something.
        import traceback

        print(f"GUI bootstrap failed: {E}\n{traceback.format_exc()}")

    import atexit

    atexit.register(_fast_shutdown)

    from nicegui import ui

    _build_ui()
    ui.run(
        native=True,
        title="OF-Scraper",
        window_size=(1280, 800),
        reload=False,
        show=False,
        port=0,
    )


if __name__ == "__main__":
    main()
