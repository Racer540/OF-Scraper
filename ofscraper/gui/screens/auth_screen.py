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
            check_button = ui.button(
                "Check status", on_click=lambda: _check(status_label, check_button)
            )
        ui.separator()
        placeholders = {
            "sess": "short token from the sess cookie (auto-imported)",
            "auth_id": "numeric id (auto-imported)",
            "auth_uid": "0 for your own account",
            "user_agent": "from a Network-tab request header: Mozilla/5.0 (Windows NT 10.0; ...)",
            "x-bc": "40-char hex from the x-bc REQUEST HEADER (Network tab) — NOT a cookie",
        }
        for field in FIELDS:
            inputs[field] = ui.input(
                field,
                value=auth.get(field) or auth.get(f"{field}_") or "",
                placeholder=placeholders.get(field, field),
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
            "cookies, and derives user_agent from the browser version. "
            "Firefox: all profiles are scanned. Chrome/Edge: the browser "
            "must be closed for cookie decryption on Windows. x-bc is NOT "
            "stored in any cookie — use the one-shot paste below for that."
        ).classes("text-xs text-gray-400")

    with ui.card().classes("w-full"):
        ui.label("One-shot paste (captures x-bc too)").classes("text-lg font-semibold")
        paste_box = ui.textarea(
            "Paste anything here: the M-rcus OnlyFans-Cookie-Helper "
            "extension output, an UltimaScraper-style auth.json, a raw "
            "cookie header, or loose 'sess=...' text",
            placeholder='{"auth": {"cookie": "auth_id=...; sess=...", "x_bc": "...", "user_agent": "..."}}',
        ).classes("w-full font-mono")
        with ui.row().classes("w-full items-center"):
            paste_label = ui.label("").classes("text-sm text-gray-400")
            ui.space()
            ui.button(
                "Fill all fields from paste",
                color="primary",
                on_click=lambda: _fill_from_paste(paste_box, paste_label),
            )
        ui.label(
            "Recommended: install the 'OnlyFans Cookie-Helper' extension in "
            "your browser (by M-rcus), open onlyfans.com, click the "
            "extension, and copy everything it shows into the box above — "
            "it includes the x-bc and user-agent that no cookie import can "
            "recover."
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
            result = state.auth_import_result
            for field, value in result.items():
                if field in inputs:
                    inputs[field].set_value(value)
            import_label.set_text(state.auth_import_message)
            if result:
                ui.notify(state.auth_import_message, type="positive")
            else:
                ui.notify(state.auth_import_message, type="warning")
        if state.auth_status_version != last_status:
            last_status = state.auth_status_version
            status_label.set_text(state.auth_status_message)
            check_button.set_enabled(True)

    ui.timer(0.25, poll_import)


def _check(status_label, button):
    """Check auth against the API. getstatus() retries internally and can
    take 30+ seconds — set immediate feedback so the button never looks
    dead while that runs."""
    import time as _time

    from ofscraper.gui.state import get_state

    state = get_state()
    status_label.set_text("Auth status: checking… (can take ~30s)")
    button.set_enabled(False)
    started = _time.time()

    def work():
        try:
            import ofscraper.data.api.init as init

            result = init.getstatus()
        except Exception as E:
            result = f"error: {E}"
        elapsed = _time.time() - started
        if result == "UP":
            message = f"Auth status: UP ({elapsed:.0f}s) — you're logged in"
        else:
            message = (
                f"Auth status: {result} ({elapsed:.0f}s) — most often the "
                "x-bc header (must come from a Network-tab REQUEST header, "
                "not a cookie) or a user_agent mismatch with the browser "
                "the sess cookie came from"
            )
        state.auth_status_message = message
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


def _fill_from_paste(paste_box, paste_label):
    """Fill all five auth fields from one paste.

    Accepts (via auth_schema's own accessors, utils/auth/data.py):
    - Cookie-Helper extension JSON: {"auth": {"cookie": "...", "x_bc": ...}}
    - UltimaScraper-style auth.json (same shape)
    - flat {"sess": ..., "x-bc": ...} dicts
    - bare cookie headers: 'auth_id=...; sess=...'
    """
    import json as _json

    from ofscraper.gui.state import get_state

    text = (paste_box.value or "").strip()
    if not text:
        paste_label.set_text("nothing pasted yet")
        return

    source = None
    try:
        parsed = _json.loads(text)
        if isinstance(parsed, dict):
            source = parsed.get("auth") if isinstance(parsed.get("auth"), dict) else parsed
    except Exception:
        source = None

    if source is None:
        # bare cookie string ('a=b; c=d') — and maybe stray key=value lines
        pairs = _parse_cookie_header(text)
        source = pairs if pairs.get("sess") or pairs.get("auth_id") else None

    state = get_state()
    if source is None:
        paste_label.set_text(
            "could not parse the paste — expected JSON, or 'name=value; …' text"
        )
        ui.notify("Paste not recognized", type="warning")
        return

    try:
        import ofscraper.utils.auth.schema as auth_schema

        normalized = auth_schema.auth_schema(source)
    except Exception as E:
        paste_label.set_text(f"parse failed: {E}")
        ui.notify(f"Could not build auth from paste: {E}", type="negative")
        return

    filled = {
        k: v
        for k, v in normalized.items()
        if v and k in FIELDS
    }
    if not filled.get("sess"):
        paste_label.set_text("paste parsed, but no sess found in it")
        ui.notify("No sess in the pasted data", type="warning")
        return

    if filled.get("x-bc"):
        state.auth_fp_cookie = ""  # a real x-bc supersedes any fp note
    state.auth_import_result = filled
    state.auth_import_message = (
        f"filled {len(filled)} field(s) from paste"
        + (
            ""
            if filled.get("x-bc") and filled.get("user_agent")
            else " — some fields still missing (x-bc/user_agent)"
        )
    )
    state.auth_import_version += 1
    paste_label.set_text(state.auth_import_message)


def _firefox_user_agent() -> str:
    """Derive the canonical Firefox UA from the profile's compatibility.ini."""
    import configparser
    import os

    base = os.path.join(os.environ.get("APPDATA", ""), "Mozilla", "Firefox")
    parser = configparser.ConfigParser()
    parser.read(os.path.join(base, "profiles.ini"))
    for section in parser.sections():
        if not section.startswith("Profile"):
            continue
        path = parser.get(section, "path", fallback="")
        full = path if os.path.isabs(path) else os.path.join(base, path)
        compat = os.path.join(full, "compatibility.ini")
        if os.path.exists(compat):
            cp = configparser.ConfigParser()
            cp.read(compat)
            last = cp.get("Compatibility", "LastVersion", fallback="")
            # e.g. 153.0.3_20260803132010/... -> major.minor
            version = last.split("_")[0]
            parts = version.split(".")
            if len(parts) >= 2 and parts[0].isdigit():
                major = parts[0]
                return (
                    f"Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:{major}.0) "
                    f"Gecko/20100101 Firefox/{major}.0"
                )
    return ""


def _import_browser(browser_name, inputs, label):
    def work():
        try:
            cookies = _browser_cookies(browser_name)
            sess = cookies.get("sess", "")
            auth_id = cookies.get("auth_id", "")
            auth_uid = cookies.get("auth_uid_", "0")
            if sess and auth_id:
                result = {
                    "sess": sess,
                    "auth_id": auth_id,
                    "auth_uid": auth_uid,
                }
                message = (
                    "cookies imported — x-bc still needed: use one-shot "
                    "paste below (Cookie-Helper extension) or a Network-tab "
                    "request header"
                )
                from ofscraper.gui.state import get_state

                state = get_state()
                # remember the fp cookie so Save can catch the classic
                # fp-pasted-as-x-bc mistake
                state.auth_fp_cookie = cookies.get("fp", "")
                if browser_name.lower().startswith("firefox"):
                    ua = _firefox_user_agent()
                    if ua:
                        result["user_agent"] = ua
                        message += "; user_agent derived from your Firefox"
            elif cookies:
                result = {}
                message = (
                    "found onlyfans cookies but no sess/auth_id pair — log "
                    "into onlyfans.com in that browser (a normal window, not "
                    "private/container) and retry"
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


def _parse_cookie_header(raw: str) -> dict:
    """If someone pasted a full cookie header, split it into name/value pairs."""
    raw = raw or ""
    if "=" not in raw or ";" not in raw:
        return {}
    out = {}
    for part in raw.split(";"):
        if "=" in part:
            key, _, value = part.partition("=")
            key = key.strip()
            if key and key not in out:
                out[key] = value.strip()
    return out


def _save(inputs):
    auth = {field: _sanitize(inputs[field].value) for field in FIELDS}

    # tolerate pasted forms like "sess=abc..." or a whole cookie header
    pasted = _parse_cookie_header(auth.get("sess", ""))
    if pasted:
        for key in FIELDS + ("auth_uid_",):
            if pasted.get(key):
                auth[key] = pasted[key]
    if auth.get("sess", "").startswith("sess="):
        auth["sess"] = auth["sess"][len("sess="):]

    # keep the legacy alias some code paths look for
    auth["auth_uid_"] = auth["auth_uid"]

    missing = [
        f for f in ("sess", "auth_id", "user_agent", "x-bc") if not auth.get(f)
    ]
    if missing:
        ui.notify(f"Missing required fields: {', '.join(missing)}", type="negative")
        return

    from ofscraper.gui.state import get_state

    fp = get_state().auth_fp_cookie
    if fp and auth.get("x-bc") == fp:
        ui.notify(
            "That x-bc is the 'fp' COOKIE from your browser, not the x-bc "
            "request header — OnlyFans will reject it. Get the real value: "
            "F12 → Network tab → reload → click an onlyfans.com/api2/... "
            "request → Request Headers → x-bc",
            type="negative",
            multi_line=True,
        )
        return

    try:
        import ofscraper.utils.auth.schema as auth_schema
        import ofscraper.utils.paths.common as common_paths

        # Note: the CLI's make_auth ends with check_auth_warning(), a
        # terminal Yes/No ("Is the auth information correct?") after
        # printing reminders — in the GUI, pressing Save IS that
        # confirmation, and the reminders live in the field placeholders,
        # so we validate via schema normalization only.
        normalized = auth_schema.auth_schema(auth)
        auth_file = common_paths.get_auth_file()
        with open(auth_file, "w") as f:
            f.write(json.dumps(normalized, indent=4))
        ui.notify(
            f"Saved to {auth_file} — press 'Check status' to verify", type="positive"
        )
    except Exception as E:
        ui.notify(f"Save failed: {E}", type="negative")
