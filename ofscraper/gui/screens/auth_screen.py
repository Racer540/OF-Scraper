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
            browser = ui.select({b: b.capitalize() for b in BROWSERS}, value="firefox").classes("w-40")
            import_label = ui.label("").classes("text-sm text-gray-400")
            ui.button(
                "Import",
                on_click=lambda: _import_browser(browser.value, inputs, import_label),
            )
        ui.label(
            "Fills sess / auth_id / auth_uid from your browser's onlyfans "
            "cookies. Firefox: all profiles are scanned. Chrome/Edge: the "
            "browser must be closed for cookie decryption on Windows."
        ).classes("text-xs text-gray-400")

    with ui.row().classes("w-full"):
        ui.button("Save auth", color="positive", on_click=lambda: _save(inputs))

    # apply worker-thread import results on the UI thread
    from ofscraper.gui.state import get_state

    state = get_state()
    last_applied = state.auth_import_version
    last_status = state.auth_status_version

    def poll_import():
        nonlocal last_applied, last_status
        if state.auth_import_version != last_applied:
            last_applied = state.auth_import_version
            for field, value in state.auth_import_result.items():
                if field in inputs:
                    inputs[field].set_value(value)
            import_label.set_text(state.auth_import_message)
            if state.auth_import_result:
                ui.notify(state.auth_import_message, type="positive")
            else:
                ui.notify(state.auth_import_message, type="warning")
        if state.auth_status_version != last_status:
            last_status = state.auth_status_version
            status_label.set_text(state.auth_status_message)

    ui.timer(0.25, poll_import)


def _check(status_label):
    def work():
        from ofscraper.gui.state import get_state

        try:
            import ofscraper.data.api.init as init

            result = init.getstatus()
        except Exception as E:
            result = f"error: {E}"
        state = get_state()
        state.auth_status_message = f"Auth status: {result}"
        state.auth_status_version += 1

    threading.Thread(target=work, name="gui-auth-status", daemon=True).start()


def _read_firefox_cookie_db(db_path: str, domain: str = "onlyfans") -> dict:
    """Read one Firefox profile's cookies.sqlite (copied to temp to dodge locks)."""
    import os
    import shutil
    import sqlite3
    import tempfile

    tmp = os.path.join(tempfile.gettempdir(), f"ofscraper_gui_{os.getpid()}_cookies.sqlite")
    shutil.copy2(db_path, tmp)
    wal = db_path + "-wal"
    if os.path.exists(wal):
        shutil.copy2(wal, tmp + "-wal")
    cookies = {}
    try:
        con = sqlite3.connect(tmp)
        try:
            rows = con.execute(
                "SELECT name, value, host FROM moz_cookies WHERE host LIKE ?",
                (f"%{domain}%",),
            ).fetchall()
        finally:
            con.close()
        for name, value, host in rows:
            # host-only cookies win over dot-domain duplicates
            if name not in cookies or (host or "").startswith(domain):
                cookies[name] = value or ""
    finally:
        for path in (tmp, tmp + "-wal", tmp + "-shm"):
            try:
                os.remove(path)
            except OSError:
                pass
    return cookies


def _firefox_cookies() -> dict:
    """Collect onlyfans cookies from EVERY Firefox profile.

    browser_cookie3.firefox() trusts the profile flagged Default=1 in
    profiles.ini, which is routinely stale on Windows (the Install section
    names a different, newer profile) — so it reads a dead profile and finds
    no login. Scanning all profiles and preferring any that carry a `sess`
    cookie fixes that.
    """
    import configparser
    import os

    base = os.path.join(os.environ.get("APPDATA", ""), "Mozilla", "Firefox")
    ini = os.path.join(base, "profiles.ini")
    dbs = []
    if os.path.exists(ini):
        parser = configparser.ConfigParser()
        parser.read(ini)
        for section in parser.sections():
            if not section.startswith("Profile"):
                continue
            path = parser.get(section, "path", fallback="")
            if not path:
                continue
            full = path if os.path.isabs(path) else os.path.join(base, path)
            db = os.path.join(full, "cookies.sqlite")
            if os.path.exists(db):
                dbs.append(db)
    if not dbs:
        raise RuntimeError(
            "no Firefox cookie databases found — is Firefox installed?"
        )

    merged = {}
    logged_in = {}
    for db in dbs:
        cookies = _read_firefox_cookie_db(db)
        merged.update(cookies)
        if cookies.get("sess"):
            logged_in.update(cookies)
    return logged_in or merged


def _browser_cookies(browser_name: str) -> dict:
    if browser_name.lower() in {"firefox", "firefox-esr"}:
        return _firefox_cookies()
    import browser_cookie3

    jar = getattr(browser_cookie3, browser_name.lower())(domain_name="onlyfans")
    return {cookie.name: cookie.value or "" for cookie in jar}


def _looks_logged_in(sess: str) -> bool:
    """A logged-in OF sess is URL-encoded JSON (%7B%22auth_id...) and long;
    anonymous visits leave a short random marker instead."""
    return bool(sess) and (sess.startswith("%7B") or len(sess) > 100)


def _import_browser(browser_name, inputs, label):
    def work():
        try:
            cookies = _browser_cookies(browser_name)
            sess = cookies.get("sess", "")
            auth_id = cookies.get("auth_id", "")
            auth_uid = cookies.get("auth_uid_", "0")
            if _looks_logged_in(sess) and auth_id:
                result = {
                    "sess": sess,
                    "auth_id": auth_id,
                    "auth_uid": auth_uid,
                }
                message = "cookies imported — now paste x-bc and user_agent"
            elif cookies:
                result = {}
                message = (
                    "onlyfans.com cookies were found, but there is no active "
                    "login session — log into onlyfans.com in that browser "
                    "(a normal window, not private/container) and retry"
                )
            else:
                result = {}
                message = "no onlyfans cookies found in that browser"
        except Exception as E:
            result = {}
            message = f"import failed: {type(E).__name__}: {E}"
        # hand off to the UI thread via the state poll below — direct element
        # updates from a worker can die silently and swallow the error
        from ofscraper.gui.state import get_state

        state = get_state()
        state.auth_import_result = result
        state.auth_import_message = message
        state.auth_import_version += 1

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
