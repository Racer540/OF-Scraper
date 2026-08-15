"""
Auth screen: edit auth.json without the terminal flow.

Reuses the prompt-free pieces of the CLI auth pipeline:
- auth_dict.get_auth_dict() / auth_schema.auth_schema() to read+normalize
- browser_cookie3.<browser>(domain_name='onlyfans') for cookie import
  (mirrors auth/utils/prompt.py:browser_cookie_helper, minus prompts)
- the same sanitize loop + check_auth_warning(auth) validation make_auth
  applies (utils/auth/make.py:45-57) before writing auth.json
- data/api/init.py:getstatus() for the live UP/DOWN check
"""

import json
import re
import threading

from nicegui import ui

import ofscraper.gui.screens as screens

FIELDS = ["sess", "auth_id", "auth_uid", "user_agent", "x-bc"]
BROWSERS = ["chrome", "chromium", "firefox", "edge", "brave", "opera", "safari"]


def _load_auth() -> dict:
    try:
        import ofscraper.utils.auth.utils.dict as auth_dict

        return auth_dict.get_auth_dict() or {}
    except Exception:
        return {}


def _sanitize(value: str) -> str:
    value = (value or "").strip()
    value = re.sub(r"^ +", "", value)
    value = re.sub(r" +$", "", value)
    return re.sub(r"\n+", "", value)


@screens.register("Auth")
def render(nav):
    auth = _load_auth()

    ui.label("Authentication").classes("text-2xl font-bold")
    ui.label(
        "Paste your OnlyFans credentials (sess cookie, auth ids, x-bc header, "
        "user-agent). Cookie fields can be imported straight from your "
        "browser; x-bc and user-agent always need manual paste."
    ).classes("text-sm text-gray-400")

    inputs = {}
    with ui.card().classes("w-full"):
        with ui.row().classes("w-full items-center"):
            status_label = ui.label("Auth status: unknown").classes("font-mono")
            ui.space()
            ui.button("Check status", on_click=lambda: _check(status_label))
        ui.separator()
        for field in FIELDS:
            placeholder = (
                "very long cookie string starting with %3D..."
                if field == "sess"
                else field
            )
            inputs[field] = ui.input(
                field, value=auth.get(field) or auth.get(f"{field}_") or ""
            ).classes("w-full")
            if field == "sess":
                inputs[field].props("type=password")
        ui.label(
            "auth_uid is usually 0 (your own account id when using your own login)"
        ).classes("text-xs text-gray-400")

    with ui.card().classes("w-full"):
        ui.label("Import cookies from browser").classes("text-lg font-semibold")
        with ui.row().classes("w-full items-center"):
            browser = ui.select({b: b.capitalize() for b in BROWSERS}, value="chrome").classes("w-40")
            import_label = ui.label("").classes("text-sm text-gray-400")
            ui.button(
                "Import",
                on_click=lambda: _import_browser(browser.value, inputs, import_label),
            )
        ui.label(
            "Fills sess / auth_id / auth_uid from your browser's onlyfans "
            "cookies. Your browser must be closed for cookie decryption on "
            "Windows (Chrome/Edge)."
        ).classes("text-xs text-gray-400")

    with ui.row().classes("w-full"):
        ui.button("Save auth", color="positive", on_click=lambda: _save(inputs))


def _check(status_label):
    def work():
        try:
            import ofscraper.data.api.init as init

            result = init.getstatus()
        except Exception as E:
            result = f"error: {E}"
        status_label.text = f"Auth status: {result}"

    threading.Thread(target=work, name="gui-auth-status", daemon=True).start()


def _import_browser(browser_name, inputs, label):
    def work():
        try:
            import browser_cookie3
            import requests

            jar = getattr(browser_cookie3, browser_name.lower())(
                domain_name="onlyfans"
            )
            cookies = requests.utils.dict_from_cookiejar(jar)
            sess = cookies.get("sess", "")
            auth_id = cookies.get("auth_id", "")
            auth_uid = cookies.get("auth_uid_", "0")
            filled = bool(sess and auth_id)
            # UI element updates must happen on the NiceGUI thread; use the
            # element's own set_text/set_value which push updates async-safe
            inputs["sess"].set_value(sess)
            inputs["auth_id"].set_value(auth_id)
            inputs["auth_uid"].set_value(auth_uid)
            label.set_text(
                "cookies imported — now paste x-bc and user_agent"
                if filled
                else "no onlyfans cookies found in that browser"
            )
        except Exception as E:
            label.set_text(f"import failed: {E}")

    threading.Thread(target=work, name="gui-cookie-import", daemon=True).start()


def _save(inputs):
    auth = {field: _sanitize(inputs[field].value) for field in FIELDS}
    # keep the legacy alias some code paths look for
    auth["auth_uid_"] = auth["auth_uid"]

    missing = [
        f for f in ("sess", "auth_id", "user_agent", "x-bc") if not auth.get(f)
    ]
    if missing:
        ui.notify(f"Missing required fields: {', '.join(missing)}", type="negative")
        return

    try:
        import ofscraper.utils.auth.schema as auth_schema
        import ofscraper.utils.auth.utils.warning.check as auth_check
        import ofscraper.utils.paths.common as common_paths

        normalized = auth_schema.auth_schema(auth)
        if not auth_check.check_auth_warning(normalized):
            ui.notify(
                "Auth validation failed — check the fields and try again",
                type="negative",
            )
            return
        auth_file = common_paths.get_auth_file()
        with open(auth_file, "w") as f:
            f.write(json.dumps(normalized, indent=4))
        ui.notify(f"Saved to {auth_file}", type="positive")
    except Exception as E:
        ui.notify(f"Save failed: {E}", type="negative")
