"""
Config screen: config.json editor.

Two views over the same file:
- Settings: the config's sections as collapsible groups, one typed control
  per key (switch for booleans, number inputs, text/JSON fields), each with
  a plain-language description.  Every key currently in the file is shown,
  including ones outside the standard schema.
- Raw JSON: the whole file as text, for keys this UI doesn't model and for
  add/remove surgery.

Saves go through config file write_config (utils/config/file.py:50) and are
followed by settings.update_settings() so the running GUI picks them up.
The on-disk structure ({config: {...}} wrapper or flat) is preserved.
"""

import json

from nicegui import ui

import ofscraper.gui.screens as screens

# Section key -> (human title, one-line summary)
SECTION_TITLES = {
    "file_options": ("Files & folders", "Where downloads land and how they're named"),
    "download_options": ("Downloads", "What gets downloaded and when to stop"),
    "binary_options": ("Binaries", "External programs (ffmpeg)"),
    "cdm_options": ("DRM / CDM", "Keys for protected (mpd) video"),
    "performance_options": ("Performance", "Parallelism and rate limits"),
    "content_filter_options": ("Content filters", "Skip media by size, length or type"),
    "advanced_options": ("Advanced", "Caching, logs, lists and other internals"),
    "script_options": ("Scripts", "Run your own scripts at specific points"),
    "responsetype": ("Folder names", "Subfolder name used for each area"),
}

# Top-level scalar keys rendered in the General group, with descriptions.
GENERAL_KEYS = {
    "main_profile": "Profile folder (under the config dir) holding auth and databases",
    "metadata": "Folder pattern for each model's database, e.g. .data/{model_id}",
    "discord": "Discord log level for update notifications (Off/Low/Normal/High)",
}

# key -> plain-language help (mirrors the CLI prompts where one exists)
DESCRIPTIONS = {
    # file_options
    "save_location": "Root folder for all downloads",
    "dir_format": "Folder pattern per model, e.g. {username}/{responsetype}",
    "file_format": "File name pattern, e.g. {filename}.{ext}",
    "textlength": "Max characters of post text saved (0 = unlimited)",
    "space_replacer": "Character that replaces spaces in names",
    "space-replacer": "Character that replaces spaces in names",
    "date": "Date format used in names (arrow/strftime, e.g. %Y-%m-%d)",
    "text_type_default": "File extension for saved post text (e.g. .txt)",
    "truncation_default": "Shorten very long generated names",
    # download_options
    "filter": "Media types to download: Videos, Audios, Images (JSON list)",
    "auto_resume": "Resume partial (.part) downloads instead of restarting",
    "system_free_min": "Pause when free disk space drops below this "
    "(bytes, or human like 10mb; 0 = off)",
    "max_post_count": "Max posts processed per model per run (0 = no limit)",
    "verify_all_integrity": "Check every downloaded video with ffprobe (slower)",
    # binary_options
    "ffmpeg": "Path to ffmpeg (ffprobe is looked up next to it)",
    # cdm_options
    "private-key": "Path to your Widevine device file (.wvd) or private key "
    "file — .wvd is enough by itself (DRM content)",
    "client-id": "CDM client id file — only needed for the split private-key "
    "style (skip it when using a .wvd)",
    "key-mode-default": "How DRM keys are obtained: 'cdrm' (public API "
    "service, down sometimes) or 'manual' (your own device file, "
    "self-contained)",
    # performance_options
    "download_sems": "Concurrent downloads per model",
    "download_limit": "Global download speed cap in bytes (0 = unlimited)",
    # content_filter_options
    "block_ads": "Skip media detected as ads",
    "file_size_max": "Skip files bigger than this (bytes or 10mb; 0 = off)",
    "file_size_min": "Skip files smaller than this (bytes or 10mb; 0 = off)",
    "length_max": "Skip videos longer than this many seconds (0 = off)",
    "length_min": "Skip videos shorter than this many seconds (0 = off)",
    # advanced_options
    "dynamic-mode-default": "How the request signatures refresh (a/headers)",
    "skip_unavailable_content": "Skip wall/story scans for expired "
    "subscriptions — set to No to still try stories of recently expired subs",
    "restructure_downloads": "When the folder layout (dir_format) changes, "
    "move already-downloaded files into the new structure instead of "
    "re-downloading (runs before each download; also on Home)",
    "models_refresh_interval": "Hours before the saved model list "
    "auto-refreshes in the GUI (0 = manual refresh only)",
    "downloadbars": "Show per-file progress bars while downloading",
    "cache-mode": "API response cache: sqlite, json, disabled or api_disabled",
    "rotate_logs": "Start a fresh log file each day",
    "sanitize_text": "Strip control characters from saved post text",
    "temp_dir": "Folder for in-progress downloads",
    "remove_hash_match": "Skip a download when its hash matches a file "
    "you already have (prevents renamed duplicates)",
    "infinite_loop_action_mode": "Behavior when a scrape gets stuck in a loop",
    "incremental_downloads": "Only download media missing from the database",
    "default_user_list": "List selected by default (e.g. ofscraper.active)",
    "default_black_list": "Usernames always excluded from runs (JSON list)",
    "logs_expire_time": "Days before old logs are deleted",
    "ssl_verify": "Verify SSL certificates (off only for debugging)",
    "env_files": "Extra .env files to load (JSON list of paths)",
    # script_options
    "after_action_script": "Runs once after the whole action finishes",
    "post_script": "Runs after each post is processed",
    "naming_script": "Overrides how files are named (prints the name)",
    "after_download_script": "Runs after each file downloads",
    "skip_download_script": "Prints 'True' to skip a specific download",
    # responsetype
    "timeline": "Subfolder name for timeline posts",
    "message": "Subfolder name for messages",
    "archived": "Subfolder name for archived posts",
    "paid": "Subfolder name for purchased posts",
    "stories": "Subfolder name for stories",
    "highlights": "Subfolder name for highlights",
    "profile": "Subfolder name for the profile avatar/cover",
    "pinned": "Subfolder name for pinned posts",
    "streams": "Subfolder name for streams",
}


def _open_full() -> dict:
    import ofscraper.utils.config.file as config_file

    return config_file.open_config() or {}


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


def _description(key: str) -> str:
    return DESCRIPTIONS.get(key) or GENERAL_KEYS.get(key, "")


def _parse_json_or_raise(raw: str, key: str):
    try:
        return json.loads(raw)
    except Exception as E:
        raise ValueError(f"{key}: invalid JSON — {E}")


def _add_control(key: str, value, registry: list) -> None:
    """Render one typed control for a leaf value; register its getter.

    registry collects (key, getter) so save can pull every value without
    knowing widget types.  Getters may raise ValueError (bad JSON) which
    save catches and shows as a notification.
    """
    with ui.row().classes("w-full items-center gap-2"):
        with ui.element("div").classes("w-72 shrink-0"):
            ui.label(key).classes("font-mono text-sm font-semibold")
            desc = _description(key)
            if desc:
                ui.label(desc).classes("text-xs text-gray-400")
        if isinstance(value, bool):
            switch = ui.switch("", value=value)
            registry.append((key, lambda s=switch: s.value))
        elif isinstance(value, (int, float)):
            number = ui.number(
                "", value=value, step=(1 if isinstance(value, int) else 0.1)
            ).classes("grow")
            cast = int if isinstance(value, int) else float
            registry.append(
                (
                    key,
                    lambda n=number, c=cast: c(n.value) if n.value is not None else None,
                )
            )
        elif isinstance(value, (list, dict)):
            area = ui.textarea(value=json.dumps(value)).classes(
                "grow font-mono"
            ).props("autogrow")
            registry.append(
                (key, lambda a=area: _parse_json_or_raise(a.value or "", key))
            )
        else:
            field = ui.input(
                "", value="" if value is None else str(value)
            ).classes("grow")
            registry.append((key, lambda f=field: f.value or ""))


def _section_groups(config: dict) -> list:
    """Ordered [(section_key_or_None, title, summary, keys)] to render.

    section_key None = General (top-level scalar keys edited in place).
    """
    groups = []
    general = [k for k in GENERAL_KEYS if k in config]
    other_general = [
        k
        for k, v in config.items()
        if not isinstance(v, (dict, list)) and k not in GENERAL_KEYS
    ]
    if general or other_general:
        groups.append(
            (
                None,
                "General",
                "Profile, database location and notification level",
                general + other_general,
            )
        )
    for section_key, (title, summary) in SECTION_TITLES.items():
        if isinstance(config.get(section_key), dict):
            groups.append((section_key, title, summary, list(config[section_key])))
    for key, value in config.items():
        if isinstance(value, dict) and key not in SECTION_TITLES:
            groups.append((key, key, "Custom section", list(value)))
    return groups


@screens.register("Config")
def render(nav):
    ui.label("Configuration").classes("text-2xl font-bold")
    ui.label(
        "Edits config.json. Settings groups every option with a plain "
        "description; Raw JSON shows the whole file for anything else."
    ).classes("text-sm text-gray-400")

    with ui.tabs() as tabs:
        settings_tab = ui.tab("Settings")
        raw_tab = ui.tab("Raw JSON")

    # (section_key_or_None, registry) per rendered group; rebuilt by rebuild()
    group_registries = []
    raw_widget = {}

    with ui.tab_panels(tabs, value=settings_tab).classes("w-full"):
        # ------------------------------------------------------- Settings
        with ui.tab_panel(settings_tab):
            search = (
                ui.input(placeholder="Search settings…")
                .classes("w-full")
                .props("clearable")
            )
            panels = ui.column().classes("w-full gap-2")

            def rebuild():
                config = _open_full()
                group_registries.clear()
                panels.clear()
                needle = (search.value or "").strip().lower()
                with panels:
                    for section_key, title, summary, keys in _section_groups(config):
                        if needle:
                            keys = [
                                k
                                for k in keys
                                if needle in k.lower()
                                or needle in _description(k).lower()
                                or needle in title.lower()
                            ]
                            if not keys:
                                continue
                        registry = []
                        group_registries.append((section_key, registry))
                        expansion = ui.expansion(
                            f"{title} ({len(keys)})", icon="settings"
                        ).classes("w-full")
                        if needle:
                            expansion.props("default-opened")
                        with expansion:
                            ui.label(summary).classes("text-xs text-gray-400")
                            if section_key is None:
                                for key in keys:
                                    _add_control(key, config[key], registry)
                            else:
                                section = config[section_key]
                                for key in keys:
                                    _add_control(key, section[key], registry)

            def save_settings():
                config = _open_full()
                for section_key, registry in group_registries:
                    target = config if section_key is None else config.get(section_key)
                    if not isinstance(target, dict):
                        continue
                    for key, getter in registry:
                        try:
                            target[key] = getter()
                        except ValueError as E:
                            ui.notify(str(E), type="negative")
                            return
                _write(config)
                rebuild()

            search.on("valuechanged", lambda: rebuild())
            rebuild()

            with ui.row().classes("w-full"):
                ui.button("Save changes", color="positive", on_click=save_settings)
                ui.button("Reload from disk", on_click=rebuild).props("outline")

        # ------------------------------------------------------- Raw JSON
        with ui.tab_panel(raw_tab):
            ui.label(
                "Edit the whole file as JSON — validates before saving. "
                "Use this to add or remove keys."
            ).classes("text-sm text-gray-400")
            raw = (
                ui.textarea(value=_raw_text())
                .classes("w-full font-mono")
                .props("autogrow")
            )
            raw_widget["area"] = raw

            def save_raw():
                try:
                    parsed = json.loads(raw.value or "{}")
                except Exception as E:
                    ui.notify(f"Invalid JSON: {E}", type="negative")
                    return
                _write(parsed)
                raw.value = _raw_text()
                rebuild()

            def reload_raw():
                raw.value = _raw_text()

            with ui.row():
                ui.button("Validate & save JSON", color="positive", on_click=save_raw)
                ui.button("Reload JSON", on_click=reload_raw).props("outline")
