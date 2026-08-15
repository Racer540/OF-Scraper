"""
Screen registry for the GUI.

Each screen is a module exposing `render(nav)` that builds its UI inside the
current content container.  `nav(name)` switches screens.  Screens that are
still under construction render a placeholder so navigation is complete from
day one.
"""

from nicegui import ui

from ofscraper.gui.runner import runner
from ofscraper.gui.state import JobStatus, get_state

# name -> render callable, filled by register() calls at import time below
SCREENS = {}


def register(name):
    def decorator(fn):
        SCREENS[name] = fn
        return fn

    return decorator


def placeholder(title: str):
    @register(title)
    def render(nav):
        ui.label(f"{title} screen — under construction").classes(
            "text-lg text-gray-400"
        )


# --- built screens ---------------------------------------------------------
from ofscraper.gui.screens import home  # noqa: E402,F401
from ofscraper.gui.screens import job  # noqa: E402,F401
from ofscraper.gui.screens import manual  # noqa: E402,F401
from ofscraper.gui.screens import metadata_screen  # noqa: E402,F401
from ofscraper.gui.screens import model_picker  # noqa: E402,F401
from ofscraper.gui.screens import scrape  # noqa: E402,F401


# --- placeholders (replaced as phases land) --------------------------------
placeholder("Checks")
placeholder("DB Viewer")
placeholder("Merge")
placeholder("Auth")
placeholder("Config")
placeholder("Profiles")


def check_group(label: str, options: list, default: list | None = None):
    """Render a labeled checkbox group; return a callable for selected values.

    NiceGUI 3 has no checkbox_group widget, so this composes plain checkboxes.
    """
    with ui.element("div").classes("grow"):
        ui.label(label).classes("text-sm font-semibold")
        boxes = {}
        with ui.row().classes("wrap gap-2"):
            for opt in options:
                boxes[opt] = ui.checkbox(opt, value=opt in (default or []))
    return lambda: [opt for opt, box in boxes.items() if box.value]


def run_button(argv, description: str, label: str = "Run"):
    """Run button that respects the single-job lock and reports refusals.

    `argv` may be a list or a zero-arg callable returning the list (so forms
    can assemble their argv at click time).
    """

    def start():
        resolved = argv() if callable(argv) else argv
        if not resolved:
            ui.notify("Nothing to run — fill in the form first", type="warning")
            return
        if not runner.start(resolved, description):
            ui.notify(
                "A job is already running — wait for it to finish", type="warning"
            )

    return ui.button(label, on_click=start)
