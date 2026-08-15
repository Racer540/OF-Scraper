"""
Config screen: config.json editor.

Two views over the same file:
- Key/value editor: every current key with an editable value (parsed as
  JSON when possible, so booleans/numbers/lists survive), plus add/remove
  keys. This covers the full config surface without a hundred bespoke
  widgets.
- Raw JSON editor for power use.

Saves go through config file write_config (utils/config/file.py:50) and are
followed by settings.update_settings() so the running GUI picks them up.
The on-disk structure ({config: {...}} wrapper or flat) is preserved.
"""

import json

from nicegui import ui

import ofscraper.gui.screens as screens


def _open_full() -> dict:
    import ofscraper.utils.config.file as config_file

    return config_file.open_config() or {}


def _inner(config: dict) -> dict:
    return config.get("config") if isinstance(config.get("config"), dict) else config


def _parse_value(raw: str):
    try:
        return json.loads(raw)
    except Exception:
        return raw


def _stringify(value) -> str:
    return value if isinstance(value, str) else json.dumps(value)


def _raw_text() -> str:
    import ofscraper.utils.config.file as config_file

    try:
        return config_file.config_string() or "{}"
    except Exception:
        return "{}"


def _write(full: dict) -> None:
    import ofscraper.utils.config.file as config_file
    import ofscraper.utils.settings as settings

    config_file.write_config(full)
    settings.update_settings()
    ui.notify("config.json saved", type="positive")


@screens.register("Config")
def render(nav):
    ui.label("Configuration").classes("text-2xl font-bold")
    ui.label(
        "Edits config.json — every key is editable. Values are parsed as "
        "JSON when possible (true/false, numbers, lists); anything else is "
        "saved as a string."
    ).classes("text-sm text-gray-400")

    inputs_registry = {}
    rows_container = ui.column().classes("w-full gap-2")

    def save_registry_changes():
        full = _open_full()
        inner = _inner(full)
        for key, element in inputs_registry.items():
            inner[key] = _parse_value(element.value)
        _write(full)
        refresh_rows()

    def delete_key(key):
        full = _open_full()
        _inner(full).pop(key, None)
        _write(full)
        refresh_rows()

    def add_key(new_key, new_value):
        key = (new_key.value or "").strip()
        if not key:
            ui.notify("Key name required", type="warning")
            return
        full = _open_full()
        _inner(full)[key] = _parse_value(new_value.value or "")
        _write(full)
        refresh_rows()

    def refresh_rows():
        inputs_registry.clear()
        rows_container.clear()
        inner = _inner(_open_full())
        with rows_container:
            for key in sorted(inner.keys(), key=str):
                with ui.row().classes("w-full items-center gap-2"):
                    ui.label(str(key)).classes("w-64 font-mono text-sm shrink-0")
                    value_input = ui.input("", value=_stringify(inner[key])).classes(
                        "grow"
                    )
                    inputs_registry[str(key)] = value_input
                    ui.button(
                        icon="delete", on_click=lambda k=key: delete_key(k)
                    ).props("flat dense")
            with ui.row().classes("w-full items-center gap-2"):
                new_key = ui.input("new key").classes("w-64")
                new_value = ui.input("new value").classes("grow")
                ui.button("Add", on_click=lambda: add_key(new_key, new_value)).props(
                    "outline"
                )

    with ui.card().classes("w-full"):
        refresh_rows()
        with ui.row().classes("w-full"):
            ui.button("Save key/value edits", color="positive", on_click=save_registry_changes)
            ui.button("Reload from disk", on_click=refresh_rows).props("outline")

    with ui.card().classes("w-full"):
        ui.label("Raw JSON").classes("text-lg font-semibold")
        raw = ui.textarea(value=_raw_text()).classes("w-full font-mono")

        def save_raw():
            try:
                parsed = json.loads(raw.value or "{}")
            except Exception as E:
                ui.notify(f"Invalid JSON: {E}", type="negative")
                return
            _write(parsed)
            raw.value = _raw_text()
            refresh_rows()

        def reload_raw():
            raw.value = _raw_text()

        with ui.row():
            ui.button("Validate & save JSON", color="positive", on_click=save_raw)
            ui.button("Reload JSON", on_click=reload_raw).props("outline")
