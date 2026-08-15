"""
Manual screen: download specific posts by URL or ID list.

Mirrors the CLI `manual` command — either a comma/space-separated URL list
(-u/--url) or a file with one URL per line (-f/--file); at least one is
required (cloup url_group constraint, surfaced as a form error).
"""

from nicegui import ui

import ofscraper.gui.screens as screens


@screens.register("Manual")
def render(nav):
    ui.label("Manual Download").classes("text-2xl font-bold")
    ui.label(
        "Download specific posts by pasting their URLs or IDs — no area "
        "scanning involved."
    ).classes("text-sm text-gray-400")

    with ui.card().classes("w-full"):
        ui.label("URLs / IDs").classes("text-lg font-semibold")
        url_input = ui.textarea(
            "One URL or ID per line (or comma-separated)",
            placeholder="https://onlyfans.com/12345678\nhttps://onlyfans.com/87654321",
        ).classes("w-full min-h-[120px]")
        with ui.row().classes("w-full items-center"):
            url_file = ui.input(
                "…or a file with one URL per line (-f)",
                placeholder="D:\\path\\to\\urls.txt",
            ).classes("grow")

    with ui.card().classes("w-full"):
        with ui.row().classes("w-full items-center"):
            extra = ui.input("Extra CLI args", placeholder="-sd 2 -k manual").classes(
                "grow"
            )
            screens.run_button(
                lambda: _build_argv(url_input, url_file, extra),
                "Manual download",
                label="Run manual download",
            )
            ui.button("Job monitor", on_click=lambda: nav("Job")).props("outline")


def _build_argv(url_input, url_file, extra) -> list:
    argv = ["manual"]
    urls = [
        u.strip()
        for line in (url_input.value or "").splitlines()
        for u in line.split(",")
        if u.strip()
    ]
    if urls:
        argv += ["-u", ",".join(urls)]
    if (url_file.value or "").strip():
        argv += ["-f", url_file.value.strip()]
    argv += (extra.value or "").split()
    return argv
