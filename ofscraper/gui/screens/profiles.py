"""
Profiles screen: create, rename, delete, and switch profiles.

Uses ProfileManager (managers/profile.py:18-70) for switch/rename/delete,
paths_manage.create_profile_path for creation, and profiles/data.py
accessors for listing. Switching permanent=True rewrites the config
default; session-only switches set args.profile for the running process.
"""

from nicegui import ui

import ofscraper.gui.screens as screens


def _profile_manager():
    import ofscraper.managers.manager as manager_module

    if not isinstance(manager_module.Manager, manager_module.mainManager):
        manager_module.Manager = manager_module.mainManager()
    return manager_module.Manager.profile_manager


def _names():
    import ofscraper.utils.profiles.data as profile_data

    try:
        return list(profile_data.get_profile_names() or [])
    except Exception:
        return []


def _active():
    import ofscraper.utils.profiles.data as profile_data

    try:
        return (
            profile_data.get_active_profile()
            or profile_data.get_current_config_profile()
            or "default"
        )
    except Exception:
        return "?"


@screens.register("Profiles")
def render(nav):
    ui.label("Profiles").classes("text-2xl font-bold")
    ui.label(
        "Profiles separate auth, config, databases and downloads — one per "
        "account or persona. Switching permanent rewrites the config default; "
        "session-only applies until the GUI closes."
    ).classes("text-sm text-gray-400")

    list_container = ui.column().classes("w-full gap-2")

    def refresh():
        active = _active()
        list_container.clear()
        with list_container:
            for name in sorted(_names(), key=str):
                with ui.row().classes("w-full items-center gap-2"):
                    badge = " (active)" if name == active else ""
                    ui.label(f"{name}{badge}").classes("font-mono")
                    if name != active:
                        ui.button(
                            "Switch (session)",
                            on_click=lambda n=name: _switch(n, False),
                        ).props("outline dense")
                        ui.button(
                            "Make default",
                            on_click=lambda n=name: _switch(n, True),
                        ).props("outline dense")
                    ui.button(
                        "Rename", on_click=lambda n=name: _rename(n)
                    ).props("outline dense")
                    if name != active:
                        ui.button(
                            "Delete",
                            color="negative",
                            on_click=lambda n=name: _delete(n),
                        ).props("outline dense")

    def _switch(name, permanent):
        try:
            _profile_manager().switch_profile(name, permanent=permanent)
            ui.notify(
                f"Switched to '{name}' ({'default' if permanent else 'session'})",
                type="positive",
            )
        except Exception as E:
            ui.notify(f"Switch failed: {E}", type="negative")
        refresh()

    def _rename(old):
        with ui.dialog() as dialog, ui.card():
            ui.label(f"Rename '{old}' to:").classes("text-lg")
            new_name = ui.input("new name")
            with ui.row():
                ui.button("Cancel", on_click=dialog.close).props("outline")
                ui.button(
                    "Rename",
                    on_click=lambda: _do_rename(old, new_name.value, dialog),
                )
        dialog.open()

    def _do_rename(old, new, dialog):
        dialog.close()
        if not (new or "").strip():
            ui.notify("Name required", type="warning")
            return
        try:
            _profile_manager().rename_profile(old, new.strip())
            ui.notify(f"Renamed to '{new.strip()}'", type="positive")
        except Exception as E:
            ui.notify(f"Rename failed: {E}", type="negative")
        refresh()

    def _delete(name):
        with ui.dialog() as dialog, ui.card():
            ui.label(
                f"Delete profile '{name}'? This removes its folder "
                "(auth, db, config overrides) and cannot be undone."
            ).classes("text-lg")
            with ui.row():
                ui.button("Cancel", on_click=dialog.close).props("outline")
                ui.button(
                    "Delete",
                    color="negative",
                    on_click=lambda: _do_delete(name, dialog),
                )
        dialog.open()

    def _do_delete(name, dialog):
        dialog.close()
        try:
            _profile_manager().delete_profile(name)
            ui.notify(f"Deleted '{name}'", type="positive")
        except Exception as E:
            ui.notify(f"Delete failed: {E}", type="negative")
        refresh()

    with ui.card().classes("w-full"):
        ui.label("Create profile").classes("text-lg font-semibold")
        with ui.row().classes("w-full items-center gap-2"):
            new_profile = ui.input("profile name").classes("grow")

            def _create():
                name = (new_profile.value or "").strip()
                if not name:
                    ui.notify("Name required", type="warning")
                    return
                try:
                    import ofscraper.utils.paths.manage as paths_manage

                    paths_manage.create_profile_path(name)
                    ui.notify(f"Created '{name}'", type="positive")
                    new_profile.value = ""
                except Exception as E:
                    ui.notify(f"Create failed: {E}", type="negative")
                refresh()

            ui.button("Create", color="positive", on_click=_create)

    refresh()
