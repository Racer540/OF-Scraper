"""
Shared background auth check: one worker, many consumers.

The header badge (app.py), the Home screen and the Auth screen all show the
login state; they all read the same GuiState fields written by this module's
worker thread.  Calls the same /users/me endpoint the CLI's init.getstatus()
uses, but keeps the response so the logged-in username is available —
auth.json never stores it, which is why the Home screen used to say
"unknown user".
"""

import threading
import time

from ofscraper.gui.state import get_state


def start_auth_check() -> bool:
    """Spawn an auth check if none is in flight.  Returns False if one is."""
    state = get_state()
    if state.auth_checking:
        return False
    state.auth_checking = True

    def work():
        started = time.time()
        username = ""
        ok = False
        try:
            import ofscraper.utils.settings as settings

            if settings.get_settings().anon:
                ok = True
            else:
                import ofscraper.data.api.me as me

                data = me.scrape_user()
                ok = bool(data.get("isAuth"))
                username = data.get("username") or ""
        except Exception:
            ok = False
        elapsed = time.time() - started

        message = (
            f"Auth status: UP ({elapsed:.0f}s) — logged in as {username}"
            if ok and username
            else f"Auth status: UP ({elapsed:.0f}s) — you're logged in"
            if ok
            else (
                f"Auth status: DOWN ({elapsed:.0f}s) — most often the "
                "x-bc header (must come from a Network-tab REQUEST header, "
                "not a cookie) or a user_agent mismatch with the browser "
                "the sess cookie came from"
            )
        )

        state.auth_ok = ok
        state.auth_username = username
        state.auth_checked_at = time.time()
        state.auth_checking = False
        state.auth_status_message = message
        state.auth_status_version += 1

    threading.Thread(target=work, name="gui-auth-check", daemon=True).start()
    return True
