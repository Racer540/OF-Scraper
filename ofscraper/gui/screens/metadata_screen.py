"""
Metadata screen: DB maintenance without downloading.

Mirrors the CLI `metadata` command:
- -md check|update|complete  (required unless -sp is used)
- -ms  mark unmatched media as locked (stray)
- -an  anonymized credentials mode
- -sp check|update|complete  metadata pass over the paid page only
Areas come via -da (or -o posts), users via -u — both reuse the same
selection semantics as the Scrape screen.
"""

from nicegui import ui

import ofscraper.gui.screens as screens
from ofscraper.gui.state import get_state

METADATA_MODES = {"check": "check", "update": "update", "complete": "complete"}

# metadata's area prompt allows any non-label area
METADATA_AREAS = [
    "Timeline",
    "Archived",
    "Messages",
    "Pinned",
    "Highlights",
    "Stories",
    "Purchased",
    "Profile",
    "Streams",
    "all",
]


@screens.register("Metadata")
def render(nav):
    state = get_state()

    ui.label("Metadata / DB maintenance").classes("text-2xl font-bold")
    ui.label(
        "Update your local database from the API without downloading files — "
        "fix filenames, mark downloads complete, or lock stray media."
    ).classes("text-sm text-gray-400")

    with ui.card().classes("w-full"):
        ui.label("Mode").classes("text-lg font-semibold")
        with ui.row().classes("w-full items-center"):
            mode = ui.select(
                METADATA_MODES, label="Metadata mode (-md)", value="check"
            ).classes("w-48")
            scrape_paid = ui.select(
                {"": "off"} | METADATA_MODES,
                label="Paid-page pass (-sp)",
                value="",
            ).classes("w-48")
        with ui.row().classes("w-full items-center"):
            mark_stray = ui.checkbox(
                "Mark unmatched media as locked (-ms)", value=False
            )
            anon = ui.checkbox("Anonymized credentials (-an)", value=False)

    with ui.card().classes("w-full"):
        ui.label("Scope").classes("text-lg font-semibold")
        with ui.row().classes("w-full items-center"):
            picker_label = ui.label(
                ", ".join(state.selected_usernames)
                if state.selected_usernames
                else "all models (ALL)"
            ).classes("text-sm text-gray-400")
            ui.button("Pick models", on_click=lambda: nav("Models")).props("outline")
            manual_users = ui.input(
                "Usernames (overrides picker)", placeholder="name1,name2  or  ALL"
            ).classes("grow")
        areas = screens.check_group("Areas", METADATA_AREAS, default=["Timeline"])

    with ui.card().classes("w-full"):
        with ui.row().classes("w-full items-center"):
            extra = ui.input("Extra CLI args", placeholder="-af 2024-01-01").classes(
                "grow"
            )
            screens.run_button(
                lambda: _build_argv(
                    mode, scrape_paid, mark_stray, anon, manual_users, areas, extra
                ),
                "Metadata job",
                label="Run metadata",
            )
            ui.button("Job monitor", on_click=lambda: nav("Job")).props("outline")


def _build_argv(
    mode, scrape_paid, mark_stray, anon, manual_users, areas, extra
) -> list:
    argv = ["metadata"]
    if mode.value:
        argv += ["-md", mode.value]
    if scrape_paid.value:
        argv += ["-sp", scrape_paid.value]
    if mark_stray.value:
        # long form only: the '-ms' short flag is shadowed by the post-filter
        # mass-skip option in the metadata command's own arg bundle
        argv.append("--mark-stray")
    if anon.value:
        argv.append("-an")

    users = [u.strip() for u in (manual_users.value or "").split(",") if u.strip()]
    if not users:
        users = list(get_state().selected_usernames)
    if users:
        argv += ["-u", ",".join(users)]

    selected = areas()
    if selected:
        # the metadata subcommand exposes -o/--posts (not -da); it flows into
        # download_area through the posts accessors
        argv += ["-o", ",".join(selected)]

    argv += (extra.value or "").split()
    return argv
