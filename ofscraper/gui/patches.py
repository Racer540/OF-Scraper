"""
GUI-mode monkeypatches.

The GUI runs OF-Scraper's job pipeline in a worker thread with no terminal.
Two kinds of console-only behavior must be diverted:

1. Interactive prompts (InquirerPy) -- would block a worker thread forever.
   The GUI always passes a complete argument set so prompts are skipped by
   design (see ofscraper/utils/actions.py: prompts only fire when the
   corresponding args are empty); these patches are the safety net that turns
   any prompt that still fires into a descriptive exception.

2. Main-thread-only APIs -- `signal.signal` raises ValueError off the main
   thread, which would mask real job errors.

Also installs the cooperative-cancel hooks: when the user hits Cancel, the
progress-update facades raise KeyboardInterrupt so the job unwinds through
the same cleanup paths the CLI uses for Ctrl+C.

Call install() once at GUI startup (before any job), uninstall() restores
originals (used by tests).
"""

import logging

from ofscraper.gui.errors import GuiAuthRequired, GuiPromptError
from ofscraper.gui.state import get_state

log = logging.getLogger("shared")

# ---------------------------------------------------------------------------
# Prompts that receive a programmatic answer instead of raising.
# Values verified against call sites:
#   - actions.py reset_download/reset_like compare == "Yes"
#   - managers/model.py reset_username_prompt expects
#     "No" | "Selection" | "Selection_Strict"
#   - retry_user_scan result is treated as a retry boolean
#   - continue_prompt/confirm_db_continue False ends the outer loop
# ---------------------------------------------------------------------------
PROMPT_DEFAULTS = {
    "retry_user_scan": lambda *a, **k: False,
    "reset_username_prompt": lambda *a, **k: "Selection_Strict",
    "reset_download_areas_prompt": lambda *a, **k: "No",
    "reset_like_areas_prompt": lambda *a, **k: "No",
    "reset_areas_prompt": lambda *a, **k: "No",
    "continue_prompt": lambda *a, **k: False,
    "confirm_db_continue": lambda *a, **k: False,
    "press_enter_to_continue": lambda *a, **k: None,
}


def _prompt_stub(name):
    default = PROMPT_DEFAULTS.get(name)

    def stub(*args, **kwargs):
        if default is not None:
            log.debug(f"GUI mode answered prompt '{name}' programmatically")
            return default(*args, **kwargs)
        raise GuiPromptError(name)

    stub.__name__ = f"gui_stub_{name}"
    return stub


def _install_prompt_guard():
    """Patch every prompt_group function exported on the prompts module.

    All call sites in the codebase access prompts via
    `import ofscraper.prompts.prompts as prompts` + `prompts.fn()` (verified:
    utils/actions.py, managers/model.py, utils/menu.py, utils/auth/make.py,
    utils/merge.py), so patching module attributes covers them all.
    """
    import ofscraper.prompts.prompts as prompts_module

    originals = getattr(_install_prompt_guard, "originals", None)
    if originals is None:
        originals = {}
        for name, value in list(vars(prompts_module).items()):
            if name.startswith("_"):
                continue
            if not callable(value):
                continue
            module = getattr(value, "__module__", "") or ""
            if not module.startswith("ofscraper.prompts.prompt_groups"):
                continue
            originals[name] = value
            setattr(prompts_module, name, _prompt_stub(name))
        _install_prompt_guard.originals = originals
        log.debug(f"GUI prompt guard installed over {len(originals)} prompts")


def _uninstall_prompt_guard():
    import ofscraper.prompts.prompts as prompts_module

    originals = getattr(_install_prompt_guard, "originals", None)
    if not originals:
        return
    for name, value in originals.items():
        setattr(prompts_module, name, value)
    _install_prompt_guard.originals = None


def _install_auth_guard():
    """make_auth drives a terminal browser-choice flow; divert to a dialog."""
    import ofscraper.utils.auth.make as auth_make

    def stub(*args, **kwargs):
        raise GuiAuthRequired()

    _install_auth_guard.original = auth_make.make_auth
    auth_make.make_auth = stub


def _uninstall_auth_guard():
    import ofscraper.utils.auth.make as auth_make

    if getattr(_install_auth_guard, "original", None) is not None:
        auth_make.make_auth = _install_auth_guard.original
        _install_auth_guard.original = None


def _install_signal_tolerance():
    """DelayedKeyboardInterrupt calls signal.signal, which is main-thread-only.

    Off the main thread it raises ValueError and would mask the real job
    exception (every error path is wrapped with @exit_wrapper /
    DelayedKeyboardInterrupt in utils/context/exit.py:82-96).
    """
    import ofscraper.utils.context.exit as exit_context

    cls = exit_context.DelayedKeyboardInterrupt
    original_enter = cls.__enter__
    original_exit = cls.__exit__

    def safe_enter(self):
        try:
            return original_enter(self)
        except ValueError:  # signal only works in main thread
            return None

    def safe_exit(self, *exc):
        try:
            return original_exit(self, *exc)
        except ValueError:
            return False

    _install_signal_tolerance.pair = (original_enter, original_exit)
    cls.__enter__ = safe_enter
    cls.__exit__ = safe_exit


def _uninstall_signal_tolerance():
    import ofscraper.utils.context.exit as exit_context

    pair = getattr(_install_signal_tolerance, "pair", None)
    if pair:
        cls = exit_context.DelayedKeyboardInterrupt
        cls.__enter__, cls.__exit__ = pair
        _install_signal_tolerance.pair = None


def _cancel_guard(fn):
    def wrapper(*args, **kwargs):
        if get_state().cancel_event.is_set():
            raise KeyboardInterrupt
        return fn(*args, **kwargs)

    wrapper.__name__ = getattr(fn, "__name__", "cancel_guarded")
    return wrapper


def _install_cancel_hooks():
    """Make progress updates cooperative cancellation points.

    Progress updates happen constantly during downloads and per-area during
    scrapes, so cancel latency is sub-second in practice.
    """
    import ofscraper.utils.live.updater as updater

    pairs = []
    for cls, methods in [
        (updater.ProgressManager, ["update_job_task", "update_overall_task"]),
        (updater.ActivityManager, ["update_task", "update_overall", "update_user"]),
    ]:
        for name in methods:
            original = getattr(cls, name)
            pairs.append((cls, name, original))
            setattr(cls, name, _cancel_guard(original))
    _install_cancel_hooks.pairs = pairs


def _uninstall_cancel_hooks():
    import ofscraper.utils.live.updater as updater

    for cls, name, original in getattr(_install_cancel_hooks, "pairs", []):
        setattr(cls, name, original)
    _install_cancel_hooks.pairs = []


def install():
    _install_prompt_guard()
    _install_auth_guard()
    _install_signal_tolerance()
    _install_cancel_hooks()
    log.info("GUI patches installed")


def uninstall():
    _uninstall_prompt_guard()
    _uninstall_auth_guard()
    _uninstall_signal_tolerance()
    _uninstall_cancel_hooks()
