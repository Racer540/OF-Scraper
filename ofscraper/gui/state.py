"""
Shared GUI state singleton.

Holds the job lifecycle (single-job lock + cancel event), cross-screen caches
and thread-safe handoff points used by the bridges and screens.  Everything in
here is written from worker threads and read from NiceGUI timers, so all
mutations go through the lock where consistency matters.
"""

import threading
from enum import Enum

from ofscraper.gui.bridges.logs import LogBuffer


class JobStatus(Enum):
    IDLE = "idle"
    RUNNING = "running"
    CANCELLING = "cancelling"


class GuiState:
    def __init__(self):
        # --- job lifecycle -------------------------------------------------
        # job_start_lock is the single-job guard: acquired non-blocking when a
        # job starts, released when the worker thread finishes.  The codebase
        # assumes one job at a time (module-level download globals, one log
        # file), so every Run button must consult this before starting.
        self.job_start_lock = threading.Lock()
        self._status = JobStatus.IDLE
        self._state_lock = threading.Lock()

        # cancel_event is consumed by the progress-updater hooks installed in
        # patches.py; setting it makes the next progress update raise
        # KeyboardInterrupt, which flows through the same cleanup paths the
        # CLI uses for Ctrl+C.
        self.cancel_event = threading.Event()

        self.job_description = ""
        self.job_result = ""
        self.job_error = ""
        self.job_started_at = None

        # --- cross-screen caches --------------------------------------------
        self.models = []  # cached Model objects from the model picker
        self.models_fetched_at = None
        self.models_fetch_error = ""
        self.models_fetch_in_flight = False  # set by fetch_models worker
        # timestamp of the persisted list (gui/models_cache.py); None when
        # the in-memory list never came from a fetch or the cache file
        self.models_cache_fetched_at = None
        self.models_cache_note = ""  # e.g. 'cached 3.2h old' for the status line
        self.selected_usernames = []  # names chosen in the model picker

        # --- check-command handoff (filled in by the check shim) ------------
        self.check_rows = []
        self.check_rows_ready = threading.Event()
        self.check_finished = threading.Event()
        self.check_row_states = {}  # index -> (state, style), updated by shim
        self.check_version = 0

        # --- db viewer -------------------------------------------------------
        self.db_rows = []
        self.db_loaded_at = None
        self.db_load_error = ""

        # --- merge -----------------------------------------------------------
        self.merge_result = ""
        self.merge_error = ""
        self.merge_finished_at = None

        # --- auth import + status (worker -> UI handoff) ---------------------
        self.auth_import_result = {}
        self.auth_import_message = ""
        self.auth_import_version = 0
        self.auth_status_message = ""
        self.auth_status_version = 0
        self.auth_fp_cookie = ""  # to catch fp-pasted-as-x-bc on save

        # --- auth state (written by gui/authstatus.py worker) ----------------
        # auth.json never stores the account username, so the logged-in name
        # only exists after a live /users/me check lands here.
        self.auth_ok = None  # None = never checked, True/False after
        self.auth_username = ""
        self.auth_checked_at = None
        self.auth_checking = False

        # --- log bridge ------------------------------------------------------
        self.log_buffer = LogBuffer()

    # ------------------------------------------------------------------ job
    @property
    def status(self) -> JobStatus:
        with self._state_lock:
            return self._status

    def begin_job(self, description: str = "") -> bool:
        """Try to mark a job as running.  Returns False if one is active."""
        if not self.job_start_lock.acquire(blocking=False):
            return False
        import time

        with self._state_lock:
            self._status = JobStatus.RUNNING
            self.job_description = description
            self.job_result = ""
            self.job_error = ""
            self.job_started_at = time.time()
        self.cancel_event.clear()
        return True

    def request_cancel(self):
        with self._state_lock:
            if self._status == JobStatus.RUNNING:
                self._status = JobStatus.CANCELLING
        self.cancel_event.set()

    def finish_job(self, result: str = "", error: str = ""):
        with self._state_lock:
            self._status = JobStatus.IDLE
            self.job_result = result
            self.job_error = error
        self.cancel_event.clear()
        if self.job_start_lock.locked():
            self.job_start_lock.release()

    @property
    def job_running(self) -> bool:
        return self.status in (JobStatus.RUNNING, JobStatus.CANCELLING)


_state: GuiState | None = None
_state_lock = threading.Lock()


def get_state() -> GuiState:
    global _state
    if _state is None:
        with _state_lock:
            if _state is None:
                _state = GuiState()
    return _state
